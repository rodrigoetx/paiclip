import os
import sys
import time
import threading
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageTk
import cv2

# Import core modules
from core.renderer import VideoRenderer
from core.tracker import CameraTracker
from utils.ffmpeg_check import (
    get_ffmpeg_path,
    ensure_ffmpeg,
    probe_encoders,
    get_best_encoder,
    get_encoder_display_name
)

# Application Theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ReframeApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("REFRAME-AI • Clone Local do OpusClip (Automação Shorts, Reels & TikTok)")
        self.geometry("1200x840")
        self.minsize(1040, 720)

        # Video state
        self.video_path: Optional[str] = None
        self.video_info: Optional[Dict[str, Any]] = None
        self.output_path: Optional[str] = None
        self.current_preview_frame_idx: int = 0
        self.is_processing: bool = False
        self.cancel_token: list = [False]

        # Core engines
        self.renderer = VideoRenderer()
        self.ffmpeg_path = get_ffmpeg_path()
        self.encoders = probe_encoders(self.ffmpeg_path)
        self.best_encoder = get_best_encoder(self.ffmpeg_path)

        # Build UI
        self._build_layout()

        # Check FFmpeg and GPU on launch
        threading.Thread(target=self._verify_ffmpeg_on_start, daemon=True).start()

    def _verify_ffmpeg_on_start(self):
        try:
            path = ensure_ffmpeg(progress_callback=self._update_ffmpeg_status)
            self.ffmpeg_path = path
            self.encoders = probe_encoders(path)
            self.best_encoder = get_best_encoder(path)
            self.after(0, self._refresh_encoder_dropdown)
        except Exception as e:
            self.after(0, lambda: self.status_label.configure(
                text=f"⚠️ Aviso FFmpeg: {e}",
                text_color="#F87171"
            ))

    def _update_ffmpeg_status(self, pct: float, msg: str):
        self.after(0, lambda: self.status_label.configure(text=f"🔧 {msg}", text_color="#60A5FA"))

    def _build_layout(self):
        # Main Grid Layout (2 Columns)
        self.grid_columnconfigure(0, weight=4, minsize=380) # Left (Preview)
        self.grid_columnconfigure(1, weight=6, minsize=620) # Right (Controls)
        self.grid_rowconfigure(0, weight=1)

        # =====================================================================
        # LEFT PANEL: 9:16 Video Preview & Timeline Scrubber
        # =====================================================================
        self.left_panel = ctk.CTkFrame(self, corner_radius=14, fg_color="#18181B", border_width=1, border_color="#27272A")
        self.left_panel.grid(row=0, column=0, padx=(18, 9), pady=18, sticky="nsew")
        self.left_panel.grid_rowconfigure(1, weight=1)
        self.left_panel.grid_columnconfigure(0, weight=1)

        # Preview Header
        preview_header_frame = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        preview_header_frame.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")

        ctk.CTkLabel(
            preview_header_frame,
            text="📱 Preview Vertical 9:16",
            font=ctk.CTkFont(size=17, weight="bold")
        ).pack(side="left")

        self.preview_badge = ctk.CTkLabel(
            preview_header_frame,
            text="1080 x 1920 (Shorts/Reels)",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#27272A",
            text_color="#34D399",
            corner_radius=6,
            padx=8,
            pady=2
        )
        self.preview_badge.pack(side="right")

        # Preview Canvas Container (9:16 aspect ratio: 324 x 576)
        self.preview_container = ctk.CTkFrame(
            self.left_panel,
            fg_color="#09090B",
            corner_radius=12,
            border_width=1,
            border_color="#3F3F46"
        )
        self.preview_container.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")
        self.preview_container.grid_rowconfigure(0, weight=1)
        self.preview_container.grid_columnconfigure(0, weight=1)

        self.preview_label = ctk.CTkLabel(
            self.preview_container,
            text="Nenhum vídeo carregado\n\nArraste ou selecione um vídeo 16:9\npara visualizar a adaptação vertical",
            font=ctk.CTkFont(size=13),
            text_color="#71717A"
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        # Timeline Scrubber Card
        self.scrubber_frame = ctk.CTkFrame(self.left_panel, fg_color="#27272A", corner_radius=10)
        self.scrubber_frame.grid(row=2, column=0, padx=16, pady=(8, 16), sticky="ew")
        self.scrubber_frame.grid_columnconfigure(1, weight=1)

        self.btn_step_prev = ctk.CTkButton(
            self.scrubber_frame,
            text="⏪ -2s",
            width=54,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#3F3F46",
            hover_color="#52525B",
            command=lambda: self._step_timeline(-2)
        )
        self.btn_step_prev.grid(row=0, column=0, padx=(10, 6), pady=8)

        self.timeline_slider = ctk.CTkSlider(
            self.scrubber_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            command=self._on_timeline_scrub,
            state="disabled"
        )
        self.timeline_slider.set(0)
        self.timeline_slider.grid(row=0, column=1, padx=6, pady=8, sticky="ew")

        self.btn_step_next = ctk.CTkButton(
            self.scrubber_frame,
            text="+2s ⏩",
            width=54,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#3F3F46",
            hover_color="#52525B",
            command=lambda: self._step_timeline(2)
        )
        self.btn_step_next.grid(row=0, column=2, padx=(6, 10), pady=8)

        self.time_label = ctk.CTkLabel(
            self.scrubber_frame,
            text="00:00 / 00:00",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#A1A1AA"
        )
        self.time_label.grid(row=1, column=0, columnspan=3, pady=(0, 8))

        # =====================================================================
        # RIGHT PANEL: Configuration, Video Selector & Execution
        # =====================================================================
        self.right_panel = ctk.CTkScrollableFrame(self, corner_radius=14, fg_color="#18181B", border_width=1, border_color="#27272A")
        self.right_panel.grid(row=0, column=1, padx=(9, 18), pady=18, sticky="nsew")

        # Header Title
        title_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        title_frame.pack(fill="x", padx=14, pady=(10, 12))

        title_label = ctk.CTkLabel(
            title_frame,
            text="✨ REFRAME-AI",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#60A5FA"
        )
        title_label.pack(anchor="w")

        sub_label = ctk.CTkLabel(
            title_frame,
            text="Clone Local do OpusClip • Adaptação 16:9 ➔ 9:16 Inteligente & Acelerada por GPU",
            font=ctk.CTkFont(size=13),
            text_color="#9CA3AF"
        )
        sub_label.pack(anchor="w", pady=(2, 0))

        # Section 1: Video File Selection Card
        self.file_card = ctk.CTkFrame(self.right_panel, fg_color="#27272A", corner_radius=12)
        self.file_card.pack(fill="x", padx=14, pady=8)

        self.btn_load_video = ctk.CTkButton(
            self.file_card,
            text="📂 Selecionar Vídeo (MP4, MKV, MOV, AVI)",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            corner_radius=8,
            command=self._select_video_file
        )
        self.btn_load_video.pack(fill="x", padx=14, pady=(14, 8))

        self.video_details_label = ctk.CTkLabel(
            self.file_card,
            text="Nenhum arquivo carregado",
            font=ctk.CTkFont(size=12),
            text_color="#9CA3AF",
            wraplength=540,
            justify="left"
        )
        self.video_details_label.pack(anchor="w", padx=16, pady=(0, 6))

        # Auto-detection badge
        self.detection_badge = ctk.CTkLabel(
            self.file_card,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#34D399",
            wraplength=540,
            justify="left"
        )
        self.detection_badge.pack(anchor="w", padx=16, pady=(0, 12))

        # Section 2: Layout Mode Selector (OpusClip Presets)
        mode_card = ctk.CTkFrame(self.right_panel, fg_color="#27272A", corner_radius=12)
        mode_card.pack(fill="x", padx=14, pady=8)

        ctk.CTkLabel(
            mode_card,
            text="🎬 Modo de Layout & Enquadramento Vertical",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w", padx=14, pady=(12, 6))

        # Default mode is opusclip_fit (100% uncropped!)
        self.mode_var = ctk.StringVar(value="opusclip_fit")

        # Mode 1 Radio: OpusClip Fit & Blur (DEFAULT)
        self.radio_mode1 = ctk.CTkRadioButton(
            mode_card,
            text="🎮 OpusClip Fit & Blur (100% Sem Cortes - Recomendado para Gameplays & Geral)",
            font=ctk.CTkFont(size=13, weight="bold"),
            variable=self.mode_var,
            value="opusclip_fit",
            command=self._on_mode_change
        )
        self.radio_mode1.pack(anchor="w", padx=14, pady=(6, 2))

        ctk.CTkLabel(
            mode_card,
            text="Adapta o vídeo 16:9 inteiro para 9:16 sem cortar NENHUM pixel das laterais. O radar, placar, HUD e inimigos ficam 100% visíveis, com fundo dinâmico desfocado (Blur Bokeh) e sombra estética.",
            font=ctk.CTkFont(size=11),
            text_color="#E4E4E7",
            wraplength=520,
            justify="left"
        ).pack(anchor="w", padx=40, pady=(0, 8))

        # Mode 2 Radio: Streamer Split
        self.radio_mode2 = ctk.CTkRadioButton(
            mode_card,
            text="🕹️ Streamer Split (Webcam no Topo + Gameplay Inteira Embaixo)",
            font=ctk.CTkFont(size=13, weight="bold"),
            variable=self.mode_var,
            value="streamer_split",
            command=self._on_mode_change
        )
        self.radio_mode2.pack(anchor="w", padx=14, pady=(4, 2))

        ctk.CTkLabel(
            mode_card,
            text="Coloca o close do jogador/webcam no topo e a gameplay completa em 16:9 embaixo com linha divisória neon.",
            font=ctk.CTkFont(size=11),
            text_color="#9CA3AF",
            wraplength=520,
            justify="left"
        ).pack(anchor="w", padx=40, pady=(0, 8))

        # Mode 3 Radio: Smart Tracker (Vlogs/Podcasts only)
        self.radio_mode3 = ctk.CTkRadioButton(
            mode_card,
            text="🎯 Smart Tracker 9:16 (Zoom Cheio com IA - Apenas para Podcasts / Vlogs)",
            font=ctk.CTkFont(size=13, weight="bold"),
            variable=self.mode_var,
            value="smart_track",
            command=self._on_mode_change
        )
        self.radio_mode3.pack(anchor="w", padx=14, pady=(4, 2))

        ctk.CTkLabel(
            mode_card,
            text="Preenche a tela toda 9:16 seguindo o locutor com Deadzone 50px e suavização. (⚠️ Atenção: Corta as laterais; não indicado para gameplays onde se precisa ver o HUD inteiro).",
            font=ctk.CTkFont(size=11),
            text_color="#9CA3AF",
            wraplength=520,
            justify="left"
        ).pack(anchor="w", padx=40, pady=(0, 8))

        # Mode 4 Radio: Split Screen 2 People
        self.radio_mode4 = ctk.CTkRadioButton(
            mode_card,
            text="👥 Dividir Tela (2 Locutores / Podcast)",
            font=ctk.CTkFont(size=13, weight="bold"),
            variable=self.mode_var,
            value="podcast",
            command=self._on_mode_change
        )
        self.radio_mode4.pack(anchor="w", padx=14, pady=(4, 2))

        ctk.CTkLabel(
            mode_card,
            text="Divide 50/50 entre dois locutores para entrevistas com corte individual.",
            font=ctk.CTkFont(size=11),
            text_color="#9CA3AF",
            wraplength=520,
            justify="left"
        ).pack(anchor="w", padx=40, pady=(0, 14))

        # Section 3: Camera Sensitivity Slider
        self.sens_card = ctk.CTkFrame(self.right_panel, fg_color="#27272A", corner_radius=12)
        self.sens_card.pack(fill="x", padx=14, pady=8)

        ctk.CTkLabel(
            self.sens_card,
            text="🕹️ Sensibilidade do Rastreamento Facial",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w", padx=14, pady=(12, 4))

        sens_selector_frame = ctk.CTkFrame(self.sens_card, fg_color="transparent")
        sens_selector_frame.pack(fill="x", padx=14, pady=(4, 6))

        self.sens_seg = ctk.CTkSegmentedButton(
            sens_selector_frame,
            values=["Lenta", "Padrão", "Rápida"],
            command=self._on_sensitivity_change
        )
        self.sens_seg.set("Padrão")
        self.sens_seg.pack(side="left", fill="x", expand=True)

        self.sens_desc_label = ctk.CTkLabel(
            self.sens_card,
            text="Padrão: Equilíbrio fluido e natural com zona morta de 45px (usado nos modos com rastreamento de rosto).",
            font=ctk.CTkFont(size=11),
            text_color="#9CA3AF"
        )
        self.sens_desc_label.pack(anchor="w", padx=14, pady=(2, 12))

        # Section 4: Hardware Acceleration & GPU Selection
        hw_card = ctk.CTkFrame(self.right_panel, fg_color="#27272A", corner_radius=12)
        hw_card.pack(fill="x", padx=14, pady=8)

        hw_top = ctk.CTkFrame(hw_card, fg_color="transparent")
        hw_top.pack(fill="x", padx=14, pady=(12, 4))

        ctk.CTkLabel(
            hw_top,
            text="⚡ Renderizador & Aceleração por Hardware (GPU)",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")

        encoder_values = ["auto", "libx264"]
        if self.encoders.get("h264_nvenc"):
            encoder_values.insert(1, "h264_nvenc")
        if self.encoders.get("h264_amf"):
            encoder_values.insert(1, "h264_amf")
        if self.encoders.get("h264_qsv"):
            encoder_values.insert(1, "h264_qsv")

        self.encoder_var = ctk.StringVar(value="auto")
        self.encoder_menu = ctk.CTkOptionMenu(
            hw_top,
            values=encoder_values,
            variable=self.encoder_var,
            width=230,
            command=self._on_encoder_change
        )
        self.encoder_menu.pack(side="right")

        self.hw_info_label = ctk.CTkLabel(
            hw_card,
            text=f"Aceleração ativa: {get_encoder_display_name(self.best_encoder)}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#34D399"
        )
        self.hw_info_label.pack(anchor="w", padx=14, pady=(0, 12))

        # Section 5: Progress & Action Controls
        self.action_card = ctk.CTkFrame(self.right_panel, fg_color="#27272A", corner_radius=12)
        self.action_card.pack(fill="x", padx=14, pady=(8, 14))

        # Big Action Button
        self.btn_generate = ctk.CTkButton(
            self.action_card,
            text="🚀 GERAR SHORT VERTICAL",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=50,
            fg_color="#059669",
            hover_color="#047857",
            corner_radius=10,
            state="disabled",
            command=self._start_processing
        )
        self.btn_generate.pack(fill="x", padx=14, pady=(14, 8))

        # Cancel Button
        self.btn_cancel = ctk.CTkButton(
            self.action_card,
            text="⏹️ Cancelar Operação",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=34,
            fg_color="#DC2626",
            hover_color="#B91C1C",
            corner_radius=8,
            command=self._cancel_processing
        )
        # Hidden until processing

        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(self.action_card, height=12, corner_radius=6)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=14, pady=(8, 4))

        # Status Label
        self.status_label = ctk.CTkLabel(
            self.action_card,
            text="Carregue um vídeo horizontal para iniciar",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#9CA3AF"
        )
        self.status_label.pack(anchor="w", padx=14, pady=(0, 8))

        # Post-Processing Actions (Open Folder / Play Video)
        self.post_actions_frame = ctk.CTkFrame(self.action_card, fg_color="transparent")

        self.btn_open_folder = ctk.CTkButton(
            self.post_actions_frame,
            text="📁 Abrir Vídeo na Pasta",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=38,
            fg_color="#3B82F6",
            hover_color="#2563EB",
            command=self._open_output_folder
        )
        self.btn_open_folder.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_play_video = ctk.CTkButton(
            self.post_actions_frame,
            text="▶️ Reproduzir Vídeo",
            font=ctk.CTkFont(size=13, weight="bold"),
            height=38,
            fg_color="#10B981",
            hover_color="#059669",
            command=self._play_output_video
        )
        self.btn_play_video.pack(side="right", fill="x", expand=True, padx=(6, 0))

    # =========================================================================
    # Event Handlers & Callbacks
    # =========================================================================

    def _select_video_file(self):
        filetypes = [
            ("Arquivos de Vídeo", "*.mp4 *.mov *.mkv *.avi *.webm"),
            ("MP4 (*.mp4)", "*.mp4"),
            ("MKV (*.mkv)", "*.mkv"),
            ("Todos os Arquivos", "*.*")
        ]
        chosen = filedialog.askopenfilename(title="Selecione um Vídeo Horizontal", filetypes=filetypes)
        if not chosen:
            return

        try:
            info = self.renderer.get_video_info(chosen)
            self.video_path = chosen
            self.video_info = info

            # Update UI details
            file_name = Path(chosen).name
            file_size_mb = os.path.getsize(chosen) / (1024 * 1024)
            details = (
                f"📹 Arquivo: {file_name}\n"
                f"📐 Resolução: {info['width']}x{info['height']} • ⏱️ Duração: {info['duration_str']} • "
                f"🎞️ {info['fps']} FPS • 💾 {file_size_mb:.1f} MB"
            )
            self.video_details_label.configure(text=details, text_color="#E4E4E7")

            # Enable controls
            self.timeline_slider.configure(
                state="normal",
                to=max(1, info["total_frames"] - 1),
                number_of_steps=min(500, info["total_frames"])
            )
            self.timeline_slider.set(0)
            self.time_label.configure(text=f"00:00 / {info['duration_str']}")
            self.btn_generate.configure(state="normal")
            self.status_label.configure(text="Pronto para gerar Short Vertical", text_color="#34D399")

            # Reset post actions
            self.post_actions_frame.pack_forget()

            # Intelligent Content Analysis in Background
            self.detection_badge.configure(text="🔍 Analisando conteúdo do vídeo...", text_color="#60A5FA")
            threading.Thread(target=self._auto_detect_content, daemon=True).start()

            # Refresh Preview
            self._update_preview_frame(0)

        except Exception as e:
            messagebox.showerror("Erro ao Carregar Vídeo", f"Não foi possível ler o vídeo selecionado:\n{e}")

    def _auto_detect_content(self):
        try:
            detected = self.renderer.detect_video_content_type(self.video_path)
            rec_mode = detected.get("recommended_mode", "opusclip_fit")
            msg = detected.get("message", "")

            def apply_detection():
                self.mode_var.set(rec_mode)
                self.detection_badge.configure(text=msg, text_color="#34D399")
                self._update_preview_frame(int(self.timeline_slider.get()))

            self.after(0, apply_detection)
        except Exception as e:
            print(f"[AutoDetect] Erro: {e}")

    def _on_mode_change(self):
        if self.video_path:
            self._update_preview_frame(int(self.timeline_slider.get()))

    def _on_sensitivity_change(self, value):
        descs = {
            "Lenta": "Lenta: Movimento cinemático ultra-suave com zona morta de 70px (ideal para entrevistas).",
            "Padrão": "Padrão: Equilíbrio fluido e natural com zona morta de 45px (ideal para vídeos normais).",
            "Rápida": "Rápida: Resposta ágil a movimentos rápidos com zona morta de 22px (ideal para vlogs dinâmicos)."
        }
        self.sens_desc_label.configure(text=descs.get(value, ""))
        if self.video_path:
            self._update_preview_frame(int(self.timeline_slider.get()))

    def _on_encoder_change(self, choice):
        if choice == "auto":
            display = get_encoder_display_name(self.best_encoder)
        else:
            display = get_encoder_display_name(choice)
        self.hw_info_label.configure(text=f"Aceleração ativa: {display}")

    def _refresh_encoder_dropdown(self):
        encoder_values = ["auto", "libx264"]
        if self.encoders.get("h264_nvenc"):
            encoder_values.insert(1, "h264_nvenc")
        if self.encoders.get("h264_amf"):
            encoder_values.insert(1, "h264_amf")
        if self.encoders.get("h264_qsv"):
            encoder_values.insert(1, "h264_qsv")
        self.encoder_menu.configure(values=encoder_values)
        self._on_encoder_change(self.encoder_var.get())

    def _on_timeline_scrub(self, value):
        if not self.video_info:
            return
        frame_idx = int(value)
        fps = self.video_info["fps"]
        cur_sec = frame_idx / fps if fps > 0 else 0
        cur_str = time.strftime('%M:%S', time.gmtime(cur_sec))
        dur_str = self.video_info["duration_str"]
        self.time_label.configure(text=f"{cur_str} / {dur_str}")
        self._update_preview_frame(frame_idx)

    def _step_timeline(self, seconds: float):
        if not self.video_info:
            return
        fps = self.video_info["fps"]
        delta_frames = int(seconds * fps)
        cur = int(self.timeline_slider.get())
        new_val = max(0, min(self.video_info["total_frames"] - 1, cur + delta_frames))
        self.timeline_slider.set(new_val)
        self._on_timeline_scrub(new_val)

    def _update_preview_frame(self, frame_idx: int):
        if not self.video_path:
            return

        mode = self.mode_var.get()
        sensitivity = self.sens_seg.get()

        def background_render():
            try:
                preview_pil = self.renderer.generate_preview_frame(
                    self.video_path,
                    frame_idx,
                    mode=mode,
                    sensitivity=sensitivity,
                    target_preview_size=(324, 576)
                )
                if preview_pil:
                    ctk_img = ctk.CTkImage(
                        light_image=preview_pil,
                        dark_image=preview_pil,
                        size=(324, 576)
                    )
                    self.after(0, lambda: self._apply_preview_image(ctk_img))
            except Exception as e:
                print(f"[Preview] Erro ao renderizar preview: {e}")

        threading.Thread(target=background_render, daemon=True).start()

    def _apply_preview_image(self, ctk_img):
        self.preview_label.configure(image=ctk_img, text="")
        self.preview_label.image = ctk_img

    # =========================================================================
    # Video Generation Pipeline
    # =========================================================================

    def _start_processing(self):
        if not self.video_path or not os.path.exists(self.video_path):
            messagebox.showwarning("Aviso", "Por favor, selecione um arquivo de vídeo válido primeiro.")
            return

        if self.is_processing:
            return

        # Prepare output path
        src_path = Path(self.video_path)
        out_name = f"{src_path.stem}_short_9x16.mp4"
        self.output_path = str(src_path.parent / out_name)

        # Set processing state
        self.is_processing = True
        self.cancel_token = [False]

        # UI Updates
        self.btn_generate.pack_forget()
        self.btn_cancel.pack(fill="x", padx=14, pady=(14, 8))
        self.btn_load_video.configure(state="disabled")
        self.radio_mode1.configure(state="disabled")
        self.radio_mode2.configure(state="disabled")
        self.radio_mode3.configure(state="disabled")
        self.radio_mode4.configure(state="disabled")
        self.sens_seg.configure(state="disabled")
        self.encoder_menu.configure(state="disabled")
        self.post_actions_frame.pack_forget()
        self.progress_bar.set(0)
        self.status_label.configure(text="Iniciando processamento com GPU...", text_color="#60A5FA")

        # Launch Worker Thread
        thread = threading.Thread(target=self._worker_process, daemon=True)
        thread.start()

    def _cancel_processing(self):
        if self.is_processing:
            self.cancel_token[0] = True
            self.status_label.configure(text="Cancelando processo...", text_color="#EF4444")
            self.btn_cancel.configure(state="disabled")

    def _worker_process(self):
        mode = self.mode_var.get()
        sensitivity = self.sens_seg.get()
        chosen_encoder = self.encoder_var.get()
        if chosen_encoder == "auto":
            chosen_encoder = self.best_encoder

        try:
            # Step 1: Face & Trajectory Analysis
            analysis = self.renderer.analyze_video(
                self.video_path,
                mode=mode,
                sensitivity=sensitivity,
                progress_cb=self._on_progress_update,
                cancel_token=self.cancel_token
            )

            if self.cancel_token[0]:
                self.after(0, lambda: self._on_process_finished(success=False, msg="Processamento cancelado pelo usuário."))
                return

            # Step 2: FFmpeg Pipe Rendering with GPU
            success = self.renderer.render_video(
                input_path=self.video_path,
                output_path=self.output_path,
                analysis_data=analysis,
                encoder=chosen_encoder,
                progress_cb=self._on_progress_update,
                cancel_token=self.cancel_token
            )

            if self.cancel_token[0] or not success:
                self.after(0, lambda: self._on_process_finished(success=False, msg="Processamento cancelado pelo usuário."))
            else:
                self.after(0, lambda: self._on_process_finished(success=True, msg="Short Vertical gerado com sucesso!"))

        except Exception as e:
            err_text = str(e)
            self.after(0, lambda: self._on_process_finished(success=False, msg=f"Erro: {err_text}"))

    def _on_progress_update(self, progress: float, message: str):
        self.after(0, lambda: self._apply_progress(progress, message))

    def _apply_progress(self, progress: float, message: str):
        self.progress_bar.set(progress)
        self.status_label.configure(text=message, text_color="#93C5FD")

    def _on_process_finished(self, success: bool, msg: str):
        self.is_processing = False
        self.btn_cancel.pack_forget()
        self.btn_generate.pack(fill="x", padx=14, pady=(14, 8))
        self.btn_cancel.configure(state="normal")
        self.btn_load_video.configure(state="normal")
        self.radio_mode1.configure(state="normal")
        self.radio_mode2.configure(state="normal")
        self.radio_mode3.configure(state="normal")
        self.radio_mode4.configure(state="normal")
        self.sens_seg.configure(state="normal")
        self.encoder_menu.configure(state="normal")

        if success:
            self.progress_bar.set(1.0)
            self.status_label.configure(
                text=f"✅ {msg}\nSalvo em: {Path(self.output_path).name}",
                text_color="#10B981"
            )
            self.post_actions_frame.pack(fill="x", padx=14, pady=(6, 12))
            messagebox.showinfo("Sucesso!", f"Seu vídeo vertical foi gerado com sucesso!\n\nArquivo:\n{self.output_path}")
        else:
            self.status_label.configure(text=f"❌ {msg}", text_color="#EF4444")
            if "cancelado" not in msg.lower():
                messagebox.showerror("Erro no Processamento", msg)

    def _open_output_folder(self):
        if self.output_path and os.path.exists(self.output_path):
            if sys.platform == "win32":
                subprocess.run(f'explorer /select,"{os.path.abspath(self.output_path)}"', shell=True)
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", self.output_path])
            else:
                subprocess.run(["xdg-open", str(Path(self.output_path).parent)])

    def _play_output_video(self):
        if self.output_path and os.path.exists(self.output_path):
            if sys.platform == "win32":
                os.startfile(self.output_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", self.output_path])
            else:
                subprocess.run(["xdg-open", self.output_path])


if __name__ == "__main__":
    app = ReframeApp()
    app.mainloop()
