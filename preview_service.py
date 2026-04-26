from dataclasses import dataclass
from typing import Any, Callable, Optional, cast

import yt_dlp

from app_utils import (
    append_error_log,
    build_preview_text,
    fetch_url_bytes,
    pick_thumbnail_url,
    ytdlp_nocheck_certificate,
)


@dataclass(frozen=True)
class PreviewResult:
    text: str
    thumb_bytes: Optional[bytes] = None


class VideoPreviewService:
    """Encapsulates preview metadata retrieval and formatting."""

    def __init__(
        self,
        ydl_factory: Callable[..., yt_dlp.YoutubeDL] = yt_dlp.YoutubeDL,
        thumbnail_fetcher: Callable[[str, int], bytes] = fetch_url_bytes,
    ):
        self._ydl_factory = ydl_factory
        self._thumbnail_fetcher = thumbnail_fetcher

    def fetch(self, url: str) -> PreviewResult:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "extract_flat": False,
            "nocheckcertificate": ytdlp_nocheck_certificate(),
        }
        with cast(Any, self._ydl_factory(opts)) as ydl:
            info_obj = cast(Any, ydl.extract_info(url, download=False))  # type: ignore[reportUnknownMemberType]
        if not info_obj:
            raise ValueError("No metadata returned for this URL.")
        info_dict: dict[str, object] = {}
        if isinstance(info_obj, dict):
            info_dict = cast(dict[str, object], info_obj)
            entries = info_dict.get("entries")
            if isinstance(entries, list) and entries and isinstance(entries[0], dict):
                info_dict = cast(dict[str, object], entries[0])

        thumb_bytes = None
        thumb_url = pick_thumbnail_url(info_dict)
        if thumb_url:
            try:
                thumb_bytes = self._thumbnail_fetcher(thumb_url, 8)
            except Exception as thumb_fetch_exc:
                append_error_log(
                    "preview_thumbnail_fetch",
                    f"URL: {url}\nThumbnail: {thumb_url}\n{thumb_fetch_exc}",
                )

        return PreviewResult(text=build_preview_text(info_dict), thumb_bytes=thumb_bytes)
