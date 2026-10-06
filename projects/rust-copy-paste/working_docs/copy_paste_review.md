# Simple Copy-Paste Implementation Review

## API & Contract Gaps

- **✅ RESOLVED: Bounding boxes drop caller data (`src/lib.rs:226-249`)**
  **Issue:** `apply_to_bboxes` ignored the array that Albumentations passes in and only emitted metadata for the previously pasted objects stored in `last_placed`. As soon as you call the transform, every original bounding box was discarded.
  **Fix:** Modified `apply_to_bboxes` to merge original bboxes with newly placed object bboxes. Now starts with original bboxes and extends with new ones.
  **Resolution Date:** 2025-11-18

- **✅ RESOLVED: Stateful metadata cannot be safely paired with images (`src/lib.rs:218-249`)**
  **Issue:** Bounding box metadata lived in `self.last_placed` using `RefCell`, which is not thread-safe. In real training pipelines with concurrent transforms, this caused data corruption.
  **Fix:** Replaced `RefCell<Vec<PlacedObject>>` with `Arc<Mutex<Vec<PlacedObject>>>` for thread-safe shared state.
  **Resolution Date:** 2025-11-18

- **`use_random_background` is a no-op (`src/lib.rs:43-144`, `copy_paste/transform.py:25-105`)**  
  The configuration flag is surfaced everywhere (Rust struct, Python wrapper, docs) but never read when composing images—no alternate background is ever generated. Either remove the flag from the public API or implement the advertised behaviour (e.g., draw a background from a pool or fill with noise before compositing) so users are not misled.

- **✅ RESOLVED: Input validation only checks tensor rank (`src/lib.rs:151-199`, `src/objects.rs:44-65`)**
  **Issue:** `apply` only validated that image/mask arrays are 3-D but never checked that their height/width/channels match. This could cause panics or read garbage.
  **Fix:** Added comprehensive validation:
  - Dimensions must be positive (> 0)
  - Image must have 3 channels (BGR format)
  - Masks must have 1 channel
  - Image and mask dimensions must match
  - Python side validates image_width/height > 0 and object_counts are non-negative integers
  **Resolution Date:** 2025-11-18

- **Documented `object_counts` contract does not match Rust (`copy_paste/transform.py:25-70`, `src/lib.rs:22-110`)**  
  The Python docstring and docs instruct users to pass a `dict[str, int]`, but `AugmentationConfig` expects `HashMap<u32, u32>`. Passing names will raise a PyO3 type error, and nothing converts from class names to numeric IDs. Update the API to accept the documented shape (e.g., string keys converted via a map) or correct the documentation/tests so the requirement on numeric IDs is clear.

## Mask & Object Processing Weaknesses

- **Mask resampling uses bilinear interpolation and ad-hoc thresholding (`src/objects.rs:361-410`)**  
  Masks represent discrete class IDs, but `transform_patch` treats them like images: it bilinearly interpolates values, rounds them, and then does a `max(value, 255-or-0)` hack. This expands masks, creates fractional halos, and blurs class boundaries before `update_output_mask` writes class IDs. Rewrite this path to use nearest-neighbour sampling for masks, keep a single-channel mask instead of cloning three channels, and carry a boolean/alpha map separate from RGB pixels.

- **Class IDs are truncated to 8-bit (`src/objects.rs:146-188`, `src/objects.rs:763-808`)**  
  Object extraction counts classes with a `[0; 256]` array and `update_output_mask` casts every class ID to `u8`. Any dataset with ≥256 classes or COCO-style category IDs >255 will be truncated silently. Rework this to track counts in a `HashMap<u32, usize>` and store the mask in a `u16`/`u32` ndarray (or at least remap IDs before writing them).

- **Axis-aligned collision detection ignores rotation and is hard-coded (`src/lib.rs:194-211`, `src/objects.rs:481-659`)**  
  The collision threshold (0.01 IoU) is baked into `apply`, and IoU is computed on axis-aligned boxes even though patches can be rotated. That lets rotated objects overlap heavily while the IoU remains low. Expose the threshold through `AugmentationConfig` and consider using the actual rotated polygon or mask coverage for collision checks.

- **Generated bbox metadata is only axis-aligned (`src/objects.rs:738-755`)**  
  `generate_output_bboxes_with_rotation` returns axis-aligned coordinates plus a rotation angle. Consumers that expect tight rotated boxes still have to reconstruct polygons manually. If rotated boxes are part of the contract, emit corner coordinates directly so downstream code can use them without guesswork.

## Performance & Maintainability

- **Flood fill and patch extraction duplicate work per channel (`src/objects.rs:122-208`)**  
  Every time an object is extracted, the code copies all three RGB channels and three identical mask channels while also running a scalar flood fill over the entire mask. Rewriting this stage around `imageproc::connected_components` or `ndarray` boolean masks (with a single-channel mask buffer) would dramatically reduce allocations and simplify the logic.

- **`last_placed` reuse makes fuzzing/testing brittle (`src/lib.rs:218-249`)**  
  Because metadata accrues globally, a failed augmentation leaves stale placements in `last_placed`. A subsequent `apply_to_bboxes` call will happily report those stale boxes even though the image was returned untouched. Clearing `last_placed` on error and returning metadata atomically would remove this footgun.

