/// Object handling for copy-paste augmentation
/// Includes extraction and selection logic
use ndarray::{Array3, ArrayView3};
use rand::Rng;
use std::collections::HashMap;

/// Represents an extracted object from a mask
#[derive(Clone, Debug)]
pub struct ExtractedObject {
    /// The image patch for this object
    pub image: Array3<u8>,
    /// The mask for this object (binary)
    pub mask: Array3<u8>,
    /// Bounding box as (x_min, y_min, x_max, y_max) in pixel coordinates
    pub bbox: (u32, u32, u32, u32),
    /// Class ID of this object
    pub class_id: u32,
}

/// Lightweight metadata for a potential object
#[derive(Clone, Debug)]
pub struct ObjectCandidate {
    pub bbox: (u32, u32, u32, u32),
    pub class_id: u32,
}

/// Scan the mask to find all object candidates without extracting pixels.
/// This is memory efficient for large masks with many objects.
pub fn find_object_candidates(mask: ArrayView3<'_, u8>) -> Vec<ObjectCandidate> {
    let shape = mask.shape();
    let (height, width) = (shape[0], shape[1]);

    // Validate dimensions
    if height == 0 || width == 0 {
        return Vec::new();
    }

    let mut candidates = Vec::new();
    // Flattened visited array for better cache locality
    let mut visited = vec![false; width * height];

    for y in 0..height {
        for x in 0..width {
            let idx = y * width + x;
            if mask[[y, x, 0]] > 0 && !visited[idx] {
                // Found a new object, extract its bounding box
                let (x_min, y_min, x_max, y_max) =
                    find_object_bounds(&mask, x, y, &mut visited, width, height);

                if x_max > x_min && y_max > y_min {
                    // Determine class_id (simple heuristic: sample the start pixel)
                    let class_id = mask[[y, x, 0]] as u32;

                    candidates.push(ObjectCandidate {
                        bbox: (x_min as u32, y_min as u32, x_max as u32, y_max as u32),
                        class_id,
                    });
                }
            }
        }
    }

    candidates
}

/// Extract pixels for a specific list of candidates
pub fn extract_candidate_patches(
    image: ArrayView3<'_, u8>,
    mask: ArrayView3<'_, u8>,
    candidates: &[ObjectCandidate],
) -> Vec<ExtractedObject> {
    candidates
        .iter()
        .filter_map(|cand| {
            extract_object_patch(
                &image,
                &mask,
                cand.bbox.0,
                cand.bbox.1,
                cand.bbox.2,
                cand.bbox.3,
            )
        })
        .collect()
}

/// Select candidates based on class counts
pub fn select_candidates_by_class(
    candidates: &[ObjectCandidate],
    object_counts: &HashMap<u32, f32>,
    max_paste_objects: u32,
) -> Vec<ObjectCandidate> {
    if max_paste_objects == 0 {
        return Vec::new();
    }

    // Group by class
    let mut by_class: HashMap<u32, Vec<ObjectCandidate>> = HashMap::new();
    for cand in candidates {
        by_class
            .entry(cand.class_id)
            .or_insert_with(Vec::new)
            .push(cand.clone());
    }

    let mut selected = Vec::new();
    let mut rng = rand::thread_rng();
    let mut total_selected = 0usize;
    let global_cap = max_paste_objects as usize;

    if object_counts.is_empty() {
        for (_class_id, items) in by_class.iter() {
            if total_selected >= global_cap {
                break;
            }
            let remaining_global = global_cap - total_selected;
            let count_to_select = items.len().min(remaining_global);
            if count_to_select == 0 {
                continue;
            }

            let mut indices: Vec<usize> = (0..items.len()).collect();
            let safe_count = count_to_select.min(items.len());
            for i in 0..safe_count {
                let remaining = indices.len() - i;
                if remaining == 0 {
                    break;
                }
                let j = i + rng.gen_range(0..remaining);
                indices.swap(i, j);
                selected.push(items[indices[i]].clone());
            }
            total_selected += safe_count;
        }
    } else {
        for (class_id, value) in object_counts.iter() {
            if total_selected >= global_cap {
                break;
            }

            if let Some(items) = by_class.get(class_id) {
                let actual_count = if *value >= 1.0 {
                    (*value).round() as usize
                } else if *value > 0.0 && *value < 1.0 {
                    if rng.gen::<f32>() < *value {
                        1
                    } else {
                        0
                    }
                } else {
                    0
                };

                if actual_count == 0 {
                    continue;
                }

                let remaining_global = global_cap - total_selected;
                let per_class_cap = actual_count.min(items.len());
                let count_to_select = per_class_cap.min(remaining_global);

                if count_to_select == 0 {
                    continue;
                }

                let mut indices: Vec<usize> = (0..items.len()).collect();
                let safe_count = count_to_select.min(items.len());
                for i in 0..safe_count {
                    let remaining = indices.len() - i;
                    if remaining == 0 {
                        break;
                    }
                    let j = i + rng.gen_range(0..remaining);
                    indices.swap(i, j);
                    selected.push(items[indices[i]].clone());
                }
                total_selected += safe_count;
            }
        }
    }

    selected
}

/// Extract all objects from a mask where each unique non-zero value is an object
#[allow(dead_code)]
pub fn extract_objects_from_mask(
    image: ArrayView3<'_, u8>,
    mask: ArrayView3<'_, u8>,
) -> Vec<ExtractedObject> {
    let candidates = find_object_candidates(mask);
    extract_candidate_patches(image, mask, &candidates)
}

