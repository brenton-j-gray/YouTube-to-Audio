from pathlib import Path
from typing import Any, Callable, cast

import yt_dlp  # type: ignore[reportMissingTypeStubs]

from app_utils import configure_ffmpeg_environment, expected_wav_path, normalize_youtube_url, ytdlp_nocheck_certificate


class Converter:
    QUALITY_MAP = {
        "High (320 kbps)": "320",
        "Medium (192 kbps)": "192",
        "Low (128 kbps)": "128",
    }
    FORMAT_MAP = {
        "WAV (44.1kHz 16-bit stereo)": "wav",
        "MP3": "mp3",
        "M4A (AAC)": "m4a",
        "FLAC": "flac",
        "OPUS": "opus",
    }
    LOSSLESS_FORMATS = {"wav", "flac"}

    def __init__(
        self,
        url: str,
        out_dir: str | Path,
        quality_key: str,
        format_key: str,
        on_progress: Callable[[float], None],
        on_status: Callable[[str], None],
        on_done: Callable[[bool, str], None],
    ) -> None:
        self.url = url.strip()
        self.out_dir = Path(out_dir)
        self.quality = self.QUALITY_MAP.get(quality_key, "192")
        self.codec = self.FORMAT_MAP.get(format_key, "wav")
        self.on_progress = on_progress
        self.on_status = on_status
        self.on_done = on_done
        self._stop = False

    def cancel(self) -> None:
        self._stop = True

    def _progress_hook(self, data: dict[str, Any]) -> None:
        if self._stop:
            raise yt_dlp.utils.DownloadError("Cancelled")
        status = data.get("status")
        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 1
            pct = min(data.get("downloaded_bytes", 0) / total * 88, 88)
            self.on_progress(pct)
            self.on_status(f"Downloading… {data.get('_speed_str', '').strip()}")
        elif status == "finished":
            self.on_progress(90)
            self.on_status(f"Converting to {self.codec.upper()}…")

    def _build_postprocessor(self) -> dict[str, str]:
        postprocessor: dict[str, str] = {"key": "FFmpegExtractAudio", "preferredcodec": self.codec}
        if self.codec not in self.LOSSLESS_FORMATS:
            postprocessor["preferredquality"] = self.quality
        return postprocessor

    def _build_ydl_options(self) -> dict[str, Any]:
        bundled_ffmpeg_dir = configure_ffmpeg_environment()
        opts = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "outtmpl": str(self.out_dir / "%(title)s.%(ext)s"),
            "postprocessors": [
                self._build_postprocessor(),
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail"},
            ],
            "postprocessor_args": ["-ar", "44100", "-ac", "2", "-sample_fmt", "s16"] if self.codec == "wav" else [],
            "audio_quality": self.quality,
            "progress_hooks": [self._progress_hook],
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": ytdlp_nocheck_certificate(),
            "overwrites": False,
        }
        if bundled_ffmpeg_dir:
            opts["ffmpeg_location"] = str(bundled_ffmpeg_dir)
        if self.codec in self.LOSSLESS_FORMATS:
            opts.pop("audio_quality", None)
        return opts

    def _resolve_output_path(self, info: Any, ydl: Any) -> Path:
        output_audio = expected_wav_path(info, ydl).with_suffix(f".{self.codec}")
        if output_audio.exists():
            return output_audio
        converted = sorted(
            self.out_dir.glob(f"*.{self.codec}"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not converted:
            raise FileNotFoundError(f"{self.codec.upper()} not found after conversion.")
        return converted[0]

    def _handle_download_error(self, err: str) -> None:
        err_lower = err.lower()
        if "cancelled" in err_lower:
            self.on_done(False, "Cancelled by user.")
        elif "ffmpeg" in err_lower or "ffprobe" in err_lower:
            self.on_done(
                False,
                "FFmpeg was not found. Install FFmpeg and ensure ffmpeg/ffprobe are on PATH.",
            )
        else:
            self.on_done(False, err)

    def run(self) -> None:
        self.url = normalize_youtube_url(self.url)
        opts = self._build_ydl_options()
        try:
            with cast(Any, yt_dlp.YoutubeDL(opts)) as ydl:
                info = cast(Any, ydl.extract_info(self.url, download=True))  # type: ignore[reportUnknownMemberType]
                saved_path = self._resolve_output_path(info, ydl)
            self.on_progress(100)
            self.on_done(True, str(saved_path))
        except yt_dlp.utils.DownloadError as e:
            self._handle_download_error(str(e))
        except Exception as e:
            if not self._stop:
                self.on_done(False, str(e))
