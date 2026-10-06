use crate::affine::{transform_patch, BOUNDARY_EPSILON};
use crate::blending::{blend_pixel, BlendMode};
use crate::collision::{check_iou_collision, clip_bbox_to_image};
use crate::objects::ExtractedObject;
use ndarray::{s, Array3};
use rand::Rng;

/// Represents a placed object with its transformed location
#[derive(Clone, Debug)]
pub struct PlacedObject {
    /// Transformed bbox as (x_min, y_min, x_max, y_max)
    pub bbox: (f32, f32, f32, f32),
    /// The transformed image patch
    pub image: Array3<u8>,
    /// The transformed mask patch
    pub mask: Array3<u8>,
    /// Class ID
    pub class_id: u32,
    /// Rotation in degrees applied to the object
    pub rotation: f32,
}

/// Place objects onto target image with collision detection
///
/// # Arguments
/// * `selected_objects` - Objects to place
/// * `image_width` - Target image width
/// * `image_height` - Target image height
/// * `use_rotation` - Whether to apply random rotation
/// * `use_scaling` - Whether to apply random scaling
/// * `rotation_range` - (min, max) rotation in degrees
/// * `scale_range` - (min, max) scale factors
/// * `collision_threshold` - IoU threshold for collision detection (0.0 = no collision)
///
/// # Returns
/// Vector of successfully placed objects with their transformed bboxes
#[allow(clippy::similar_names)]
pub fn place_objects(
    selected_objects: &[ExtractedObject],
    image_width: u32,
    image_height: u32,
    use_rotation: bool,
    use_scaling: bool,
    rotation_range: (f32, f32),
    scale_range: (f32, f32),
    collision_threshold: f32,
) -> Vec<PlacedObject> {
    let mut placed: Vec<PlacedObject> = Vec::new();
    let mut rng = rand::thread_rng();

    for obj in selected_objects {
        // Random center position within image bounds based on original patch size
        let obj_width = (obj.bbox.2 - obj.bbox.0) as f32;
        let obj_height = (obj.bbox.3 - obj.bbox.1) as f32;

        let image_width_f = image_width as f32;
        let image_height_f = image_height as f32;

        if image_width_f < obj_width || image_height_f < obj_height {
            continue; // Object too large for image
        }

        let half_width = obj_width / 2.0;
        let half_height = obj_height / 2.0;

        let center_x_min = half_width;
        let center_x_max = image_width_f - half_width;
        let center_y_min = half_height;
        let center_y_max = image_height_f - half_height;

        let center_x = if (center_x_max - center_x_min).abs() <= f32::EPSILON {
            center_x_min
        } else {
            rng.gen_range(center_x_min..=center_x_max)
        };

        let center_y = if (center_y_max - center_y_min).abs() <= f32::EPSILON {
            center_y_min
        } else {
            rng.gen_range(center_y_min..=center_y_max)
        };

        // Random transformation parameters
        let rotation = if use_rotation {
            rng.gen_range(rotation_range.0..=rotation_range.1)
        } else {
            0.0
        };

        let scale = if use_scaling {
            rng.gen_range(scale_range.0..=scale_range.1)
        } else {
            1.0
        };

        // Apply rotation and scaling transformation to the patch
        let (mut transformed_image, mut transformed_mask, offset_x, offset_y) =
            if rotation != 0.0 || (scale - 1.0).abs() > BOUNDARY_EPSILON {
                transform_patch(&obj.image, &obj.mask, rotation, scale)
            } else {
                (
                    obj.image.clone(),
                    obj.mask.clone(),
                    -half_width,
                    -half_height,
                )
            };

        let patch_width = transformed_image.shape()[1] as f32;
        let patch_height = transformed_image.shape()[0] as f32;

        let raw_bbox = (
            center_x + offset_x,
            center_y + offset_y,
            center_x + offset_x + patch_width,
            center_y + offset_y + patch_height,
        );

        let clipped_bbox = clip_bbox_to_image(raw_bbox, image_width, image_height);

        // Calculate how much of the transformed patch lies inside the image
        let trim_left = (clipped_bbox.0 - raw_bbox.0).max(0.0);
        let trim_top = (clipped_bbox.1 - raw_bbox.1).max(0.0);
        let trim_right = (raw_bbox.2 - clipped_bbox.2).max(0.0);
        let trim_bottom = (raw_bbox.3 - clipped_bbox.3).max(0.0);

        let src_width = transformed_image.shape()[1];
        let src_height = transformed_image.shape()[0];

        let x_start = trim_left.round().clamp(0.0, src_width as f32) as usize;
        let y_start = trim_top.round().clamp(0.0, src_height as f32) as usize;
        let x_end = src_width.saturating_sub(trim_right.round() as usize);
        let y_end = src_height.saturating_sub(trim_bottom.round() as usize);

        if x_start >= x_end || y_start >= y_end {
            continue; // Patch lies completely outside the image
        }

        // Crop the patch to the visible region
        transformed_image = transformed_image
            .slice(s![y_start..y_end, x_start..x_end, ..])
            .to_owned();
        transformed_mask = transformed_mask
            .slice(s![y_start..y_end, x_start..x_end, ..])
            .to_owned();

        // Calculate tight bbox from actual mask pixels
        let tight_bbox = match calculate_tight_bbox_from_mask(&transformed_mask) {
            Some(bbox) => bbox,
            None => continue, // No mask pixels found, skip this object
        };

        let (tight_x_min, tight_y_min, tight_x_max, tight_y_max) = tight_bbox;

        // Further crop to tight bounds
        transformed_image = transformed_image
            .slice(s![tight_y_min..tight_y_max, tight_x_min..tight_x_max, ..])
            .to_owned();
        transformed_mask = transformed_mask
            .slice(s![tight_y_min..tight_y_max, tight_x_min..tight_x_max, ..])
            .to_owned();

        let tight_width = transformed_image.shape()[1] as f32;
        let tight_height = transformed_image.shape()[0] as f32;

        // Calculate final bbox accounting for both initial crop and tight bbox
        let final_x_min =
            (raw_bbox.0 + x_start as f32 + tight_x_min as f32).clamp(0.0, image_width_f);
        let final_y_min =
            (raw_bbox.1 + y_start as f32 + tight_y_min as f32).clamp(0.0, image_height_f);
        let final_x_max = (final_x_min + tight_width).min(image_width_f);
        let final_y_max = (final_y_min + tight_height).min(image_height_f);

        if final_x_max - final_x_min <= 0.0 || final_y_max - final_y_min <= 0.0 {
            continue;
        }

        let final_bbox = (final_x_min, final_y_min, final_x_max, final_y_max);

        // Check for collisions with already-placed objects using the final bbox
        let mut has_collision = false;
        for placed_obj in &placed {
            if check_iou_collision(final_bbox, placed_obj.bbox, collision_threshold) {
                has_collision = true;
                break;
            }
        }

        if has_collision {
            continue; // Skip this object due to collision
        }

        let placed_obj = PlacedObject {
            bbox: final_bbox,
            image: transformed_image,
            mask: transformed_mask,
            class_id: obj.class_id,
            rotation,
        };

        placed.push(placed_obj);
    }

    placed
}

