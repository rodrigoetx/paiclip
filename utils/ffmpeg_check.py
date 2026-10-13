import os
import sys
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

_CACHED_FFMPEG_PATH = None
_CACHED_ENCODERS = None

def get_ffmpeg_path() -> str:
    """
    Locates the FFmpeg executable:
    1. System PATH
    2. Local ./bin directory
    3. imageio_ffmpeg bundled binary
    4. Downloads or returns None if unavailable
    """
    global _CACHED_FFMPEG_PATH
    if _CACHED_FFMPEG_PATH and os.path.exists(_CACHED_FFMPEG_PATH):
        return _CACHED_FFMPEG_PATH

    # 1. System PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        _CACHED_FFMPEG_PATH = system_ffmpeg
        return _CACHED_FFMPEG_PATH

    # 2. Local ./bin directory
    base_dir = Path(__file__).resolve().parent.parent
    local_bin = base_dir / "bin" / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if local_bin.exists():
        _CACHED_FFMPEG_PATH = str(local_bin)
        return _CACHED_FFMPEG_PATH

    # 3. imageio_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            _CACHED_FFMPEG_PATH = exe
            return _CACHED_FFMPEG_PATH
    except Exception:
        pass

    return ""

def ensure_ffmpeg(progress_callback=None) -> str:
    """
    Ensures FFmpeg is available. If missing, attempts to download a static build.
    """
    path = get_ffmpeg_path()
    if path:
        return path

    # Attempt download for Windows
    if sys.platform == "win32":
        if progress_callback:
            progress_callback(0.1, "Baixando FFmpeg estático para Windows...")
        
        base_dir = Path(__file__).resolve().parent.parent
        bin_dir = base_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg_exe = bin_dir / "ffmpeg.exe"

        zip_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        zip_path = bin_dir / "ffmpeg.zip"

        try:
            def report_hook(count, block_size, total_size):
                if total_size > 0 and progress_callback:
                    p = min(0.9, 0.1 + (count * block_size / total_size) * 0.8)
                    progress_callback(p, f"Baixando FFmpeg... {int(p*100)}%")

            urllib.request.urlretrieve(zip_url, zip_path, reporthook=report_hook)
            
            if progress_callback:
                progress_callback(0.92, "Extraindo binário do FFmpeg...")
                
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    if member.endswith("ffmpeg.exe"):
                        with zip_ref.open(member) as source, open(ffmpeg_exe, "wb") as target:
                            shutil.copyfileobj(source, target)
                        break

            if zip_path.exists():
                zip_path.unlink()

            if ffmpeg_exe.exists():
                global _CACHED_FFMPEG_PATH
                _CACHED_FFMPEG_PATH = str(ffmpeg_exe)
                return str(ffmpeg_exe)
        except Exception as e:
            if progress_callback:
                progress_callback(1.0, f"Erro ao baixar FFmpeg: {e}")
            raise RuntimeError(f"FFmpeg não encontrado e falha ao baixar: {e}")

    raise RuntimeError("FFmpeg não encontrado no sistema. Por favor, instale o FFmpeg ou adicione-o ao PATH.")

def probe_encoders(ffmpeg_exe: str = None) -> dict:
    """
    Tests hardware and software encoders with a valid resolution probe (256x256).
    Hardware encoders like NVENC require dimensions >= 128px to initialize.
    Returns dict: {'h264_nvenc': bool, 'h264_amf': bool, 'h264_qsv': bool, 'libx264': bool}
    """
    global _CACHED_ENCODERS
    if _CACHED_ENCODERS is not None:
        return _CACHED_ENCODERS

    if not ffmpeg_exe:
        ffmpeg_exe = get_ffmpeg_path()

    if not ffmpeg_exe or not os.path.exists(ffmpeg_exe):
        return {"libx264": True}

    candidates = ["h264_nvenc", "h264_amf", "h264_qsv", "libx264"]
    results = {}

    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    for enc in candidates:
        # Use 256x256 resolution so hardware encoders (like NVENC) accept the frame dimension
        cmd = [
            ffmpeg_exe,
            "-hide_banner",
            "-loglevel", "error",
            "-f", "lavfi",
            "-i", "color=c=black:s=256x256:d=0.05",
            "-c:v", enc,
            "-f", "null",
            "-"
        ]
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                timeout=4
            )
            results[enc] = (res.returncode == 0)
        except Exception:
            results[enc] = False

    # libx264 is always available as software fallback
    if not any(results.values()):
        results["libx264"] = True

    _CACHED_ENCODERS = results
    return results

def get_best_encoder(ffmpeg_exe: str = None) -> str:
    """
    Returns the fastest available encoder (NVENC > AMF > QSV > libx264).
    Prioritizes NVIDIA GPU (NVENC) for RTX cards like RTX 3060 / 5060.
    """
    encoders = probe_encoders(ffmpeg_exe)
    if encoders.get("h264_nvenc"):
        return "h264_nvenc"
    if encoders.get("h264_amf"):
        return "h264_amf"
    if encoders.get("h264_qsv"):
        return "h264_qsv"
    return "libx264"

def get_encoder_display_name(encoder_name: str) -> str:
    mapping = {
        "h264_nvenc": "⚡ NVIDIA NVENC (GPU RTX 3060/5060 - Ultra Rápido)",
        "h264_amf": "⚡ AMD AMF (GPU Radeon - Ultra Rápido)",
        "h264_qsv": "⚡ Intel QuickSync (GPU Integrada)",
        "libx264": "🖥️ CPU libx264 (Processador / Alta Qualidade)",
        "auto": "Automático (Melhor Aceleração por GPU)"
    }
    return mapping.get(encoder_name, encoder_name)

if __name__ == "__main__":
    path = get_ffmpeg_path()
    print("FFmpeg Path:", path)
    encoders = probe_encoders(path)
    print("Available Encoders:", encoders)
    print("Best Encoder:", get_best_encoder(path))
