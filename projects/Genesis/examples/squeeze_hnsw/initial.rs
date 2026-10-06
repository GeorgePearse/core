use std::collections::{BinaryHeap, HashSet};
use std::cmp::Ordering;
use std::env;
use std::fs;
use std::io::{self, BufRead, BufReader, Write};

/// Candidate for priority queues
#[derive(Clone, Copy, Debug)]
struct Candidate {
    index: usize,
    distance: f32,
}

impl PartialEq for Candidate {
    fn eq(&self, other: &Self) -> bool {
        self.distance == other.distance && self.index == other.index
    }
}
impl Eq for Candidate {}

// MinHeap ordering (smallest distance first via reverse)
impl PartialOrd for Candidate {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Candidate {
    fn cmp(&self, other: &Self) -> Ordering {
        other.distance.partial_cmp(&self.distance)
            .unwrap_or(Ordering::Equal)
            .then_with(|| other.index.cmp(&self.index))
    }
}

/// MaxHeap wrapper
#[derive(Clone, Copy, Debug)]
struct MaxDistCandidate(Candidate);

impl PartialEq for MaxDistCandidate {
    fn eq(&self, other: &Self) -> bool { self.0.eq(&other.0) }
}
impl Eq for MaxDistCandidate {}
impl PartialOrd for MaxDistCandidate {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        self.0.distance.partial_cmp(&other.0.distance)
    }
}
impl Ord for MaxDistCandidate {
    fn cmp(&self, other: &Self) -> Ordering {
        self.0.distance.partial_cmp(&other.0.distance)
            .unwrap_or(Ordering::Equal)
    }
}

/// HNSW Node - stores neighbors at each layer
#[derive(Clone, Debug)]
struct Node {
    links: Vec<Vec<usize>>,
}

impl Node {
    fn new(level: usize) -> Self {
        let mut links = Vec::with_capacity(level + 1);
        for _ in 0..=level {
            links.push(Vec::new());
        }
        Self { links }
    }

    fn level(&self) -> usize {
        if self.links.is_empty() { 0 } else { self.links.len() - 1 }
    }
}

/// Simple HNSW graph for k-NN search
struct Hnsw {
    nodes: Vec<Node>,
    entry_point: Option<usize>,
    m: usize,
    m_max0: usize,
    ef_construction: usize,
}

impl Hnsw {
    fn new(m: usize, ef_construction: usize, capacity: usize) -> Self {
        Self {
            nodes: Vec::with_capacity(capacity),
            entry_point: None,
            m,
            m_max0: m * 2,
            ef_construction,
        }
    }

    fn get_random_level(&self, seed: usize) -> usize {
        // Simple deterministic level assignment based on index
        let level_mult = 1.0 / (self.m as f64).ln();
        let r = ((seed * 2654435761) % 1000000) as f64 / 1000000.0;
        let level = (-r.ln() * level_mult).floor() as usize;
        level.min(10) // Cap at 10 layers
    }

    fn insert(&mut self, item_idx: usize, data: &[Vec<f32>]) {
        let level = self.get_random_level(item_idx);
        let mut new_node = Node::new(level);

        if item_idx >= self.nodes.len() {
            self.nodes.resize(item_idx + 1, Node::new(0));
        }

        let entry_point = match self.entry_point {
            Some(ep) => ep,
            None => {
                self.nodes[item_idx] = new_node;
                self.entry_point = Some(item_idx);
                return;
            }
        };

        let max_level = self.nodes[entry_point].level();
        let mut curr_obj = entry_point;
        let mut curr_dist = euclidean_distance(&data[item_idx], &data[curr_obj]);

        // Navigate through upper layers
        for l in (level + 1..=max_level).rev() {
            let mut changed = true;
            while changed {
                changed = false;
                let current_node = &self.nodes[curr_obj];
                if l >= current_node.links.len() { break; }

                for &neighbor_idx in &current_node.links[l] {
                    let d = euclidean_distance(&data[item_idx], &data[neighbor_idx]);
                    if d < curr_dist {
                        curr_dist = d;
                        curr_obj = neighbor_idx;
                        changed = true;
                    }
                }
            }
        }

        let mut ep = curr_obj;

        // Insert at each layer
        for l in (0..=level.min(max_level)).rev() {
            let candidates = self.search_layer(ep, item_idx, self.ef_construction, l, data);

            if let Some(c) = candidates.peek() {
                ep = c.index;
            }

            let m_allowed = if l == 0 { self.m_max0 } else { self.m };
            let selected = Self::select_neighbors(&candidates, m_allowed);

            new_node.links[l] = selected.clone();

            // Add bidirectional links
            for &neighbor_idx in &selected {
                let mut neighbor_links = self.nodes[neighbor_idx].links[l].clone();
                neighbor_links.push(item_idx);

                let m_neigh_allowed = if l == 0 { self.m_max0 } else { self.m };
                if neighbor_links.len() > m_neigh_allowed {
                    neighbor_links = self.prune_connections(neighbor_idx, &neighbor_links, m_neigh_allowed, data);
                }

                self.nodes[neighbor_idx].links[l] = neighbor_links;
            }
        }

        self.nodes[item_idx] = new_node;

        if level > max_level {
            self.entry_point = Some(item_idx);
        }
    }

