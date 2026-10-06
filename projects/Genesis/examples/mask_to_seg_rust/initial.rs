use std::env;
use std::fs;
use std::io::{self, BufRead, BufReader};

#[derive(Debug, Clone, PartialEq, Eq, Copy)]
struct Point {
    x: i32,
    y: i32,
}

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 {
        eprintln!("Usage: {} <input_mask.txt> <output_polys.json>", args[0]);
        std::process::exit(1);
    }

    let input_path = &args[1];
    let output_path = &args[2];

    let (width, height, grid) = read_mask(input_path)?;

    // Baseline: Moore-Neighbor Tracing + Flood Fill for visited
    // This produces ordered polygons, so IoU should be > 0.
    let contours = find_contours(width, height, &grid);

    write_json(output_path, &contours)?;

    Ok(())
}

fn read_mask(path: &str) -> io::Result<(usize, usize, Vec<u8>)> {
    let file = fs::File::open(path)?;
    let reader = BufReader::new(file);
    let mut lines = reader.lines();

    let header = lines.next().ok_or(io::Error::new(io::ErrorKind::InvalidData, "Empty file"))??;
    let parts: Vec<&str> = header.split_whitespace().collect();
    if parts.len() < 2 {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "Invalid header"));
    }
    let width: usize = parts[0].parse().unwrap();
    let height: usize = parts[1].parse().unwrap();

    let mut grid = Vec::with_capacity(width * height);
    for line in lines {
        let line = line?;
        for val in line.split_whitespace() {
            if let Ok(pixel) = val.parse::<u8>() {
                grid.push(pixel);
            }
        }
    }

    Ok((width, height, grid))
}

fn find_contours(width: usize, height: usize, grid: &[u8]) -> Vec<Vec<Point>> {
    let mut visited = vec![false; width * height];
    let mut contours = Vec::new();

    for y in 0..height {
        for x in 0..width {
            let idx = y * width + x;
            if idx < grid.len() && grid[idx] > 0 && !visited[idx] {
                // Found new blob. (x,y) is the top-left-most pixel because of scan order.
                // 1. Mark component as visited
                flood_fill_mark(width, height, grid, &mut visited, x, y);
                
                // 2. Trace boundary
                let poly = trace_boundary(width, height, grid, x, y);
                if !poly.is_empty() {
                    contours.push(poly);
                }
            }
        }
    }
    contours
}

fn flood_fill_mark(width: usize, height: usize, grid: &[u8], visited: &mut [bool], start_x: usize, start_y: usize) {
    let mut stack = vec![(start_x, start_y)];
    let start_idx = start_y * width + start_x;
    // We might have already visited this pixel in the main loop? 
    // No, main loop checks !visited.
    // But trace_boundary doesn't mark visited.
    visited[start_idx] = true;
    
    while let Some((cx, cy)) = stack.pop() {
        let neighbors = [
            (cx.wrapping_sub(1), cy), (cx+1, cy), 
            (cx, cy.wrapping_sub(1)), (cx, cy+1)
        ];
        for (nx, ny) in neighbors {
            if nx < width && ny < height {
                let nidx = ny * width + nx;
                if grid[nidx] > 0 && !visited[nidx] {
                    visited[nidx] = true;
                    stack.push((nx, ny));
                }
            }
        }
    }
}

fn trace_boundary(width: usize, height: usize, grid: &[u8], start_x: usize, start_y: usize) -> Vec<Point> {
    let mut contour = Vec::new();
    let start = Point { x: start_x as i32, y: start_y as i32 };
    contour.push(start);
    
    // Moore-Neighbor tracing
    // Directions: N, NE, E, SE, S, SW, W, NW
    // Indices:    0,  1, 2,  3, 4,  5, 6,  7
    let dirs = [
        (0, -1), (1, -1), (1, 0), (1, 1), 
        (0, 1), (-1, 1), (-1, 0), (-1, -1)
    ];
    
    let mut curr = start;
    // Entered from West (index 6 is West, so we start search from 7? or 0?)
    // We assume (x-1, y) is 0. We start searching clockwise from West?
    // Standard: if entered from dir D, start search at D+1?
    // Let's try starting search from index 7 (NW) if we assume 6 (W) is empty.
    let mut search_start_idx = 7;
    
    let mut steps = 0;
    loop {
        let mut found_next = false;
        let mut next_pt = curr;
        let mut next_from_idx = 0; // The index of the neighbor we found
        
        for i in 0..8 {
            let idx = (search_start_idx + i) % 8;
            let (dx, dy) = dirs[idx];
            let nx = curr.x + dx;
            let ny = curr.y + dy;
            
            if nx >= 0 && nx < width as i32 && ny >= 0 && ny < height as i32 {
                let idx_grid = (ny as usize) * width + (nx as usize);
                if grid[idx_grid] > 0 {
                    // Found
                    next_pt = Point { x: nx, y: ny };
                    next_from_idx = idx;
                    found_next = true;
                    break;
                }
            }
        }
        
        if !found_next {
            break; // Isolated point
        }
        
        // Backtrack rule: (found_idx + 4 + 1) % 8 is not robust?
        // Use (found_idx + 5) % 8.
        search_start_idx = (next_from_idx + 5) % 8;
        
        curr = next_pt;
        
        // Stop if back to start
        if curr == start {
            // Check if we are heading in the same direction as first move?
            // For simple polygons, just hitting start is enough usually.
            // But standard Jacobs criterion is (curr == start AND next_dir == first_dir).
            // Let's just stop at start for simplicity.
            break;
        }
        contour.push(curr);
        
        steps += 1;
        if steps > width * height * 2 { break; } // Safety
    }
    
    contour
}

fn write_json(path: &str, contours: &[Vec<Point>]) -> io::Result<()> {
    let mut json = String::new();
    json.push('[');
    for (i, poly) in contours.iter().enumerate() {
        if i > 0 { json.push(','); }
        json.push('[');
        for (j, p) in poly.iter().enumerate() {
            if j > 0 { json.push(','); }
            json.push_str(&format!("[{},{}]", p.x, p.y));
        }
        json.push(']');
    }
    json.push(']');
    
    fs::write(path, json)
}
