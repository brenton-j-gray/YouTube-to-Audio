import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import app_utils


class ExternalPathTests(TestCase):
    def test_open_folder_uses_linux_file_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(app_utils.os, "name", "posix"), patch.object(sys, "platform", "linux"):
                with patch.object(app_utils.shutil, "which", return_value="/usr/bin/xdg-open"):
                    with patch.object(app_utils.subprocess, "Popen") as popen:
                        app_utils.open_folder(Path(tmp_dir))

        popen.assert_called_once_with(["/usr/bin/xdg-open", str(Path(tmp_dir).resolve())])

    def test_open_folder_ignores_missing_linux_file_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.object(app_utils.os, "name", "posix"), patch.object(sys, "platform", "linux"):
                with patch.object(app_utils.shutil, "which", return_value=None):
                    with patch.object(app_utils.subprocess, "Popen") as popen:
                        app_utils.open_folder(Path(tmp_dir))

        popen.assert_not_called()

    def test_reveal_file_uses_parent_directory_on_linux(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "download.wav"
            path.touch()
            with patch.object(app_utils.os, "name", "posix"), patch.object(sys, "platform", "linux"):
                with patch.object(app_utils.shutil, "which", return_value="/usr/bin/xdg-open"):
                    with patch.object(app_utils.subprocess, "Popen") as popen:
                        app_utils.reveal_in_explorer(path)

        popen.assert_called_once_with(["/usr/bin/xdg-open", str(path.parent.resolve())])
