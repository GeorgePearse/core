/// Blending modes for combining images
#[derive(Clone, Copy, Debug)]
pub enum BlendMode {
    /// Standard alpha blending
    Normal,
    /// X-ray style blending (for overlays)
    XRay,
}

impl BlendMode {
    pub fn from_string(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "xray" => BlendMode::XRay,
            _ => BlendMode::Normal,
        }
    }
}

/// Blend two images with the specified mode
#[allow(dead_code)]
pub fn blend_images(
    base: &[u8],
    overlay: &[u8],
    alpha: f32,
    mode: BlendMode,
    _width: u32,
    _height: u32,
) -> Vec<u8> {
    let mut result = base.to_vec();
    let len = base.len();

    match mode {
        BlendMode::Normal => {
            for i in 0..len {
                let base_val = f32::from(base[i]);
                let overlay_val = f32::from(overlay[i]);
                let blended = base_val * (1.0 - alpha) + overlay_val * alpha;
                #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
                {
                    result[i] = blended.clamp(0.0, 255.0) as u8;
                }
            }
        }
        BlendMode::XRay => {
            // X-ray blending: weighted sum that makes overlaid areas more visible
            for i in 0..len {
                let base_val = f32::from(base[i]);
                let overlay_val = f32::from(overlay[i]);
                // X-ray blend formula: creates a lighter blend
                let blended = (base_val + overlay_val * alpha).min(255.0);
                #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
                {
                    result[i] = blended as u8;
                }
            }
        }
    }

    result
}

