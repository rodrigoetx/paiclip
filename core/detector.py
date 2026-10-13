import os
import sys
import urllib.request
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple
import cv2
import numpy as np

@dataclass
class FaceInfo:
    x: int
    y: int
    w: int
    h: int
    cx: float
    cy: float
    confidence: float
    area: float

class FaceDetector:
    """
    Robust Face Detector combining MediaPipe BlazeFace with OpenCV Haar Cascade fallback.
    """
    MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"

    def __init__(self, min_confidence: float = 0.5):
        self.min_confidence = min_confidence
        self.mp_detector = None
        self.cv_cascade = None
        self.use_mediapipe = False

        self._init_mediapipe()
        self._init_opencv_fallback()

    def _init_mediapipe(self):
        try:
            base_dir = Path(__file__).resolve().parent.parent
            model_dir = base_dir / "models"
            model_dir.mkdir(parents=True, exist_ok=True)
            model_path = model_dir / "blaze_face_short_range.tflite"

            if not model_path.exists() or model_path.stat().st_size < 10000:
                try:
                    urllib.request.urlretrieve(self.MODEL_URL, model_path)
                except Exception as e:
                    print(f"[Detector] Aviso: Não foi possível baixar modelo MediaPipe: {e}")

            if model_path.exists() and model_path.stat().st_size >= 10000:
                import mediapipe as mp
                from mediapipe.tasks import python
                from mediapipe.tasks.python import vision

                base_options = python.BaseOptions(model_asset_path=str(model_path.resolve()))
                options = vision.FaceDetectorOptions(
                    base_options=base_options,
                    min_detection_confidence=self.min_confidence
                )
                self.mp_detector = vision.FaceDetector.create_from_options(options)
                self.mp = mp
                self.use_mediapipe = True
                print("[Detector] MediaPipe FaceDetector carregado com sucesso.")
        except Exception as e:
            print(f"[Detector] MediaPipe indisponível ou falhou ao inicializar: {e}. Usando OpenCV Cascade.")
            self.use_mediapipe = False

    def _init_opencv_fallback(self):
        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            if os.path.exists(cascade_path):
                self.cv_cascade = cv2.CascadeClassifier(cascade_path)
        except Exception as e:
            print(f"[Detector] Erro ao carregar OpenCV Cascade: {e}")

    def detect(self, frame: np.ndarray) -> List[FaceInfo]:
        """
        Detects faces in BGR frame. Returns list of FaceInfo.
        """
        if frame is None or frame.size == 0:
            return []

        h_img, w_img = frame.shape[:2]

        if self.use_mediapipe and self.mp_detector is not None:
            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # Ensure contiguous memory buffer
                rgb_frame = np.ascontiguousarray(rgb_frame)
                mp_image = self.mp.Image(
                    image_format=self.mp.ImageFormat.SRGB,
                    data=rgb_frame
                )
                result = self.mp_detector.detect(mp_image)
                detections = []
                for det in result.detections:
                    bbox = det.bounding_box
                    x = max(0, int(bbox.origin_x))
                    y = max(0, int(bbox.origin_y))
                    w = min(w_img - x, int(bbox.width))
                    h = min(h_img - y, int(bbox.height))
                    if w > 10 and h > 10:
                        conf = det.categories[0].score if det.categories else 0.8
                        cx = x + w / 2.0
                        cy = y + h / 2.0
                        detections.append(FaceInfo(
                            x=x, y=y, w=w, h=h,
                            cx=cx, cy=cy,
                            confidence=conf,
                            area=float(w * h)
                        ))
                if detections:
                    return detections
            except Exception as e:
                # If MediaPipe throws unexpectedly, fallback to OpenCV
                pass

        # Fallback to OpenCV Haar Cascade
        if self.cv_cascade is not None:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                # Downscale for fast cascade detection if frame is large
                scale = 1.0
                if max(w_img, h_img) > 1280:
                    scale = 0.5
                    small_gray = cv2.resize(gray, (0, 0), fx=scale, fy=scale)
                else:
                    small_gray = gray

                faces = self.cv_cascade.detectMultiScale(
                    small_gray,
                    scaleFactor=1.15,
                    minNeighbors=4,
                    minSize=(int(30 * scale), int(30 * scale))
                )
                results = []
                for (x, y, w, h) in faces:
                    rx = int(x / scale)
                    ry = int(y / scale)
                    rw = int(w / scale)
                    rh = int(h / scale)
                    cx = rx + rw / 2.0
                    cy = ry + rh / 2.0
                    results.append(FaceInfo(
                        x=rx, y=ry, w=rw, h=rh,
                        cx=cx, cy=cy,
                        confidence=0.7,
                        area=float(rw * rh)
                    ))
                return results
            except Exception:
                pass

        return []

    def get_primary_face(self, faces: List[FaceInfo], prev_cx: Optional[float] = None, frame_width: Optional[int] = None) -> Optional[FaceInfo]:
        """
        Chooses the primary speaker face among detected faces.
        If prev_cx is provided, balances face size with distance to previous tracking point.
        """
        if not faces:
            return None
        if len(faces) == 1:
            return faces[0]

        if prev_cx is None:
            # Rank by area and centrality
            def score(f: FaceInfo):
                centrality = 1.0
                if frame_width:
                    dist = abs(f.cx - (frame_width / 2.0))
                    centrality = max(0.2, 1.0 - (dist / frame_width))
                return f.area * centrality

            return max(faces, key=score)

        # When tracking actively, penalize distance from prev_cx
        def track_score(f: FaceInfo):
            dist = abs(f.cx - prev_cx)
            norm_dist = dist / (frame_width if frame_width else 1920.0)
            # Distance penalty
            proximity_weight = np.exp(-4.0 * norm_dist)
            return (f.area ** 0.5) * proximity_weight

        return max(faces, key=track_score)

    def get_podcast_faces(self, faces: List[FaceInfo], frame_width: int) -> Tuple[Optional[FaceInfo], Optional[FaceInfo]]:
        """
        Returns (left_face, right_face) for 2-speaker podcast split screen.
        If only 1 face detected, returns (face, None).
        If 0 faces, returns (None, None).
        """
        if not faces:
            return (None, None)
        if len(faces) == 1:
            # One face: check which side it is on or treat as single
            return (faces[0], None)

        # Sort top 2 by area
        sorted_by_area = sorted(faces, key=lambda f: f.area, reverse=True)[:2]
        # Sort these 2 left-to-right by cx
        sorted_by_x = sorted(sorted_by_area, key=lambda f: f.cx)
        return (sorted_by_x[0], sorted_by_x[1])