/// Find the bounding box of an object starting from a point
fn find_object_bounds(
    mask: &ArrayView3<'_, u8>,
    start_x: usize,
    start_y: usize,
    visited: &mut [bool],
    width: usize,
    height: usize,
) -> (usize, usize, usize, usize) {
    let mut x_min = start_x;
    let mut x_max = start_x + 1;
    let mut y_min = start_y;
    let mut y_max = start_y + 1;

    // Simple flood fill to find bounds
    let mut stack = vec![(start_x, start_y)];

    // Maximum iterations to prevent infinite loops
    let max_iterations = width * height;
    let mut iterations = 0;

    while let Some((x, y)) = stack.pop() {
        iterations += 1;
        if iterations > max_iterations {
            break;
        }

        if x >= width || y >= height {
            continue;
        }

        let idx = y * width + x;
        if visited[idx] {
            continue;
        }

        if mask[[y, x, 0]] == 0 {
            continue;
        }

        visited[idx] = true;

        x_min = x_min.min(x);
        x_max = x_max.max(x + 1);
        y_min = y_min.min(y);
        y_max = y_max.max(y + 1);

        // Check neighbors
        if x > 0 {
            stack.push((x - 1, y));
        }
        if x < width - 1 {
            stack.push((x + 1, y));
        }
        if y > 0 {
            stack.push((x, y - 1));
        }
        if y < height - 1 {
            stack.push((x, y + 1));
        }
    }

    (x_min, y_min, x_max, y_max)
}

/// Extract a patch from the image and mask
fn extract_object_patch(
    image: &ArrayView3<'_, u8>,
    mask: &ArrayView3<'_, u8>,
    x_min: u32,
    y_min: u32,
    x_max: u32,
    y_max: u32,
) -> Option<ExtractedObject> {
    let patch_height = (y_max - y_min) as usize;
    let patch_width = (x_max - x_min) as usize;
    let channels = image.shape()[2];
    let mask_channels = mask.shape()[2];

    if patch_height == 0 || patch_width == 0 {
        return None;
    }

    // Create patch arrays
    let mut patch_image = Array3::zeros((patch_height, patch_width, channels));
    let mut patch_mask = Array3::zeros((patch_height, patch_width, channels));

    // Copy data
    let img_shape = image.shape();
    let mut class_counts = [0usize; 256];

    for y in 0..patch_height {
        for x in 0..patch_width {
            let src_y = (y_min as usize) + y;
            let src_x = (x_min as usize) + x;

            if src_y < img_shape[0] && src_x < img_shape[1] {
                let class_value = mask[[src_y, src_x, 0]];
                if class_value > 0 {
                    class_counts[class_value as usize] += 1;
                }

                for c in 0..channels {
                    patch_image[[y, x, c]] = image[[src_y, src_x, c]];

                    let mask_channel = if c < mask_channels { c } else { 0 };
                    let mask_value = mask[[src_y, src_x, mask_channel]];
                    patch_mask[[y, x, c]] = if mask_value > 0 { 255 } else { 0 };
                }
            }
        }
    }

    let mut class_id = 0u32;
    let mut max_count = 0usize;
    for (value, count) in class_counts.iter().enumerate() {
        if value == 0 || *count == 0 {
            continue;
        }

        if *count > max_count {
            max_count = *count;
            class_id = value as u32;
        }
    }

    Some(ExtractedObject {
        image: patch_image,
        mask: patch_mask,
        bbox: (x_min, y_min, x_max, y_max),
        class_id,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::Array3;

    #[test]
    fn test_extract_objects_from_mask() {
        // Create a simple test image and mask
        let image = Array3::zeros((10, 10, 3));
        let mut mask = Array3::zeros((10, 10, 3));

        // Add a simple object (a small rectangle)
        for y in 2..5 {
            for x in 2..5 {
                mask[[y, x, 0]] = 1;
            }
        }

        let objects = extract_objects_from_mask(image.view(), mask.view());
        assert!(!objects.is_empty());
        assert_eq!(objects[0].class_id, 1);
    }

    #[test]
    fn test_extract_objects_produces_binary_masks_for_blending() {
        let image = Array3::zeros((8, 8, 3));
        let mut mask = Array3::zeros((8, 8, 3));

        for y in 2..6 {
            for x in 2..6 {
                mask[[y, x, 0]] = 7; // class id, not alpha
            }
        }

        let objects = extract_objects_from_mask(image.view(), mask.view());
        assert_eq!(objects.len(), 1);
        let extracted = &objects[0];
        assert_eq!(extracted.class_id, 7);

        let unique_values: std::collections::HashSet<u8> = extracted.mask.iter().copied().collect();
        assert!(
            unique_values.iter().all(|&v| v == 0 || v == 255),
            "mask used for blending should be binary"
        );
        assert!(
            unique_values.contains(&255),
            "mask should retain opaque coverage for the object"
        );
    }

    #[test]
    fn test_select_candidates_by_class() {
        let candidates = vec![
            ObjectCandidate { bbox: (0,0,1,1), class_id: 1 },
            ObjectCandidate { bbox: (2,2,3,3), class_id: 1 },
            ObjectCandidate { bbox: (4,4,5,5), class_id: 2 },
        ];
        
        let mut counts = HashMap::new();
        counts.insert(1, 2.0);
        counts.insert(2, 1.0);

        let selected = select_candidates_by_class(&candidates, &counts, 10);
        assert_eq!(selected.len(), 3);
    }
}