import numpy as np
from typing import List, Tuple, Optional, Dict

class CameraTracker:
    """
    Computes smooth 9:16 pan & scan trajectories with Deadzone,
    Exponential Moving Average (EMA), and edge clamping.
    """

    SENSITIVITY_CONFIGS = {
        "Lenta": {"alpha": 0.06, "deadzone": 70.0, "smooth_radius": 15},
        "Padrão": {"alpha": 0.14, "deadzone": 45.0, "smooth_radius": 8},
        "Rápida": {"alpha": 0.28, "deadzone": 22.0, "smooth_radius": 4},
    }

    def __init__(self, orig_width: int, orig_height: int, sensitivity: str = "Padrão"):
        self.orig_w = orig_width
        self.orig_h = orig_height
        self.sensitivity = sensitivity
        self.config = self.SENSITIVITY_CONFIGS.get(sensitivity, self.SENSITIVITY_CONFIGS["Padrão"])

        # 9:16 crop window dimensions
        self.crop_w = int(round(self.orig_h * 9.0 / 16.0))
        if self.crop_w % 2 != 0:
            self.crop_w += 1
        self.crop_h = self.orig_h
        # Ensure crop width does not exceed original video width
        if self.crop_w > self.orig_w:
            self.crop_w = self.orig_w

    def set_sensitivity(self, sensitivity: str):
        self.sensitivity = sensitivity
        self.config = self.SENSITIVITY_CONFIGS.get(sensitivity, self.SENSITIVITY_CONFIGS["Padrão"])

    def build_trajectory(
        self,
        sampled_detections: Dict[int, float],
        total_frames: int,
        default_cx: Optional[float] = None
    ) -> np.ndarray:
        """
        Takes sparse frame detections {frame_index: face_cx} and builds a complete,
        smooth per-frame trajectory of camera center X coordinates.
        """
        if default_cx is None:
            default_cx = self.orig_w / 2.0

        if total_frames <= 0:
            return np.array([default_cx])

        # 1. Fill dense raw points
        raw_x = np.full(total_frames, np.nan, dtype=np.float64)
        for frame_idx, cx in sampled_detections.items():
            if 0 <= frame_idx < total_frames and cx is not None:
                raw_x[frame_idx] = float(cx)

        # 2. Interpolate missing points with forward hold & center drift
        dense_x = np.zeros(total_frames, dtype=np.float64)
        last_known = default_cx
        frames_missing = 0

        # Find first known point
        known_indices = np.where(~np.isnan(raw_x))[0]
        if len(known_indices) > 0:
            first_idx = known_indices[0]
            last_known = raw_x[first_idx]
            dense_x[:first_idx] = last_known
        else:
            dense_x[:] = default_cx
            return self._apply_deadzone_and_smoothing(dense_x)

        for i in range(total_frames):
            if not np.isnan(raw_x[i]):
                last_known = raw_x[i]
                dense_x[i] = last_known
                frames_missing = 0
            else:
                frames_missing += 1
                if frames_missing > 45:
                    # After 1.5s of no faces, gently pull towards center
                    pull_factor = min(1.0, (frames_missing - 45) / 60.0)
                    dense_x[i] = (1.0 - pull_factor * 0.05) * last_known + (pull_factor * 0.05) * default_cx
                    last_known = dense_x[i]
                else:
                    dense_x[i] = last_known

        # 3. Apply Deadzone and Smoothing filter
        return self._apply_deadzone_and_smoothing(dense_x)

    def _apply_deadzone_and_smoothing(self, dense_x: np.ndarray) -> np.ndarray:
        total = len(dense_x)
        if total == 0:
            return dense_x

        alpha = self.config["alpha"]
        deadzone = self.config["deadzone"]
        radius = self.config["smooth_radius"]

        # Pass 1: Deadzone + Causal EMA
        cam_x = np.zeros(total, dtype=np.float64)
        cam_pos = dense_x[0]
        cam_x[0] = cam_pos

        for i in range(1, total):
            target = dense_x[i]
            diff = target - cam_pos

            if abs(diff) > deadzone:
                # Camera follows excess past deadzone with ease-in
                effective_target = target - np.sign(diff) * deadzone
                cam_pos += alpha * (effective_target - cam_pos)

            cam_x[i] = cam_pos

        # Pass 2: Non-causal Gaussian smoothing to eliminate micro-steps and lag
        if radius > 0 and total > radius * 2:
            kernel_size = radius * 2 + 1
            kernel = np.exp(-0.5 * (np.linspace(-2.5, 2.5, kernel_size) ** 2))
            kernel /= kernel.sum()
            padded = np.pad(cam_x, radius, mode='edge')
            smoothed = np.convolve(padded, kernel, mode='valid')
            cam_x = smoothed

        # Pass 3: Clamp inside frame bounds
        half_crop = self.crop_w / 2.0
        min_x = half_crop
        max_x = self.orig_w - half_crop
        cam_x = np.clip(cam_x, min_x, max_x)

        return cam_x

    def get_crop_box(self, cam_cx: float) -> Tuple[int, int, int, int]:
        """
        Given the camera center X, returns (x1, y1, w, h) clamped inside the frame.
        Guarantees even dimensions for video encoders.
        """
        x1 = int(round(cam_cx - (self.crop_w / 2.0)))
        x1 = max(0, min(x1, self.orig_w - self.crop_w))
        if x1 % 2 != 0:
            x1 = max(0, x1 - 1)

        return (x1, 0, self.crop_w, self.crop_h)

    def get_podcast_crop_boxes(
        self,
        cam_cx1: float,
        cam_cx2: Optional[float] = None
    ) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int, int]]:
        """
        For Split Screen / Podcast Mode (Top half and Bottom half).
        Target aspect ratio for each half is 9:8 (e.g. 1080x960).
        Returns ((x1, y1, w, h), (x2, y2, w, h)).
        """
        # Desired box aspect ratio: 9:8 (w / h = 9/8 = 1.125)
        # Using 85% of original height to capture head and shoulders
        box_h = int(round(self.orig_h * 0.88))
        if box_h % 2 != 0:
            box_h -= 1
        box_w = int(round(box_h * (9.0 / 8.0)))
        if box_w % 2 != 0:
            box_w += 1
        if box_w > self.orig_w:
            box_w = self.orig_w
            box_h = int(round(box_w * (8.0 / 9.0)))
            if box_h % 2 != 0:
                box_h -= 1

        y1 = max(0, int(round((self.orig_h - box_h) * 0.35))) # slightly top-aligned for heads

        # Box 1 (Subject A - Top)
        x1 = int(round(cam_cx1 - (box_w / 2.0)))
        x1 = max(0, min(x1, self.orig_w - box_w))
        if x1 % 2 != 0:
            x1 = max(0, x1 - 1)
        box1 = (x1, y1, box_w, box_h)

        # Box 2 (Subject B - Bottom)
        if cam_cx2 is not None:
            x2 = int(round(cam_cx2 - (box_w / 2.0)))
            x2 = max(0, min(x2, self.orig_w - box_w))
            if x2 % 2 != 0:
                x2 = max(0, x2 - 1)
            box2 = (x2, y1, box_w, box_h)
        else:
            # Fallback: if only 1 person, use wide or secondary framing
            box2 = box1

        return (box1, box2)
