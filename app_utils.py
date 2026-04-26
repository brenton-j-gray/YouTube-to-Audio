import ctypes
import hashlib
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import traceback
import winreg
from pathlib import Path
from types import TracebackType
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


def _try_install_certifi_ssl() -> bool:
    """Point Python's default HTTPS context at certifi's CA bundle (common Windows fix for CERTIFICATE_VERIFY_FAILED)."""
    try:
        import certifi

        def _https_context() -> ssl.SSLContext:
            return ssl.create_default_context(cafile=certifi.where())

        ssl._create_default_https_context = _https_context  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


# Set as early as possible (before any HTTPS). If False, yt-dlp uses nocheck by default; see ytdlp_nocheck_certificate.
_SSL_USES_CERTIFI = _try_install_certifi_ssl()


def _ffmpeg_binary_name(base: str) -> str:
    return f"{base}.exe" if os.name == "nt" else base


def _ffmpeg_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    script_dir = Path(__file__).resolve().parent
    dirs.append(script_dir)
    dirs.append(script_dir / "ffmpeg")
    dirs.append(script_dir / "ffmpeg" / "bin")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        dirs.append(exe_dir)
        dirs.append(exe_dir / "ffmpeg")
        dirs.append(exe_dir / "ffmpeg" / "bin")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        mp = Path(str(meipass))
        dirs.append(mp)
        dirs.append(mp / "ffmpeg")
        dirs.append(mp / "ffmpeg" / "bin")
    seen: set[str] = set()
    unique_dirs: list[Path] = []
    for d in dirs:
        s = str(d)
        if s not in seen:
            seen.add(s)
            unique_dirs.append(d)
    return unique_dirs


def bundled_ffmpeg_directory() -> Path | None:
    ffmpeg_name = _ffmpeg_binary_name("ffmpeg")
    ffprobe_name = _ffmpeg_binary_name("ffprobe")
    for d in _ffmpeg_search_dirs():
        if (d / ffmpeg_name).is_file() and (d / ffprobe_name).is_file():
            return d
    return None


def configure_ffmpeg_environment() -> Path | None:
    bundled_dir = bundled_ffmpeg_directory()
    if not bundled_dir:
        return None
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep) if current else []
    bundled_str = str(bundled_dir)
    if bundled_str not in parts:
        os.environ["PATH"] = bundled_str + (os.pathsep + current if current else "")
    return bundled_dir


def missing_ffmpeg_binaries() -> list[str]:
    """Return required ffmpeg binaries that are missing from PATH."""
    configure_ffmpeg_environment()
    required = ("ffmpeg", "ffprobe")
    return [name for name in required if shutil.which(name) is None]


def ffmpeg_help_message(missing: list[str] | None = None) -> str:
    missing = missing or missing_ffmpeg_binaries()
    missing_display = ", ".join(missing) if missing else "none"
    return (
        "Missing required media tools.\n\n"
        f"Not found on PATH: {missing_display}\n\n"
        "This app requires both ffmpeg and ffprobe.\n"
        "Install FFmpeg and make sure ffmpeg/ffprobe are available in your system PATH.\n\n"
        "Quick Windows options:\n"
        "  - winget install Gyan.FFmpeg\n"
        "  - choco install ffmpeg\n\n"
        "After installing, restart this app."
    )