/// Calculate tight bounding box from actual mask content
fn calculate_tight_bbox_from_mask(mask: &Array3<u8>) -> Option<(usize, usize, usize, usize)> {
    let height = mask.shape()[0];
    let width = mask.shape()[1];

    let mut min_x = width;
    let mut min_y = height;
    let mut max_x = 0;
    let mut max_y = 0;
    let mut found_pixel = false;

    // Scan all pixels to find non-zero mask values
    for y in 0..height {
        for x in 0..width {
            // Check if any channel has non-zero value
            let has_mask = mask[[y, x, 0]] > 0;

            if has_mask {
                found_pixel = true;
                min_x = min_x.min(x);
                min_y = min_y.min(y);
                max_x = max_x.max(x);
                max_y = max_y.max(y);
            }
        }
    }

    if found_pixel {
        // Add 1 to max values to make them exclusive (standard bbox convention)
        Some((min_x, min_y, max_x + 1, max_y + 1))
    } else {
        None
    }
}

/// Compose placed objects onto target image with blending
pub fn compose_objects(
    output_image: &mut Array3<u8>,
    placed_objects: &[PlacedObject],
    blend_mode: BlendMode,
) {
    let out_shape = output_image.shape();
    let (height, width, channels) = (out_shape[0], out_shape[1], out_shape[2]);

    for placed_obj in placed_objects {
        let (x_min_f, y_min_f, _, _) = placed_obj.bbox;
        let x_min = x_min_f.floor().max(0.0) as usize;
        let y_min = y_min_f.floor().max(0.0) as usize;

        if x_min >= width || y_min >= height {
            continue;
        }

        let obj_shape = placed_obj.image.shape();
        let patch_height = obj_shape[0];
        let patch_width = obj_shape[1];

        if patch_height == 0 || patch_width == 0 {
            continue;
        }

        let y_max = (y_min + patch_height).min(height);
        let x_max = (x_min + patch_width).min(width);

        let target_height = y_max.saturating_sub(y_min);
        let target_width = x_max.saturating_sub(x_min);

        if target_width == 0 || target_height == 0 {
            continue;
        }

        // Blend the object patch onto the output image
        // Using the mask to determine alpha blending
        for py in 0..target_height {
            for px in 0..target_width {
                let target_y = y_min + py;
                let target_x = x_min + px;

                if target_y >= height || target_x >= width {
                    continue;
                }

                // Use mask to determine if pixel should be blended
                let mask_value = placed_obj.mask[[py, px, 0]];
                if mask_value == 0 {
                    continue; // Skip transparent pixels
                }

                let alpha = (mask_value as f32) / 255.0;

                // Blend each channel
                for c in 0..channels {
                    let base_pixel = output_image[[target_y, target_x, c]];
                    let overlay_pixel = placed_obj.image[[py, px, c]];

                    let blended = blend_pixel(base_pixel, overlay_pixel, alpha, blend_mode);
                    output_image[[target_y, target_x, c]] = blended;
                }
            }
        }
    }
}

