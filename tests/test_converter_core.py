from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from converter_core import Converter


def _noop_progress(_: float) -> None:
    pass


def _noop_status(_: str) -> None:
    pass


def _noop_done(_: bool, __: str) -> None:
    pass


class ConverterYtDlpOptionTests(TestCase):
    def _converter(self) -> Converter:
        return Converter(
            "https://www.youtube.com/watch?v=test",
            Path("."),
            "Medium (192 kbps)",
            "WAV (44.1kHz 16-bit stereo)",
            _noop_progress,
            _noop_status,
            _noop_done,
        )

    def test_browser_cookies_are_disabled_by_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            opts = self._converter()._build_ydl_options()

        self.assertNotIn("cookiesfrombrowser", opts)

    def test_browser_cookies_are_used_when_configured(self) -> None:
        with patch.dict("os.environ", {"YT_TO_AUDIO_COOKIES_FROM_BROWSER": "chrome"}):
            opts = self._converter()._build_ydl_options()

        self.assertEqual(opts["cookiesfrombrowser"], ("chrome", None, None, None))
