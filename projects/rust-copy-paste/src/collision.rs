//! Collision detection and bounding box operations for copy-paste augmentation.
//!
//! This module provides utilities for bounding box operations including:
//! - IoU (Intersection over Union) calculation
//! - Collision detection between placed objects
//! - Bounding box clipping to image boundaries
//! - Helper functions for intersection and union boxes (used in tests and may be needed for future features)

/// Bounding box represented as (x_min, y_min, x_max, y_max)
pub type BBox = (f32, f32, f32, f32);

/// Calculate Intersection over Union (IoU) between two bounding boxes
#[allow(clippy::similar_names)]
pub fn calculate_iou(bbox1: BBox, bbox2: BBox) -> f32 {
    let (x1_min, y1_min, x1_max, y1_max) = bbox1;
    let (x2_min, y2_min, x2_max, y2_max) = bbox2;

    // Calculate intersection area
    let inter_x_min = x1_min.max(x2_min);
    let inter_y_min = y1_min.max(y2_min);
    let inter_x_max = x1_max.min(x2_max);
    let inter_y_max = y1_max.min(y2_max);

    if inter_x_max <= inter_x_min || inter_y_max <= inter_y_min {
        return 0.0;
    }

    let inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min);

    // Calculate union area
    let area1 = (x1_max - x1_min) * (y1_max - y1_min);
    let area2 = (x2_max - x2_min) * (y2_max - y2_min);
    let union_area = area1 + area2 - inter_area;

    if union_area < 1e-10 {
        return 0.0;
    }

    inter_area / union_area
}

/// Check if two bounding boxes have collision (IoU > threshold)
pub fn check_iou_collision(bbox1: BBox, bbox2: BBox, threshold: f32) -> bool {
    calculate_iou(bbox1, bbox2) > threshold
}

/// Get the intersection box of two bounding boxes
#[allow(dead_code, clippy::similar_names)]
pub fn get_intersection_box(bbox1: BBox, bbox2: BBox) -> Option<BBox> {
    let (x1_min, y1_min, x1_max, y1_max) = bbox1;
    let (x2_min, y2_min, x2_max, y2_max) = bbox2;

    let inter_x_min = x1_min.max(x2_min);
    let inter_y_min = y1_min.max(y2_min);
    let inter_x_max = x1_max.min(x2_max);
    let inter_y_max = y1_max.min(y2_max);

    if inter_x_max > inter_x_min && inter_y_max > inter_y_min {
        Some((inter_x_min, inter_y_min, inter_x_max, inter_y_max))
    } else {
        None
    }
}

/// Get the union (bounding box that contains both boxes)
#[allow(dead_code)]
pub fn get_union_box(bbox1: BBox, bbox2: BBox) -> BBox {
    let (x1_min, y1_min, x1_max, y1_max) = bbox1;
    let (x2_min, y2_min, x2_max, y2_max) = bbox2;

    (
        x1_min.min(x2_min),
        y1_min.min(y2_min),
        x1_max.max(x2_max),
        y1_max.max(y2_max),
    )
}