def ytdlp_nocheck_certificate() -> bool:
    """
    When True, yt-dlp does not verify TLS (only when necessary). Set YT_TO_AUDIO_NO_CHECK_CERT=0 to
    force verification, or =1 to always skip. Default: skip verify only if certifi is not available.
    """
    v = os.environ.get("YT_TO_AUDIO_NO_CHECK_CERT", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return not _SSL_USES_CERTIFI


TEMP_ERROR_LOG_PATH = os.path.join(tempfile.gettempdir(), "yt_to_audio_error.log")
PROJECT_ERROR_LOG_PATH = str(Path(__file__).resolve().parent / "yt_to_audio_error.log")


def log_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> None:
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    append_error_log("uncaught_exception", details)


def append_error_log(context: str, details: str) -> None:
    payload = f"\n[{context}]\n{details}\n"
    for path in (TEMP_ERROR_LOG_PATH, PROJECT_ERROR_LOG_PATH):
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(payload)
        except OSError:
            continue


def pick_thumbnail_url(info: dict[str, object] | object) -> str | None:
    if not isinstance(info, dict):
        return None
    data = cast(dict[str, object], info)
    thumb = data.get("thumbnail")
    if isinstance(thumb, str) and thumb:
        return thumb
    thumbs = data.get("thumbnails")
    if isinstance(thumbs, list) and thumbs:
        thumb_list = cast(list[object], thumbs)
        last = thumb_list[-1]
        if isinstance(last, dict):
            last_data = cast(dict[str, object], last)
            url = last_data.get("url")
            if isinstance(url, str):
                return url
    return None


def format_duration(seconds: int | float | object) -> str:
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "Unknown"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def format_upload_date(yyyymmdd: str | int | None) -> str:
    if not yyyymmdd or len(str(yyyymmdd)) != 8:
        return "Unknown"
    s = str(yyyymmdd)
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def format_view_count(count: int | object) -> str:
    if not isinstance(count, int) or count < 0:
        return "Unknown"
    return f"{count:,}"


def build_preview_text(info: dict[str, object] | object) -> str:
    if not isinstance(info, dict):
        return "Preview unavailable."
    data = cast(dict[str, object], info)
    title_val = data.get("title")
    title = title_val if isinstance(title_val, str) and title_val else "Unknown title"
    uploader_val = data.get("uploader")
    channel_val = data.get("channel")
    uploader = uploader_val if isinstance(uploader_val, str) and uploader_val else (
        channel_val if isinstance(channel_val, str) and channel_val else "Unknown channel"
    )
    duration = format_duration(data.get("duration"))
    views = format_view_count(data.get("view_count"))
    upload_raw = data.get("upload_date")
    upload_date = format_upload_date(upload_raw if isinstance(upload_raw, (str, int)) else None)
    live = "Yes" if bool(data.get("is_live")) else "No"
    age_limit = data.get("age_limit")
    age_restricted = "Yes" if isinstance(age_limit, (int, float)) and age_limit >= 18 else "No"
    webpage_val = data.get("webpage_url")
    original_val = data.get("original_url")
    webpage_url = webpage_val if isinstance(webpage_val, str) and webpage_val else (
        original_val if isinstance(original_val, str) and original_val else "Unknown"
    )
    short_source = webpage_url if len(webpage_url) <= 70 else f"{webpage_url[:67]}..."
    return (
        f"{title}\n"
        f"Channel: {uploader}\n"
        f"Duration: {duration}   Views: {views}\n"
        f"Uploaded: {upload_date}   Live: {live}   18+: {age_restricted}\n"
        f"Source: {short_source}"
    )


def is_safe_http_url(url: object) -> bool:
    """Allow only http(s) fetches; blocks file:, data:, and other schemes (SSRF hardening)."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    return True


# Cap thumbnail fetches to avoid unbounded memory use on malicious Content-Length/streams.
_MAX_URL_FETCH_BYTES = 10 * 1024 * 1024


def _read_response_body_limited(response: Any, max_bytes: int) -> bytes:
    out = bytearray()
    while len(out) < max_bytes:
        chunk = response.read(min(65536, max_bytes - len(out)))
        if not chunk:
            break
        out.extend(chunk)
    return bytes(out)


def fetch_url_bytes(url: str, timeout: int = 8, max_bytes: int = _MAX_URL_FETCH_BYTES) -> bytes:
    if not is_safe_http_url(url):
        raise ValueError("Only http(s) URLs are allowed for downloads.")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout) as r:
            return _read_response_body_limited(r, max_bytes)
    except Exception as first_exc:
        # Retry with unverified SSL for users with local trust-store issues.
        try:
            insecure_ctx = ssl._create_unverified_context()  # type: ignore[attr-defined]
            with urlopen(req, timeout=timeout, context=insecure_ctx) as r:
                return _read_response_body_limited(r, max_bytes)
        except Exception:
            raise first_exc


def expected_wav_path(info_dict: object, ydl: Any) -> Path:
    if isinstance(info_dict, dict):
        info_data = cast(dict[str, object], info_dict)
        entries = info_data.get("entries")
        if isinstance(entries, list) and entries:
            info_dict = cast(object, entries[0])
    downloaded_path = Path(ydl.prepare_filename(cast(Any, info_dict)))
    return downloaded_path.with_suffix(".wav")


def normalize_youtube_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = parse_qs(parsed.query)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"} and parsed.path == "/watch":
        query = {k: v for k, v in query.items() if k == "v"}
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    if host == "youtu.be":
        return urlunparse(parsed._replace(query=""))
    return url.strip()


def is_supported_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            return bool(parse_qs(parsed.query).get("v"))
        return parsed.path.startswith("/shorts/") or parsed.path.startswith("/live/")
    if host == "youtu.be":
        return bool(parsed.path.strip("/"))
    return False


def open_folder(path: str | Path) -> None:
    subprocess.Popen(["explorer", str(path)])


def error_log_path_candidates() -> list[Path]:
    return [Path(PROJECT_ERROR_LOG_PATH), Path(TEMP_ERROR_LOG_PATH)]


def open_error_log_externally() -> None:
    """Open the first available error log in the system default viewer, or create the project log."""
    for p in error_log_path_candidates():
        if p.is_file():
            try:
                os.startfile(p)  # type: ignore[attr-defined]
            except (OSError, AttributeError):
                try:
                    subprocess.Popen(["explorer", str(p)])
                except OSError:
                    pass
            return
    try:
        Path(PROJECT_ERROR_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        Path(PROJECT_ERROR_LOG_PATH).touch()
        os.startfile(Path(PROJECT_ERROR_LOG_PATH))  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        pass


def reveal_in_explorer(path: str | Path) -> None:
    """Select a file in Windows Explorer, or open a directory."""
    try:
        p = Path(path).resolve()
    except (OSError, TypeError, ValueError):
        return
    if p.is_file():
        subprocess.Popen(["explorer", "/select,", str(p)])
    elif p.is_dir():
        open_folder(p)


def is_windows_dark_mode() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
    except OSError:
        return False


def ensure_taskbar_presence(window: Any) -> None:
    try:
        gwl_exstyle = -20
        ws_ex_toolwindow = 0x00000080
        ws_ex_appwindow = 0x00040000
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, gwl_exstyle)
        style = (style & ~ws_ex_toolwindow) | ws_ex_appwindow
        ctypes.windll.user32.SetWindowLongW(hwnd, gwl_exstyle, style)
        window.withdraw()
        window.after(10, window.deiconify)
    except Exception:
        pass


def thumbnail_cache_paths(thumb_bytes: bytes) -> tuple[str, str]:
    digest = hashlib.sha1(thumb_bytes).hexdigest()[:12]
    in_path = os.path.join(tempfile.gettempdir(), f"yt_to_audio_thumb_{digest}.jpg")
    out_path = os.path.join(tempfile.gettempdir(), f"yt_to_audio_thumb_{digest}.png")
    return in_path, out_path
