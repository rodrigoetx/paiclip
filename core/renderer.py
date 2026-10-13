import os
import sys
import time
import subprocess
from typing import Callable, Optional, Dict, Any, Tuple
import cv2
import numpy as np
from PIL import Image

from core.detector import FaceDetector
from core.tracker import CameraTracker
from utils.ffmpeg_check import get_ffmpeg_path, get_best_encoder

class VideoRenderer:
    """
    Layout engine and GPU-accelerated FFmpeg streaming renderer for Reframe-AI.
    Offers OpusClip-style 100% uncropped Fit with dynamic blurred background,
    Streamer split, and facial smart tracking.
    """

    TARGET_WIDTH = 1080
    TARGET_HEIGHT = 1920

    def __init__(self):
        self.detector = None

    def _ensure_detector(self):
        if self.detector is None:
            self.detector = FaceDetector(min_confidence=0.5)

    @staticmethod
    def get_video_info(video_path: str) -> Dict[str, Any]:
        """
        Extracts metadata from video file using OpenCV.
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Não foi possível abrir o arquivo de vídeo: {video_path}")

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        duration = (total_frames / fps) if fps > 0 else 0.0

        return {
            "width": w,
            "height": h,
            "fps": round(fps, 2),
            "total_frames": total_frames,
            "duration": duration,
            "duration_str": time.strftime('%H:%M:%S', time.gmtime(duration))
        }

    def detect_video_content_type(self, video_path: str, samples: int = 12) -> Dict[str, Any]:
        """
        Quickly samples frames across the video to detect if it's a Gameplay (no real face),
        Streamer (small facecam), or Talking Head (vlog/podcast).
        """
        self._ensure_detector()
        info = self.get_video_info(video_path)
        total = info["total_frames"]
        if total <= 0:
            return {"type": "gameplay", "recommended_mode": "opusclip_fit", "face_count": 0}

        step = max(1, total // samples)
        cap = cv2.VideoCapture(video_path)
        face_detections = 0
        small_corner_faces = 0

        for s in range(samples):
            f_idx = min(total - 1, s * step)
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            faces = self.detector.detect(frame)
            if faces:
                face_detections += 1
                for f in faces:
                    # Check if face is small (< 7% of screen width) and in corner
                    if (f.w / info["width"]) < 0.15:
                        small_corner_faces += 1

        cap.release()

        face_ratio = face_detections / max(1, samples)

        if face_ratio < 0.20:
            return {
                "type": "gameplay",
                "recommended_mode": "opusclip_fit",
                "face_ratio": face_ratio,
                "message": "🎮 Gameplay / Vídeo sem rosto detectado! Modo 'OpusClip Fit (100% Sem Cortes)' recomendado para preservar HUD, placar e laterais."
            }
        elif small_corner_faces >= 3 and face_ratio >= 0.40:
            return {
                "type": "streamer",
                "recommended_mode": "streamer_split",
                "face_ratio": face_ratio,
                "message": "🕹️ Gameplay com Webcam detectada! Layout Streamer Split recomendado."
            }
        else:
            return {
                "type": "talking_head",
                "recommended_mode": "smart_track",
                "face_ratio": face_ratio,
                "message": "🎯 Locutor principal detectado! Modo Smart Tracker ou Dividir Tela disponível."
            }

    # =========================================================================
    # Layout Processing Functions
    # =========================================================================

    @classmethod
    def apply_opusclip_fit(
        cls,
        frame: np.ndarray,
        target_w: int = 1080,
        target_h: int = 1920,
        position: str = "center"
    ) -> np.ndarray:
        """
        SIGNATURE OPUSCLIP / SHORTS LAYOUT:
        - Entire 16:9 frame is fitted into 1080px width (ZERO pixels cropped on sides!).
        - Background fills 1080x1920 with real-time Gaussian Bokeh and ambient vignette.
        - Drop shadow and sleek borders applied so gameplay HUD and action are 100% sharp.
        """
        h_orig, w_orig = frame.shape[:2]

        # 1. Background: scale to cover full vertical 9:16
        scale_bg = max(target_w / w_orig, target_h / h_orig)
        bg_w, bg_h = int(round(w_orig * scale_bg)), int(round(h_orig * scale_bg))

        crop_x = (bg_w - target_w) // 2
        crop_y = (bg_h - target_h) // 2

        bg_full = cv2.resize(frame, (bg_w, bg_h), interpolation=cv2.INTER_AREA)
        bg_cropped = bg_full[crop_y:crop_y + target_h, crop_x:crop_x + target_w]

        # Ultra-fast silky Bokeh blur (downscale -> blur -> upscale)
        small_w, small_h = target_w // 8, target_h // 8
        bg_small = cv2.resize(bg_cropped, (small_w, small_h), interpolation=cv2.INTER_LINEAR)
        bg_blur = cv2.GaussianBlur(bg_small, (31, 31), 0)
        bg_final = cv2.resize(bg_blur, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

        # Ambient Dark Vignette (48% brightness for high contrast with main video)
        canvas = cv2.addWeighted(bg_final, 0.48, np.zeros_like(bg_final), 0.52, 0)

        # 2. Foreground: 100% uncropped 16:9 video
        fg_w = target_w
        fg_h = int(round(fg_w * h_orig / w_orig))
        if fg_h % 2 != 0:
            fg_h -= 1

        fg_resized = cv2.resize(frame, (fg_w, fg_h), interpolation=cv2.INTER_LANCZOS4)

        # Position calculation
        if position == "top":
            fg_y = int(target_h * 0.16)
        else:
            # Center
            fg_y = (target_h - fg_h) // 2

        # 3. Soft ambient drop shadow above and below foreground
        shadow_h = 18
        for s in range(shadow_h):
            factor = (s / shadow_h) ** 1.6
            top_y = fg_y - shadow_h + s
            bot_y = fg_y + fg_h + s
            if 0 <= top_y < target_h:
                canvas[top_y, :] = (canvas[top_y, :] * factor).astype(np.uint8)
            if 0 <= bot_y < target_h:
                canvas[bot_y, :] = (canvas[bot_y, :] * (1.0 - factor)).astype(np.uint8)

        # Subtle dark border line on edges
        if fg_y - 1 >= 0:
            cv2.line(canvas, (0, fg_y - 1), (target_w, fg_y - 1), (50, 50, 50), 1)
        if fg_y + fg_h < target_h:
            cv2.line(canvas, (0, fg_y + fg_h), (target_w, fg_y + fg_h), (50, 50, 50), 1)

        # Paste uncropped foreground video
        canvas[fg_y:fg_y + fg_h, 0:fg_w] = fg_resized

        return canvas

    @classmethod
    def apply_streamer_split(
        cls,
        frame: np.ndarray,
        face_crop_box: Optional[Tuple[int, int, int, int]] = None,
        target_w: int = 1080,
        target_h: int = 1920
    ) -> np.ndarray:
        """
        GAMER / STREAMER LAYOUT:
        - Top section (~700px): Close-up zoom of streamer / facecam.
        - Bottom section: 100% uncropped full 16:9 gameplay!
        """
        h_orig, w_orig = frame.shape[:2]
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)

        # Gameplay dimensions (fitted to width, 100% uncropped)
        game_w = target_w
        game_h = int(round(game_w * h_orig / w_orig))
        if game_h % 2 != 0:
            game_h -= 1
        game_resized = cv2.resize(frame, (game_w, game_h), interpolation=cv2.INTER_LANCZOS4)

        # Place gameplay at bottom portion
        game_y = target_h - game_h - 100
        canvas[game_y:game_y + game_h, 0:game_w] = game_resized

        # Top section: Streamer Facecam
        top_h = game_y - 20
        if face_crop_box is not None:
            fx, fy, fw, fh = face_crop_box
            face_img = frame[fy:fy+fh, fx:fx+fw]
            if face_img.size > 0:
                top_resized = cv2.resize(face_img, (target_w, top_h), interpolation=cv2.INTER_LINEAR)
            else:
                top_resized = cv2.resize(frame, (target_w, top_h), interpolation=cv2.INTER_LINEAR)
        else:
            # Fallback: blurred ambient top
            top_resized = cv2.resize(frame, (target_w, top_h), interpolation=cv2.INTER_LINEAR)
            top_resized = cv2.GaussianBlur(top_resized, (35, 35), 0)

        canvas[0:top_h, 0:target_w] = top_resized

        # Sleek dividing border with neon accent line
        cv2.line(canvas, (0, top_h + 4), (target_w, top_h + 4), (30, 30, 30), 2)
        cv2.line(canvas, (0, top_h + 7), (target_w, top_h + 7), (70, 160, 255), 2)
        cv2.line(canvas, (0, top_h + 10), (target_w, top_h + 10), (30, 30, 30), 2)

        return canvas

    @classmethod
    def apply_smart_track(
        cls,
        frame: np.ndarray,
        crop_box: Tuple[int, int, int, int],
        target_w: int = 1080,
        target_h: int = 1920
    ) -> np.ndarray:
        """
        FULL ZOOM REFRAME (Crops sides to follow speaker in talking-head / podcast videos).
        """
        x, y, w, h = crop_box
        cropped = frame[y:y+h, x:x+w]
        if cropped.size == 0:
            return cv2.resize(frame, (target_w, target_h))
        return cv2.resize(cropped, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

    @classmethod
    def apply_split_screen(
        cls,
        frame: np.ndarray,
        box_top: Tuple[int, int, int, int],
        box_bottom: Tuple[int, int, int, int],
        target_w: int = 1080,
        target_h: int = 1920
    ) -> np.ndarray:
        half_h = target_h // 2
        
        # Crop Top
        xt, yt, wt, ht = box_top
        crop_t = frame[yt:yt+ht, xt:xt+wt]
        if crop_t.size == 0:
            crop_t = frame
        top_half = cv2.resize(crop_t, (target_w, half_h), interpolation=cv2.INTER_LINEAR)

        # Crop Bottom
        xb, yb, wb, hb = box_bottom
        crop_b = frame[yb:yb+hb, xb:xb+wb]
        if crop_b.size == 0:
            crop_b = frame
        bottom_half = cv2.resize(crop_b, (target_w, half_h), interpolation=cv2.INTER_LINEAR)

        combined = np.empty((target_h, target_w, 3), dtype=np.uint8)
        combined[0:half_h, :] = top_half
        combined[half_h:target_h, :] = bottom_half

        # Divider line
        line_y = half_h
        cv2.line(combined, (0, line_y - 2), (target_w, line_y - 2), (20, 20, 20), 1)
        cv2.line(combined, (0, line_y + 2), (target_w, line_y + 2), (20, 20, 20), 1)
        cv2.line(combined, (0, line_y - 1), (target_w, line_y + 1), (230, 230, 230), 2)

        return combined

    # =========================================================================
    # Pass 1: Analysis
    # =========================================================================

    def analyze_video(
        self,
        video_path: str,
        mode: str,
        sensitivity: str = "Padrão",
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_token: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Samples video frames, detects faces, and generates camera trajectories.
        For opusclip_fit mode, analysis is ultra-fast as it needs no cropping trajectory!
        """
        info = self.get_video_info(video_path)
        orig_w = info["width"]
        orig_h = info["height"]
        total_frames = info["total_frames"]

        result = {
            "info": info,
            "mode": mode,
            "sensitivity": sensitivity,
        }

        # For OpusClip Fit mode: frame is fitted 100% without cropping, so trajectory is static!
        if mode in ("opusclip_fit", "blur_fill"):
            if progress_cb:
                progress_cb(0.40, "Vídeo 100% completo preparado para encaixe vertical OpusClip...")
            time.sleep(0.1)
            if progress_cb:
                progress_cb(0.45, "Pronto para renderização com aceleração por GPU!")
            return result

        self._ensure_detector()
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Não foi possível abrir o arquivo: {video_path}")

        step = 3
        tracker = CameraTracker(orig_w, orig_h, sensitivity=sensitivity)
        result["tracker"] = tracker

        sampled_main = {}
        sampled_top = {}
        sampled_bottom = {}
        last_main_cx = orig_w / 2.0
        frame_idx = 0

        if progress_cb:
            progress_cb(0.02, "Iniciando análise facial com IA...")

        while True:
            if cancel_token and cancel_token[0]:
                cap.release()
                return {}

            ret, frame = cap.read()
            if not ret or frame_idx >= total_frames:
                break

            if frame_idx % step == 0:
                faces = self.detector.detect(frame)

                if mode == "podcast":
                    f_left, f_right = self.detector.get_podcast_faces(faces, orig_w)
                    if f_left and f_right:
                        sampled_top[frame_idx] = f_left.cx
                        sampled_bottom[frame_idx] = f_right.cx
                    elif f_left:
                        sampled_top[frame_idx] = f_left.cx
                        sampled_bottom[frame_idx] = orig_w * 0.75
                    else:
                        sampled_top[frame_idx] = orig_w * 0.25
                        sampled_bottom[frame_idx] = orig_w * 0.75
                else:
                    primary = self.detector.get_primary_face(faces, prev_cx=last_main_cx, frame_width=orig_w)
                    if primary:
                        sampled_main[frame_idx] = primary.cx
                        last_main_cx = primary.cx
                    else:
                        sampled_main[frame_idx] = None

            frame_idx += 1
            if frame_idx % 30 == 0 and progress_cb:
                pct = 0.05 + 0.35 * (frame_idx / max(1, total_frames))
                progress_cb(pct, f"Analisando rastreamento... ({int(pct*100)}%)")

        cap.release()

        if mode == "podcast":
            result["traj_top"] = tracker.build_trajectory(sampled_top, total_frames, default_cx=orig_w * 0.25)
            result["traj_bottom"] = tracker.build_trajectory(sampled_bottom, total_frames, default_cx=orig_w * 0.75)
        elif mode == "smart_track":
            result["traj_main"] = tracker.build_trajectory(sampled_main, total_frames, default_cx=orig_w / 2.0)

        if progress_cb:
            progress_cb(0.45, "Análise concluída com sucesso!")

        return result

    # =========================================================================
    # Pass 2: Rendering via FFmpeg stdin Pipe with GPU Acceleration
    # =========================================================================

    def render_video(
        self,
        input_path: str,
        output_path: str,
        analysis_data: Dict[str, Any],
        encoder: str = "auto",
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_token: Optional[list] = None
    ) -> bool:
        """
        Streams composited frames to FFmpeg with hardware GPU acceleration.
        """
        ffmpeg_exe = get_ffmpeg_path()
        if not ffmpeg_exe:
            raise RuntimeError("Binário FFmpeg não encontrado.")

        if encoder == "auto" or not encoder:
            encoder = get_best_encoder(ffmpeg_exe)

        info = analysis_data["info"]
        mode = analysis_data["mode"]
        tracker = analysis_data.get("tracker") or CameraTracker(info["width"], info["height"])
        total_frames = info["total_frames"]
        fps = info["fps"]

        out_w = self.TARGET_WIDTH
        out_h = self.TARGET_HEIGHT

        # Prepare FFmpeg command with GPU NVENC optimization
        cmd = [
            ffmpeg_exe,
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{out_w}x{out_h}",
            "-pix_fmt", "bgr24",
            "-r", str(fps),
            "-i", "-",  # pipe:0
            "-ss", "0",
            "-i", input_path,  # Audio source
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-c:v", encoder,
            "-pix_fmt", "yuv420p",
        ]

        if encoder == "h264_nvenc":
            # NVIDIA RTX Hardware Acceleration - Ultra Fast & Crisp
            cmd.extend([
                "-preset", "p4",
                "-tune", "hq",
                "-rc", "vbr",
                "-cq", "19",
                "-b:v", "0",
                "-maxrate", "25M",
                "-bufsize", "50M"
            ])
        elif encoder == "h264_amf":
            cmd.extend(["-quality", "speed", "-rc", "cbr"])
        elif encoder == "h264_qsv":
            cmd.extend(["-preset", "veryfast", "-global_quality", "21"])
        else:
            # CPU Fallback (libx264)
            cmd.extend(["-preset", "veryfast", "-crf", "20"])

        cmd.extend([
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_path
        ])

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
            bufsize=10**8
        )

        cap = cv2.VideoCapture(input_path)
        frame_idx = 0
        start_time = time.time()

        traj_main = analysis_data.get("traj_main")
        traj_top = analysis_data.get("traj_top")
        traj_bottom = analysis_data.get("traj_bottom")

        encoder_label = "⚡ GPU NVIDIA NVENC" if encoder == "h264_nvenc" else f"Encoder: {encoder}"

        try:
            while True:
                if cancel_token and cancel_token[0]:
                    cap.release()
                    if process.stdin:
                        process.stdin.close()
                    process.terminate()
                    if os.path.exists(output_path):
                        try:
                            os.remove(output_path)
                        except Exception:
                            pass
                    return False

                ret, frame = cap.read()
                if not ret or frame_idx >= total_frames:
                    break

                # Apply layout
                if mode in ("opusclip_fit", "blur_fill"):
                    out_frame = self.apply_opusclip_fit(frame, out_w, out_h, position="center")
                elif mode == "streamer_split":
                    out_frame = self.apply_streamer_split(frame, target_w=out_w, target_h=out_h)
                elif mode == "smart_track" and traj_main is not None:
                    cx = traj_main[min(frame_idx, len(traj_main) - 1)]
                    crop_box = tracker.get_crop_box(cx)
                    out_frame = self.apply_smart_track(frame, crop_box, out_w, out_h)
                elif mode == "podcast" and traj_top is not None and traj_bottom is not None:
                    cx1 = traj_top[min(frame_idx, len(traj_top) - 1)]
                    cx2 = traj_bottom[min(frame_idx, len(traj_bottom) - 1)]
                    box_t, box_b = tracker.get_podcast_crop_boxes(cx1, cx2)
                    out_frame = self.apply_split_screen(frame, box_t, box_b, out_w, out_h)
                else:
                    out_frame = self.apply_opusclip_fit(frame, out_w, out_h, position="center")

                # Stream to FFmpeg
                try:
                    process.stdin.write(out_frame.tobytes())
                except (BrokenPipeError, OSError):
                    _, stderr = process.communicate()
                    err_msg = stderr.decode('utf-8', errors='ignore')
                    raise RuntimeError(f"FFmpeg encerrou inesperadamente: {err_msg}")

                frame_idx += 1

                if frame_idx % 15 == 0 and progress_cb:
                    elapsed = time.time() - start_time
                    fps_render = frame_idx / max(0.01, elapsed)
                    rem_frames = total_frames - frame_idx
                    eta_sec = rem_frames / max(1.0, fps_render)
                    eta_str = time.strftime('%M:%S', time.gmtime(eta_sec))

                    pct = 0.45 + 0.53 * (frame_idx / max(1, total_frames))
                    msg = f"Renderizando ({int(pct*100)}%) • {encoder_label} • {fps_render:.0f} FPS • Restante: {eta_str}"
                    progress_cb(pct, msg)

        finally:
            cap.release()
            if process.stdin:
                try:
                    process.stdin.close()
                except Exception:
                    pass

        stderr_output = process.stderr.read().decode('utf-8', errors='ignore') if process.stderr else ""
        process.wait()

        if process.returncode != 0:
            raise RuntimeError(f"Erro na renderização FFmpeg (código {process.returncode}): {stderr_output}")

        if progress_cb:
            progress_cb(1.0, "Short Vertical gerado com sucesso!")

        return True

    # =========================================================================
    # Quick Preview Helper
    # =========================================================================

    def generate_preview_frame(
        self,
        video_path: str,
        frame_idx: int,
        mode: str,
        sensitivity: str = "Padrão",
        target_preview_size: Tuple[int, int] = (324, 576)
    ) -> Optional[Image.Image]:
        """
        Extracts a single frame and renders preview at requested size.
        """
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return None

        h_orig, w_orig = frame.shape[:2]

        if mode in ("opusclip_fit", "blur_fill"):
            res = self.apply_opusclip_fit(frame, self.TARGET_WIDTH, self.TARGET_HEIGHT, position="center")
        elif mode == "streamer_split":
            res = self.apply_streamer_split(frame, target_w=self.TARGET_WIDTH, target_h=self.TARGET_HEIGHT)
        elif mode == "smart_track":
            self._ensure_detector()
            tracker = CameraTracker(w_orig, h_orig, sensitivity=sensitivity)
            faces = self.detector.detect(frame)
            primary = self.detector.get_primary_face(faces, frame_width=w_orig)
            cx = primary.cx if primary else (w_orig / 2.0)
            crop_box = tracker.get_crop_box(cx)
            res = self.apply_smart_track(frame, crop_box, self.TARGET_WIDTH, self.TARGET_HEIGHT)
        elif mode == "podcast":
            self._ensure_detector()
            tracker = CameraTracker(w_orig, h_orig, sensitivity=sensitivity)
            faces = self.detector.detect(frame)
            f_left, f_right = self.detector.get_podcast_faces(faces, w_orig)
            cx1 = f_left.cx if f_left else (w_orig * 0.25)
            cx2 = f_right.cx if f_right else (w_orig * 0.75)
            box_t, box_b = tracker.get_podcast_crop_boxes(cx1, cx2)
            res = self.apply_split_screen(frame, box_t, box_b, self.TARGET_WIDTH, self.TARGET_HEIGHT)
        else:
            res = self.apply_opusclip_fit(frame, self.TARGET_WIDTH, self.TARGET_HEIGHT)

        # Resize for GUI display
        preview_rgb = cv2.cvtColor(cv2.resize(res, target_preview_size), cv2.COLOR_BGR2RGB)
        return Image.fromarray(preview_rgb)