/// Clip bounding box to be within image bounds
pub fn clip_bbox_to_image(bbox: BBox, image_width: u32, image_height: u32) -> BBox {
    let (mut x_min, mut y_min, mut x_max, mut y_max) = bbox;

    x_min = x_min.max(0.0).min(image_width as f32);
    y_min = y_min.max(0.0).min(image_height as f32);
    x_max = x_max.max(0.0).min(image_width as f32);
    y_max = y_max.max(0.0).min(image_height as f32);

    (x_min, y_min, x_max, y_max)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_iou_identical_boxes() {
        let bbox = (0.0, 0.0, 10.0, 10.0);
        let iou = calculate_iou(bbox, bbox);
        assert!((iou - 1.0).abs() < 1e-5);
    }

    #[test]
    fn test_iou_no_overlap() {
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (20.0, 20.0, 30.0, 30.0);
        let iou = calculate_iou(bbox1, bbox2);
        assert!(iou.abs() < 1e-5);
    }

    #[test]
    fn test_iou_partial_overlap() {
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (5.0, 5.0, 15.0, 15.0);
        let iou = calculate_iou(bbox1, bbox2);
        // Intersection area = 5*5 = 25
        // Union area = 100 + 100 - 25 = 175
        // IoU = 25/175 ≈ 0.1429
        assert!((iou - (25.0 / 175.0)).abs() < 1e-5);
    }

    #[test]
    fn test_collision_detection() {
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (5.0, 5.0, 15.0, 15.0);
        assert!(check_iou_collision(bbox1, bbox2, 0.1));
        assert!(!check_iou_collision(bbox1, bbox2, 0.2));
    }

    #[test]
    fn test_clip_bbox() {
        let bbox = (-5.0, -5.0, 105.0, 105.0);
        let clipped = clip_bbox_to_image(bbox, 100, 100);
        assert_eq!(clipped, (0.0, 0.0, 100.0, 100.0));
    }

    // ==================== Phase 3: Collision & Boundary Tests ====================

    #[test]
    fn test_iou_degenerate_box_zero_area() {
        // Box with zero area (x_min == x_max)
        let bbox1 = (5.0, 5.0, 5.0, 10.0);
        let bbox2 = (0.0, 0.0, 10.0, 10.0);

        let iou = calculate_iou(bbox1, bbox2);
        // Zero-area box should have IoU = 0
        assert!(iou.abs() < 1e-5);
    }

    #[test]
    fn test_iou_both_degenerate_boxes() {
        // Both boxes have zero area
        let bbox1 = (5.0, 5.0, 5.0, 5.0);
        let bbox2 = (5.0, 5.0, 5.0, 5.0);

        let iou = calculate_iou(bbox1, bbox2);
        // IoU of two degenerate boxes should be 0
        assert!(iou.abs() < 1e-5);
    }

    #[test]
    fn test_iou_floating_point_precision() {
        // Boxes that differ by tiny floating point amount
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (0.0000001, 0.0000001, 10.0000001, 10.0000001);

        let iou1 = calculate_iou(bbox1, bbox1);
        let iou2 = calculate_iou(bbox1, bbox2);

        // Should be very close to 1.0
        assert!((iou1 - 1.0).abs() < 1e-5);
        assert!(iou2 > 0.999);
    }

    #[test]
    fn test_iou_touching_edges() {
        // Boxes touching at edges but not overlapping
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (10.0, 0.0, 20.0, 10.0);

        let iou = calculate_iou(bbox1, bbox2);
        // Touching edges but no overlap = IoU = 0
        assert!(iou.abs() < 1e-5);
    }

    #[test]
    fn test_iou_touching_corners() {
        // Boxes touching at corner
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (10.0, 10.0, 20.0, 20.0);

        let iou = calculate_iou(bbox1, bbox2);
        // Corner touching = no overlap
        assert!(iou.abs() < 1e-5);
    }

    #[test]
    fn test_iou_one_box_inside_another() {
        // Box2 is completely inside Box1
        let bbox1 = (0.0, 0.0, 100.0, 100.0);
        let bbox2 = (10.0, 10.0, 20.0, 20.0);

        let iou = calculate_iou(bbox1, bbox2);
        // Intersection = area of bbox2 = 100
        // Union = area of bbox1 = 10000
        // IoU = 100/10000 = 0.01
        assert!((iou - 0.01).abs() < 1e-5);
    }

    #[test]
    fn test_iou_symmetric() {
        // IoU(A, B) should equal IoU(B, A)
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (5.0, 5.0, 15.0, 15.0);

        let iou_12 = calculate_iou(bbox1, bbox2);
        let iou_21 = calculate_iou(bbox2, bbox1);

        assert!((iou_12 - iou_21).abs() < 1e-5);
    }

    #[test]
    fn test_iou_very_small_boxes() {
        // Very small boxes with small overlap
        let bbox1 = (0.0, 0.0, 0.1, 0.1);
        let bbox2 = (0.05, 0.05, 0.15, 0.15);

        let iou = calculate_iou(bbox1, bbox2);
        // Should be valid IoU
        assert!(iou >= 0.0 && iou <= 1.0);
    }

    #[test]
    fn test_iou_very_large_boxes() {
        // Very large boxes
        let bbox1 = (0.0, 0.0, 10000.0, 10000.0);
        let bbox2 = (5000.0, 5000.0, 15000.0, 15000.0);

        let iou = calculate_iou(bbox1, bbox2);
        assert!(iou >= 0.0 && iou <= 1.0);
    }

    #[test]
    fn test_collision_detection_exact_threshold() {
        // Test at exact threshold boundary
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (5.0, 5.0, 15.0, 15.0);

        let iou = calculate_iou(bbox1, bbox2);
        // Should not collide at exact threshold
        assert!(!check_iou_collision(bbox1, bbox2, iou));
        // Should collide just below threshold
        assert!(check_iou_collision(bbox1, bbox2, iou - 0.001));
    }

    #[test]
    fn test_clip_bbox_no_clipping_needed() {
        // BBox completely within image
        let bbox = (10.0, 10.0, 90.0, 90.0);
        let clipped = clip_bbox_to_image(bbox, 100, 100);
        assert_eq!(clipped, bbox);
    }

    #[test]
    fn test_clip_bbox_negative_coordinates() {
        // BBox with negative coordinates
        let bbox = (-50.0, -50.0, 50.0, 50.0);
        let clipped = clip_bbox_to_image(bbox, 100, 100);
        assert_eq!(clipped, (0.0, 0.0, 50.0, 50.0));
    }

    #[test]
    fn test_clip_bbox_completely_outside_left() {
        // BBox completely outside to the left
        let bbox = (-100.0, 10.0, -50.0, 50.0);
        let clipped = clip_bbox_to_image(bbox, 100, 100);
        assert_eq!(clipped, (0.0, 10.0, 0.0, 50.0));
    }

    #[test]
    fn test_clip_bbox_completely_outside_top() {
        // BBox completely outside above
        let bbox = (10.0, -100.0, 50.0, -50.0);
        let clipped = clip_bbox_to_image(bbox, 100, 100);
        assert_eq!(clipped, (10.0, 0.0, 50.0, 0.0));
    }

    #[test]
    fn test_clip_bbox_completely_outside_right() {
        // BBox completely outside to the right
        let bbox = (150.0, 10.0, 200.0, 50.0);
        let clipped = clip_bbox_to_image(bbox, 100, 100);
        assert_eq!(clipped, (100.0, 10.0, 100.0, 50.0));
    }

    #[test]
    fn test_clip_bbox_completely_outside_bottom() {
        // BBox completely outside below
        let bbox = (10.0, 150.0, 50.0, 200.0);
        let clipped = clip_bbox_to_image(bbox, 100, 100);
        assert_eq!(clipped, (10.0, 100.0, 50.0, 100.0));
    }

    #[test]
    fn test_clip_bbox_small_image() {
        // BBox clipping on very small image
        let bbox = (-10.0, -10.0, 30.0, 30.0);
        let clipped = clip_bbox_to_image(bbox, 10, 10);
        assert_eq!(clipped, (0.0, 0.0, 10.0, 10.0));
    }

    #[test]
    fn test_clip_bbox_large_coordinates() {
        // BBox with large coordinates
        let bbox = (1000.0, 2000.0, 3000.0, 4000.0);
        let clipped = clip_bbox_to_image(bbox, 2500, 2500);
        assert_eq!(clipped, (1000.0, 2000.0, 2500.0, 2500.0));
    }

    #[test]
    fn test_iou_small_percentage_overlap() {
        // Very small percentage overlap
        let bbox1 = (0.0, 0.0, 1000.0, 1000.0);
        let bbox2 = (999.0, 999.0, 1001.0, 1001.0);

        let iou = calculate_iou(bbox1, bbox2);
        // Should be very small IoU
        assert!(iou > 0.0);
        assert!(iou < 0.001);
    }

    #[test]
    fn test_iou_50_percent_overlap() {
        // 50% overlap (corner to corner)
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (5.0, 5.0, 15.0, 15.0);

        let iou = calculate_iou(bbox1, bbox2);
        // Intersection: 5x5 = 25
        // Union: 100 + 100 - 25 = 175
        // IoU = 25/175 ≈ 0.1429
        assert!((iou - (25.0 / 175.0)).abs() < 1e-5);
    }

    #[test]
    fn test_get_intersection_box_valid() {
        // Test get_intersection_box function
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (5.0, 5.0, 15.0, 15.0);

        let inter = get_intersection_box(bbox1, bbox2);
        assert_eq!(inter, Some((5.0, 5.0, 10.0, 10.0)));
    }

    #[test]
    fn test_get_intersection_box_no_overlap() {
        // No overlapping region
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (20.0, 20.0, 30.0, 30.0);

        let inter = get_intersection_box(bbox1, bbox2);
        assert_eq!(inter, None);
    }

    #[test]
    fn test_get_intersection_box_edge_touching() {
        // Boxes touching at edge
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (10.0, 0.0, 20.0, 10.0);

        let inter = get_intersection_box(bbox1, bbox2);
        assert_eq!(inter, None);
    }

    #[test]
    fn test_get_union_box() {
        // Test get_union_box function
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (5.0, 5.0, 15.0, 15.0);

        let union = get_union_box(bbox1, bbox2);
        assert_eq!(union, (0.0, 0.0, 15.0, 15.0));
    }

    #[test]
    fn test_get_union_box_with_negative_coords() {
        // Union with negative coordinates
        let bbox1 = (-10.0, -10.0, 10.0, 10.0);
        let bbox2 = (0.0, 0.0, 20.0, 20.0);

        let union = get_union_box(bbox1, bbox2);
        assert_eq!(union, (-10.0, -10.0, 20.0, 20.0));
    }

    #[test]
    fn test_collision_with_zero_threshold() {
        // Zero threshold means even tiny overlap is collision
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (9.99, 9.99, 20.0, 20.0);

        let has_collision = check_iou_collision(bbox1, bbox2, 0.0);
        // Should have collision with threshold=0
        assert!(has_collision);
    }

    #[test]
    fn test_collision_with_high_threshold() {
        // High threshold (0.9) requires significant overlap
        let bbox1 = (0.0, 0.0, 10.0, 10.0);
        let bbox2 = (5.0, 5.0, 15.0, 15.0);

        let has_collision = check_iou_collision(bbox1, bbox2, 0.9);
        // Should not have collision (IoU ~ 0.14 < 0.9)
        assert!(!has_collision);
    }

    #[test]
    fn test_clip_bbox_inverted_coordinates() {
        // BBox with min > max (shouldn't happen but test for safety)
        let bbox = (20.0, 20.0, 10.0, 10.0);
        let clipped = clip_bbox_to_image(bbox, 100, 100);
        // Should handle gracefully
        assert!(clipped.0 >= 0.0);
        assert!(clipped.1 >= 0.0);
    }

    #[test]
    fn test_iou_identical_very_small_boxes() {
        // Identical very small boxes
        let bbox = (0.0, 0.0, 0.01, 0.01);
        let iou = calculate_iou(bbox, bbox);
        assert!((iou - 1.0).abs() < 1e-5);
    }

    #[test]
    fn test_collision_reflexive() {
        // A box colliding with itself
        let bbox = (10.0, 10.0, 50.0, 50.0);
        assert!(check_iou_collision(bbox, bbox, 0.0));
    }
}
