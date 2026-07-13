import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import app_utils


class ExternalPathTests(TestCase):
    def test_open_folder_uses_linux_file_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(sys, "platform", "linux"):
                with patch.object(app_utils.shutil, "which", return_value="/usr/bin/xdg-open"):
                    with patch.object(app_utils.subprocess, "Popen") as popen:
                        app_utils.open_folder(Path(tmp_dir))

        popen.assert_called_once_with(["/usr/bin/xdg-open", str(Path(tmp_dir).resolve())])

    def test_open_folder_ignores_missing_linux_file_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(sys, "platform", "linux"):
                with patch.object(app_utils.shutil, "which", return_value=None):
                    with patch.object(app_utils.subprocess, "Popen") as popen:
                        app_utils.open_folder(Path(tmp_dir))

        popen.assert_not_called()

    def test_reveal_file_uses_parent_directory_on_linux(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "download.wav"
            path.touch()
            with patch.object(sys, "platform", "linux"):
                with patch.object(app_utils.shutil, "which", return_value="/usr/bin/xdg-open"):
                    with patch.object(app_utils.subprocess, "Popen") as popen:
                        app_utils.reveal_in_explorer(path)

        popen.assert_called_once_with(["/usr/bin/xdg-open", str(path.parent.resolve())])


class YtDlpCookieOptionTests(TestCase):
    def test_default_cookiesfrombrowser_is_disabled(self) -> None:
        with patch.dict(app_utils.os.environ, {}, clear=True):
            self.assertIsNone(app_utils.ytdlp_cookies_from_browser())

    def test_cookiesfrombrowser_can_be_overridden(self) -> None:
        with patch.dict(app_utils.os.environ, {"YT_TO_AUDIO_COOKIES_FROM_BROWSER": "chrome"}):
            self.assertEqual(app_utils.ytdlp_cookies_from_browser(), ("chrome", None, None, None))

    def test_cookiesfrombrowser_accepts_profile_spec(self) -> None:
        with patch.dict(
            app_utils.os.environ,
            {"YT_TO_AUDIO_COOKIES_FROM_BROWSER": "firefox:default-release::personal"},
        ):
            self.assertEqual(
                app_utils.ytdlp_cookies_from_browser(),
                ("firefox", "default-release", None, "personal"),
            )

    def test_cookiesfrombrowser_can_be_disabled(self) -> None:
        with patch.dict(app_utils.os.environ, {"YT_TO_AUDIO_COOKIES_FROM_BROWSER": "0"}):
            self.assertIsNone(app_utils.ytdlp_cookies_from_browser())

    def test_cookie_load_errors_are_detected(self) -> None:
        self.assertTrue(app_utils.is_ytdlp_cookie_error("failed to load cookies"))
        self.assertTrue(app_utils.is_ytdlp_cookie_error("Failed to decrypt with DPAPI"))
        self.assertFalse(app_utils.is_ytdlp_cookie_error("video unavailable"))
