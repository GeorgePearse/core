//! Affine transformation utilities for copy-paste augmentation.
use ndarray::Array3;
use rayon::prelude::*;
use std::f32::consts::PI;

/// Tolerance for floating-point comparison to avoid edge boundary artifacts during interpolation
pub const BOUNDARY_EPSILON: f32 = 1e-6;

/// Transform a patch using rotation and scaling with bilinear interpolation
///
/// # Arguments
/// * `patch` - The image patch to transform
/// * `mask` - The mask patch to transform
/// * `rotation` - Rotation angle in degrees
/// * `scale` - Scale factor
///
/// # Returns
/// Tuple of (transformed_image, transformed_mask, offset_x, offset_y)
/// where offset_x/offset_y are the displacement from the patch center
pub fn transform_patch(
    patch: &Array3<u8>,
    mask: &Array3<u8>,
    rotation: f32,
    scale: f32,
) -> (Array3<u8>, Array3<u8>, f32, f32) {
    let (height, width, channels) = (patch.shape()[0], patch.shape()[1], patch.shape()[2]);

    if height == 0 || width == 0 {
        return (patch.clone(), mask.clone(), 0.0, 0.0);
    }

    // Center of the patch
    let center_x = (width as f32) / 2.0;
    let center_y = (height as f32) / 2.0;

    // Convert rotation to radians
    let rad = rotation * PI / 180.0;
    let cos_a = rad.cos();
    let sin_a = rad.sin();

    // Calculate transformed corners relative to center
    let corners = [
        (0.0 - center_x, 0.0 - center_y),
        (width as f32 - center_x, 0.0 - center_y),
        (0.0 - center_x, height as f32 - center_y),
        (width as f32 - center_x, height as f32 - center_y),
    ];

    // Transform corners and calculate bbox in a single pass for efficiency
    let mut min_x = f32::INFINITY;
    let mut min_y = f32::INFINITY;
    let mut max_x = f32::NEG_INFINITY;
    let mut max_y = f32::NEG_INFINITY;

    for &(x, y) in &corners {
        let new_x = scale * (cos_a * x - sin_a * y);
        let new_y = scale * (sin_a * x + cos_a * y);
        min_x = min_x.min(new_x);
        max_x = max_x.max(new_x);
        min_y = min_y.min(new_y);
        max_y = max_y.max(new_y);
    }

    let new_width = ((max_x - min_x).ceil() as usize).max(1);
    let new_height = ((max_y - min_y).ceil() as usize).max(1);

    // Inverse transformation parameters
    let scale_inv = if scale > BOUNDARY_EPSILON {
        1.0 / scale
    } else {
        1.0
    };
    let cos_a_inv = cos_a;
    let sin_a_inv = -sin_a;

    // We process rows in parallel using Rayon
    // Create vectors of rows to allow parallel iteration and construction
    let rows: Vec<(Vec<u8>, Vec<u8>)> = (0..new_height)
        .into_par_iter()
        .map(|y| {
            let mut row_img = Vec::with_capacity(new_width * channels);
            let mut row_mask = Vec::with_capacity(new_width * channels);

            for x in 0..new_width {
                let out_x = (x as f32) + min_x;
                let out_y = (y as f32) + min_y;

                // Apply inverse transform to find source coordinates
                let dx = out_x;
                let dy = out_y;
                let src_x = scale_inv * (cos_a_inv * dx - sin_a_inv * dy) + center_x;
                let src_y = scale_inv * (sin_a_inv * dx + cos_a_inv * dy) + center_y;

                // Bilinear interpolation with boundary tolerance
                if src_x >= 0.0
                    && src_x < (width as f32 - BOUNDARY_EPSILON)
                    && src_y >= 0.0
                    && src_y < (height as f32 - BOUNDARY_EPSILON)
                {
                    let x0 = src_x.floor() as usize;
                    let y0 = src_y.floor() as usize;
                    let x1 = (x0 + 1).min(width - 1);
                    let y1 = (y0 + 1).min(height - 1);

                    let fx = src_x - x0 as f32;
                    let fy = src_y - y0 as f32;

                    for c in 0..channels {
                        let v00 = patch[[y0, x0, c]] as f32;
                        let v10 = patch[[y0, x1, c]] as f32;
                        let v01 = patch[[y1, x0, c]] as f32;
                        let v11 = patch[[y1, x1, c]] as f32;

                        let v0 = v00 * (1.0 - fx) + v10 * fx;
                        let v1 = v01 * (1.0 - fx) + v11 * fx;
                        let v = v0 * (1.0 - fy) + v1 * fy;

                        row_img.push(v.round() as u8);

                        // Same for mask
                        let m00 = mask[[y0, x0, c]] as f32;
                        let m10 = mask[[y0, x1, c]] as f32;
                        let m01 = mask[[y1, x0, c]] as f32;
                        let m11 = mask[[y1, x1, c]] as f32;

                        let m0 = m00 * (1.0 - fx) + m10 * fx;
                        let m1 = m01 * (1.0 - fx) + m11 * fx;
                        let m = m0 * (1.0 - fy) + m1 * fy;

                        row_mask.push((m.round() as u8).max(if m > 127.5 { 255 } else { 0 }));
                    }
                } else {
                    // Outside bounds - transparent/black
                    for _ in 0..channels {
                        row_img.push(0);
                        row_mask.push(0);
                    }
                }
            }
            (row_img, row_mask)
        })
        .collect();

    // Reassemble the rows into Array3
    let mut output_image = Array3::zeros((new_height, new_width, channels));
    let mut output_mask = Array3::zeros((new_height, new_width, channels));

    // This part is sequential but fast (memory copy)
    for (y, (row_img, row_mask)) in rows.into_iter().enumerate() {
        // We can't easily slice-assign Vec to ArrayViewMut, so we copy element-wise or use from_vec if careful
        // Manual copy is safe and relatively fast for these sizes
        let mut idx = 0;
        for x in 0..new_width {
            for c in 0..channels {
                output_image[[y, x, c]] = row_img[idx];
                output_mask[[y, x, c]] = row_mask[idx];
                idx += 1;
            }
        }
    }

    (output_image, output_mask, min_x, min_y)
}

/// Represents an affine transformation matrix and its parameters (Legacy/Future use)
#[derive(Clone, Debug)]
#[allow(dead_code)]
pub struct AffineTransform {
    /// 2x3 affine transformation matrix
    pub matrix: ndarray::Array2<f32>,
    pub rotation: f32,
    pub scale: f32,
    pub tx: f32,
    pub ty: f32,
}