    // EVOLVE-BLOCK-START
    /// Core beam search algorithm - this is the hot path to optimize
    fn search_layer(
        &self,
        entry_point: usize,
        query_idx: usize,
        ef: usize,
        level: usize,
        data: &[Vec<f32>],
    ) -> BinaryHeap<Candidate> {
        let query = &data[query_idx];
        let mut visited = vec![false; self.nodes.len()];
        let d_ep = euclidean_distance(query, &data[entry_point]);
        visited[entry_point] = true;

        // Candidates to explore (min-heap by distance)
        let mut c_heap = BinaryHeap::new();
        c_heap.push(Candidate { index: entry_point, distance: d_ep });

        // Best results so far (max-heap to track worst best)
        let mut w_heap = BinaryHeap::new();
        w_heap.push(MaxDistCandidate(Candidate { index: entry_point, distance: d_ep }));

        while let Some(c) = c_heap.pop() {
            // Stop only once heap is full and candidate is already worse than worst.
            let worst_dist = w_heap.peek().map(|f| f.0.distance).unwrap_or(f32::INFINITY);
            if w_heap.len() >= ef && c.distance > worst_dist {
                break;
            }

            let c_node = &self.nodes[c.index];
            if level >= c_node.links.len() { continue; }

            // Explore neighbors
            for &neighbor_idx in &c_node.links[level] {
                if visited[neighbor_idx] {
                    continue;
                }
                visited[neighbor_idx] = true;

                let d = euclidean_distance(query, &data[neighbor_idx]);
                if w_heap.len() < ef {
                    let cand = Candidate { index: neighbor_idx, distance: d };
                    c_heap.push(cand);
                    w_heap.push(MaxDistCandidate(cand));
                    continue;
                }

                let f_curr = w_heap.peek().unwrap();
                if d < f_curr.0.distance {
                    let cand = Candidate { index: neighbor_idx, distance: d };
                    c_heap.push(cand);
                    w_heap.push(MaxDistCandidate(cand));

                    // Maintain ef size
                    if w_heap.len() > ef {
                        w_heap.pop();
                    }
                }
            }
        }

        // Convert to result heap
        let mut result = BinaryHeap::new();
        for wrapper in w_heap {
            result.push(wrapper.0);
        }
        result
    }
    // EVOLVE-BLOCK-END

    fn select_neighbors(candidates: &BinaryHeap<Candidate>, m: usize) -> Vec<usize> {
        let mut sorted: Vec<_> = candidates.iter().copied().collect();
        sorted.sort_by(|a, b| a.distance.partial_cmp(&b.distance).unwrap_or(Ordering::Equal));
        sorted.into_iter().take(m).map(|c| c.index).collect()
    }

    fn prune_connections(
        &self,
        node_idx: usize,
        neighbors: &[usize],
        m_max: usize,
        data: &[Vec<f32>],
    ) -> Vec<usize> {
        let mut candidates: BinaryHeap<Candidate> = BinaryHeap::new();
        for &neigh in neighbors {
            let d = euclidean_distance(&data[node_idx], &data[neigh]);
            candidates.push(Candidate { index: neigh, distance: d });
        }
        Self::select_neighbors(&candidates, m_max)
    }

