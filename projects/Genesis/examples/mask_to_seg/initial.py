import cv2
import numpy as np
from typing import List


def run_conversion(mask: np.ndarray) -> List[np.ndarray]:
    """
    Converts a binary mask to a list of polygons.

    Args:
        mask: Binary mask (numpy array of shape (H, W), dtype=uint8/bool)
              where non-zero values are the object.

    Returns:
        List of polygons, where each polygon is an np.ndarray of shape (N, 2)
        representing (x, y) coordinates.
    """
    # Ensure mask is uint8
    if mask.dtype != np.uint8:
        mask = mask.astype(np.uint8)

    # Find contours
    # cv2.RETR_EXTERNAL retrieves only the extreme outer contours
    # cv2.CHAIN_APPROX_SIMPLE compresses horizontal, vertical, and diagonal segments
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    polygons = []
    for cnt in contours:
        if len(cnt) >= 3:  # A polygon must have at least 3 points
            # cnt has shape (N, 1, 2), we want (N, 2)
            polygon = cnt.squeeze(axis=1)
            polygons.append(polygon)

    return polygons