/// Update output mask with placed objects
pub fn update_output_mask(output_mask: &mut Array3<u8>, placed_objects: &[PlacedObject]) {
    let out_shape = output_mask.shape();
    let (height, width, _channels) = (out_shape[0], out_shape[1], out_shape[2]);

    for placed_obj in placed_objects {
        let (x_min_f, y_min_f, _, _) = placed_obj.bbox;
        let x_min = x_min_f.floor().max(0.0) as usize;
        let y_min = y_min_f.floor().max(0.0) as usize;

        if x_min >= width || y_min >= height {
            continue;
        }

        let mask_shape = placed_obj.mask.shape();
        let patch_height = mask_shape[0];
        let patch_width = mask_shape[1];

        if patch_width == 0 || patch_height == 0 {
            continue;
        }

        let y_max = (y_min + patch_height).min(height);
        let x_max = (x_min + patch_width).min(width);

        let target_height = y_max.saturating_sub(y_min);
        let target_width = x_max.saturating_sub(x_min);

        if target_width == 0 || target_height == 0 {
            continue;
        }

        // Copy mask values where object exists
        for py in 0..target_height {
            for px in 0..target_width {
                let target_y = y_min + py;
                let target_x = x_min + px;

                if target_y >= height || target_x >= width {
                    continue;
                }

                let mask_value = placed_obj.mask[[py, px, 0]];
                if mask_value > 0 {
                    // Use the class_id as the mask value for this object
                    output_mask[[target_y, target_x, 0]] = (placed_obj.class_id as u8).min(255);
                }
            }
        }
    }
}

/// Generate axis-aligned bounding boxes along with rotation metadata.
///
/// Each entry is `[x_min, y_min, x_max, y_max, class_id, rotation_deg]`.
pub fn generate_output_bboxes_with_rotation(placed_objects: &[PlacedObject]) -> Vec<[f32; 6]> {
    placed_objects
        .iter()
        .map(|obj| {
            let (x_min, y_min, x_max, y_max) = obj.bbox;
            [
                x_min,
                y_min,
                x_max,
                y_max,
                obj.class_id as f32,
                obj.rotation,
            ]
        })
        .collect()
}