    /// Main search function - find k nearest neighbors
    fn search(&self, query: &[f32], k: usize, ef: usize, data: &[Vec<f32>]) -> Vec<(usize, f32)> {
        if self.entry_point.is_none() { return Vec::new(); }
        let entry_point = self.entry_point.unwrap();

        let dist_to_query = |idx: usize| euclidean_distance(query, &data[idx]);

        let mut curr_obj = entry_point;
        let mut curr_dist = dist_to_query(curr_obj);

        let max_level = self.nodes[entry_point].level();

        // Navigate upper layers greedily
        for l in (1..=max_level).rev() {
            let mut changed = true;
            while changed {
                changed = false;
                let current_node = &self.nodes[curr_obj];
                if l >= current_node.links.len() { break; }

                for &neighbor_idx in &current_node.links[l] {
                    let d = dist_to_query(neighbor_idx);
                    if d < curr_dist {
                        curr_dist = d;
                        curr_obj = neighbor_idx;
                        changed = true;
                    }
                }
            }
        }

        // Search at base layer
        let mut visited = HashSet::new();
        let mut c_heap = BinaryHeap::new();
        let mut w_heap = BinaryHeap::new();

        visited.insert(curr_obj);
        c_heap.push(Candidate { index: curr_obj, distance: curr_dist });
        w_heap.push(MaxDistCandidate(Candidate { index: curr_obj, distance: curr_dist }));

        while let Some(c) = c_heap.pop() {
            let f = w_heap.peek().unwrap();
            if c.distance > f.0.distance { break; }

            let c_node = &self.nodes[c.index];
            if c_node.links.is_empty() { continue; }

            for &neighbor_idx in &c_node.links[0] {
                if !visited.contains(&neighbor_idx) {
                    visited.insert(neighbor_idx);
                    let d = dist_to_query(neighbor_idx);
                    let f_curr = w_heap.peek().unwrap();

                    if d < f_curr.0.distance || w_heap.len() < ef {
                        let cand = Candidate { index: neighbor_idx, distance: d };
                        c_heap.push(cand);
                        w_heap.push(MaxDistCandidate(cand));
                        if w_heap.len() > ef {
                            w_heap.pop();
                        }
                    }
                }
            }
        }

        let mut result_vec: Vec<_> = w_heap.into_iter().map(|w| (w.0.index, w.0.distance)).collect();
        result_vec.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(Ordering::Equal));
        result_vec.truncate(k);
        result_vec
    }
}

/// Euclidean distance between two vectors
fn euclidean_distance(a: &[f32], b: &[f32]) -> f32 {
    a.iter()
        .zip(b.iter())
        .map(|(x, y)| (x - y).powi(2))
        .sum::<f32>()
        .sqrt()
}

/// Read dataset from file
fn read_data(path: &str) -> io::Result<Vec<Vec<f32>>> {
    let file = fs::File::open(path)?;
    let reader = BufReader::new(file);
    let mut data = Vec::new();

    for line in reader.lines() {
        let line = line?;
        if line.trim().is_empty() { continue; }
        let vec: Vec<f32> = line.split_whitespace()
            .filter_map(|s| s.parse().ok())
            .collect();
        if !vec.is_empty() {
            data.push(vec);
        }
    }
    Ok(data)
}

/// Read queries from file
fn read_queries(path: &str) -> io::Result<Vec<Vec<f32>>> {
    read_data(path)
}

/// Write results to JSON
fn write_results(path: &str, results: &[Vec<(usize, f32)>]) -> io::Result<()> {
    let mut file = fs::File::create(path)?;
    write!(file, "[")?;
    for (i, result) in results.iter().enumerate() {
        if i > 0 { write!(file, ",")?; }
        write!(file, "[")?;
        for (j, (idx, dist)) in result.iter().enumerate() {
            if j > 0 { write!(file, ",")?; }
            write!(file, "[{},{}]", idx, dist)?;
        }
        write!(file, "]")?;
    }
    write!(file, "]")?;
    Ok(())
}

fn main() -> io::Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 4 {
        eprintln!("Usage: {} <data.txt> <queries.txt> <output.json>", args[0]);
        std::process::exit(1);
    }

    let data_path = &args[1];
    let query_path = &args[2];
    let output_path = &args[3];

    // Read data and queries
    let data = read_data(data_path)?;
    let queries = read_queries(query_path)?;

    if data.is_empty() {
        eprintln!("Empty dataset");
        std::process::exit(1);
    }

    // Build HNSW index
    let m = 16;
    let ef_construction = 100;
    let mut hnsw = Hnsw::new(m, ef_construction, data.len());

    for i in 0..data.len() {
        hnsw.insert(i, &data);
    }

    // Search for each query
    let k = 10;
    let ef_search = 50;
    let mut results = Vec::with_capacity(queries.len());

    for query in &queries {
        let neighbors = hnsw.search(query, k, ef_search, &data);
        results.push(neighbors);
    }

    // Write results
    write_results(output_path, &results)?;

    Ok(())
}