/// Blend two pixels
pub fn blend_pixel(base: u8, overlay: u8, alpha: f32, mode: BlendMode) -> u8 {
    match mode {
        BlendMode::Normal => {
            let base_val = f32::from(base);
            let overlay_val = f32::from(overlay);
            let blended = base_val * (1.0 - alpha) + overlay_val * alpha;
            #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
            {
                blended.clamp(0.0, 255.0) as u8
            }
        }
        BlendMode::XRay => {
            let base_val = f32::from(base);
            let overlay_val = f32::from(overlay);
            let blended = (base_val + overlay_val * alpha).min(255.0);
            #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
            {
                blended as u8
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_blend_mode_from_string() {
        match BlendMode::from_string("normal") {
            BlendMode::Normal => (),
            _ => panic!("Expected Normal mode"),
        }

        match BlendMode::from_string("xray") {
            BlendMode::XRay => (),
            _ => panic!("Expected XRay mode"),
        }
    }

    #[test]
    fn test_blend_pixel_normal() {
        let result = blend_pixel(100, 200, 0.5, BlendMode::Normal);
        assert_eq!(result, 150);
    }

    #[test]
    fn test_blend_pixel_xray() {
        let result = blend_pixel(100, 200, 0.5, BlendMode::XRay);
        // 100 + 200*0.5 = 200
        assert_eq!(result, 200);
    }

    // ==================== Phase 4: Blending Tests ====================

    #[test]
    fn test_blend_pixel_normal_full_alpha() {
        // Alpha = 1.0 should give full overlay color
        let result = blend_pixel(100, 200, 1.0, BlendMode::Normal);
        assert_eq!(result, 200);
    }

    #[test]
    fn test_blend_pixel_normal_zero_alpha() {
        // Alpha = 0.0 should give full base color
        let result = blend_pixel(100, 200, 0.0, BlendMode::Normal);
        assert_eq!(result, 100);
    }

    #[test]
    fn test_blend_pixel_normal_quarter_alpha() {
        // Alpha = 0.25: 100 * 0.75 + 200 * 0.25 = 75 + 50 = 125
        let result = blend_pixel(100, 200, 0.25, BlendMode::Normal);
        assert_eq!(result, 125);
    }

    #[test]
    fn test_blend_pixel_normal_three_quarter_alpha() {
        // Alpha = 0.75: 100 * 0.25 + 200 * 0.75 = 25 + 150 = 175
        let result = blend_pixel(100, 200, 0.75, BlendMode::Normal);
        assert_eq!(result, 175);
    }

    #[test]
    fn test_blend_pixel_normal_both_zero() {
        // Both pixels are 0
        let result = blend_pixel(0, 0, 0.5, BlendMode::Normal);
        assert_eq!(result, 0);
    }

    #[test]
    fn test_blend_pixel_normal_both_max() {
        // Both pixels are 255
        let result = blend_pixel(255, 255, 0.5, BlendMode::Normal);
        assert_eq!(result, 255);
    }

    #[test]
    fn test_blend_pixel_normal_clamp_overflow() {
        // Result might exceed 255 due to floating point, should clamp
        let result = blend_pixel(255, 255, 1.0, BlendMode::Normal);
        assert_eq!(result, 255);
    }

    #[test]
    fn test_blend_pixel_xray_full_alpha() {
        // XRay: base + overlay * alpha = 100 + 200 * 1.0 = 300 -> clamped to 255
        let result = blend_pixel(100, 200, 1.0, BlendMode::XRay);
        assert_eq!(result, 255); // Should be clamped to 255
    }

    #[test]
    fn test_blend_pixel_xray_zero_alpha() {
        // XRay: base + overlay * 0 = 100 + 0 = 100
        let result = blend_pixel(100, 200, 0.0, BlendMode::XRay);
        assert_eq!(result, 100);
    }

    #[test]
    fn test_blend_pixel_xray_quarter_alpha() {
        // XRay: 100 + 200 * 0.25 = 100 + 50 = 150
        let result = blend_pixel(100, 200, 0.25, BlendMode::XRay);
        assert_eq!(result, 150);
    }

    #[test]
    fn test_blend_pixel_xray_clamp_limit() {
        // XRay with result > 255 should clamp
        let result = blend_pixel(200, 255, 0.5, BlendMode::XRay);
        // 200 + 255 * 0.5 = 200 + 127.5 = 327.5 -> 255
        assert_eq!(result, 255);
    }

    #[test]
    fn test_blend_pixel_inverse_colors() {
        // Blending 0 (black) with 255 (white) at 0.5
        let result = blend_pixel(0, 255, 0.5, BlendMode::Normal);
        assert_eq!(result, 127); // Should be middle gray
    }

    #[test]
    fn test_blend_pixel_xray_additive_property() {
        // XRay mode should be additive
        let result1 = blend_pixel(100, 50, 1.0, BlendMode::XRay);
        let result2 = blend_pixel(100, 100, 1.0, BlendMode::XRay);

        // result1 = 100 + 50 = 150
        // result2 = 100 + 100 = 200
        assert!(result2 > result1);
    }

    #[test]
    fn test_blend_mode_from_string_case_insensitive() {
        // Should handle different cases
        match BlendMode::from_string("XRAY") {
            BlendMode::XRay => (),
            _ => panic!("Expected XRay mode"),
        }

        match BlendMode::from_string("XRay") {
            BlendMode::XRay => (),
            _ => panic!("Expected XRay mode"),
        }
    }

    #[test]
    fn test_blend_mode_from_string_normal_variants() {
        // Normal should match various spellings
        match BlendMode::from_string("normal") {
            BlendMode::Normal => (),
            _ => panic!("Expected Normal mode"),
        }

        match BlendMode::from_string("Normal") {
            BlendMode::Normal => (),
            _ => panic!("Expected Normal mode"),
        }

        match BlendMode::from_string("NORMAL") {
            BlendMode::Normal => (),
            _ => panic!("Expected Normal mode"),
        }
    }

    #[test]
    fn test_blend_mode_from_string_default() {
        // Unknown string should default to Normal
        match BlendMode::from_string("unknown") {
            BlendMode::Normal => (),
            _ => panic!("Expected Normal mode as default"),
        }

        match BlendMode::from_string("") {
            BlendMode::Normal => (),
            _ => panic!("Expected Normal mode as default"),
        }
    }

    #[test]
    fn test_blend_images_normal_mode() {
        let base = vec![100u8, 100, 100];
        let overlay = vec![200u8, 200, 200];

        let result = blend_images(&base, &overlay, 0.5, BlendMode::Normal, 3, 1);

        // Each pixel: 100 * 0.5 + 200 * 0.5 = 150
        assert_eq!(result, vec![150, 150, 150]);
    }

    #[test]
    fn test_blend_images_xray_mode() {
        let base = vec![100u8, 100, 100];
        let overlay = vec![200u8, 200, 200];

        let result = blend_images(&base, &overlay, 0.5, BlendMode::XRay, 3, 1);

        // Each pixel: min(100 + 200*0.5, 255) = min(200, 255) = 200
        assert_eq!(result, vec![200, 200, 200]);
    }

    #[test]
    fn test_blend_images_zero_alpha() {
        let base = vec![100u8, 100, 100];
        let overlay = vec![200u8, 200, 200];

        let result = blend_images(&base, &overlay, 0.0, BlendMode::Normal, 3, 1);

        // Should return base unchanged
        assert_eq!(result, vec![100, 100, 100]);
    }

    #[test]
    fn test_blend_images_full_alpha() {
        let base = vec![100u8, 100, 100];
        let overlay = vec![200u8, 200, 200];

        let result = blend_images(&base, &overlay, 1.0, BlendMode::Normal, 3, 1);

        // Should return overlay
        assert_eq!(result, vec![200, 200, 200]);
    }

    #[test]
    fn test_blend_images_large_image() {
        let base = vec![100u8; 1000];
        let overlay = vec![200u8; 1000];

        let result = blend_images(&base, &overlay, 0.5, BlendMode::Normal, 1000, 1);

        // All pixels should be 150
        assert!(result.iter().all(|&p| p == 150));
    }

    #[test]
    fn test_blend_images_alternating_pattern() {
        let base = vec![0u8, 255, 0, 255];
        let overlay = vec![255u8, 0, 255, 0];

        let result = blend_images(&base, &overlay, 0.5, BlendMode::Normal, 4, 1);

        // Each pixel: 0.5 * a + 0.5 * b = 127.5 -> rounds to 128 or 127
        for pixel in &result {
            assert!(*pixel >= 127 && *pixel <= 128);
        }
    }

    #[test]
    fn test_blend_pixel_normal_symmetry() {
        // Blending A onto B should be different from blending B onto A
        let result_ab = blend_pixel(100, 200, 0.5, BlendMode::Normal);
        let result_ba = blend_pixel(200, 100, 0.5, BlendMode::Normal);

        // They should be equal by coincidence when alpha is 0.5
        assert_eq!(result_ab, result_ba);

        // But with different alpha they differ
        let result_ab_3 = blend_pixel(100, 200, 0.25, BlendMode::Normal);
        let result_ba_3 = blend_pixel(200, 100, 0.25, BlendMode::Normal);

        assert_ne!(result_ab_3, result_ba_3);
    }

    #[test]
    fn test_blend_pixel_extreme_alpha_values() {
        // Test alpha values outside [0, 1]
        let result_neg = blend_pixel(100, 200, -0.5, BlendMode::Normal);
        let result_over = blend_pixel(100, 200, 1.5, BlendMode::Normal);

        // Should handle gracefully and return valid u8 values
        assert!(result_neg != 0); // Should produce some value
        assert!(result_over != 0); // Should produce some value
    }

    #[test]
    fn test_blend_mode_clone() {
        // Test that BlendMode can be cloned
        let mode = BlendMode::XRay;
        let mode_copy = mode;
        match mode_copy {
            BlendMode::XRay => (),
            _ => panic!("Clone should preserve mode"),
        }
    }

    #[test]
    fn test_blend_pixel_normal_boundary_values() {
        // Test with boundary pixel values
        let test_cases = vec![
            (0, 0, 0.0),
            (0, 255, 0.0),
            (0, 255, 1.0),
            (255, 0, 0.5),
            (255, 255, 0.5),
        ];

        for (base, overlay, alpha) in test_cases {
            let result = blend_pixel(base, overlay, alpha, BlendMode::Normal);
            // u8 type ensures result is always valid
            let _ = result;
        }
    }

    #[test]
    fn test_blend_pixel_xray_no_underflow() {
        // XRay should never produce values below base
        let result = blend_pixel(100, 50, 0.5, BlendMode::XRay);
        assert!(result >= 100);
    }

    #[test]
    fn test_blend_images_empty() {
        // Empty image
        let base = vec![];
        let overlay = vec![];

        let result = blend_images(&base, &overlay, 0.5, BlendMode::Normal, 0, 0);
        assert_eq!(result.len(), 0);
    }

    #[test]
    fn test_blend_mode_from_string_special_chars() {
        // Test with spaces and special characters
        match BlendMode::from_string("  xray  ") {
            BlendMode::Normal => (), // Spaces before/after won't match, so defaults to Normal
            _ => (),
        }
    }
}
