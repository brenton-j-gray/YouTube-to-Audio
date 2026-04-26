"""Persistent GUI preferences (JSON in local app data)."""

import json
import os
from pathlib import Path
from typing import Any, Optional, cast

from converter_core import Converter

VERSION = 1
MAX_RECENT_FOLDERS = 8
DEBOUNCE_CHOICES = (300, 500, 650, 1000)


def _config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        d = Path(base) / "YouTubeToAudio"
    else:
        d = Path.home() / ".config" / "youtube-to-audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_path() -> Path:
    return _config_dir() / "settings.json"


def _default_output_dir() -> str:
    return str(Path.home() / "Downloads")


def _valid_format(key: str) -> bool:
    return key in Converter.FORMAT_MAP


def _valid_quality(key: str) -> bool:
    return key in Converter.QUALITY_MAP


def _valid_debounce(n: int) -> int:
    if n in DEBOUNCE_CHOICES:
        return n
    return 650


def _defaults() -> dict[str, Any]:
    return {
        "version": VERSION,
        "theme": "system",
        "default_output_dir": _default_output_dir(),
        "recent_folders": [],
        "format": "WAV (44.1kHz 16-bit stereo)",
        "quality": "Medium (192 kbps)",
        "auto_open_folder": True,
        "play_after_download": False,
        "force_remain_on_top": False,
        "auto_preview": True,
        "preview_debounce_ms": 650,
        "last_download_path": None,
        "window_geometry": None,
    }


def _normalize(loaded: dict[str, Any]) -> dict[str, Any]:
    d = _defaults()
    for k, v in loaded.items():
        if k in d and v is not None:
            d[k] = v
    d["version"] = VERSION
    d["format"] = loaded.get("format", d["format"])
    d["quality"] = loaded.get("quality", d["quality"])
    if not _valid_format(d["format"]):
        d["format"] = _defaults()["format"]
    if not _valid_quality(d["quality"]):
        d["quality"] = _defaults()["quality"]
    d["theme"] = loaded.get("theme", "system")
    if d["theme"] not in ("system", "light", "dark"):
        d["theme"] = "system"
    d["default_output_dir"] = str(loaded.get("default_output_dir") or d["default_output_dir"])
    rf: object = cast(object, loaded.get("recent_folders"))
    if not isinstance(rf, list):
        rf = []
    rf = cast(list[object], rf)
    out_rf: list[str] = []
    for p in rf:
        if not isinstance(p, str):
            continue
        try:
            pr = Path(p)
        except (OSError, TypeError, ValueError):
            continue
        if pr.is_dir():
            out_rf.append(str(pr.resolve()))
    d["recent_folders"] = out_rf[:MAX_RECENT_FOLDERS]
    d["auto_open_folder"] = bool(loaded.get("auto_open_folder", True))
    d["play_after_download"] = bool(loaded.get("play_after_download", False))
    d["force_remain_on_top"] = bool(loaded.get("force_remain_on_top", False))
    d["auto_preview"] = bool(loaded.get("auto_preview", True))
    d["preview_debounce_ms"] = _valid_debounce(
        int(loaded.get("preview_debounce_ms", 650) or 650)
    )
    lp = loaded.get("last_download_path")
    if isinstance(lp, str) and lp:
        try:
            p = Path(lp)
            d["last_download_path"] = str(p) if p.is_file() else None
        except (OSError, TypeError, ValueError):
            d["last_download_path"] = None
    else:
        d["last_download_path"] = None
    geo = loaded.get("window_geometry")
    d["window_geometry"] = geo if isinstance(geo, str) and geo else None
    return d


def load() -> dict[str, Any]:
    path = settings_path()
    if not path.is_file():
        return _defaults()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _defaults()
        return _normalize(cast(dict[str, Any], data))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return _defaults()


def save(
    *,
    theme: str,
    default_output_dir: str,
    recent_folders: list[str],
    format_key: str,
    quality_key: str,
    auto_open_folder: bool,
    play_after_download: bool,
    force_remain_on_top: bool,
    auto_preview: bool,
    preview_debounce_ms: int,
    last_download_path: Optional[str],
    window_geometry: Optional[str],
) -> None:
    d = {
        "version": VERSION,
        "theme": theme,
        "default_output_dir": default_output_dir,
        "recent_folders": recent_folders[:MAX_RECENT_FOLDERS],
        "format": format_key if _valid_format(format_key) else _defaults()["format"],
        "quality": quality_key if _valid_quality(quality_key) else _defaults()["quality"],
        "auto_open_folder": auto_open_folder,
        "play_after_download": play_after_download,
        "force_remain_on_top": force_remain_on_top,
        "auto_preview": auto_preview,
        "preview_debounce_ms": _valid_debounce(preview_debounce_ms),
        "last_download_path": last_download_path,
        "window_geometry": window_geometry,
    }
    path = settings_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
    except OSError:
        pass


def bump_recent(recent: list[str], folder: str) -> list[str]:
    try:
        p = str(Path(folder).resolve())
    except (OSError, TypeError, ValueError):
        return recent
    if not Path(p).is_dir():
        return recent
    nxt = [x for x in recent if x != p]
    nxt.insert(0, p)
    return nxt[:MAX_RECENT_FOLDERS]
