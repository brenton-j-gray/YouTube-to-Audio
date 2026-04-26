#!/usr/bin/env python3
"""
YouTube -> Audio File Converter
Outputs an audio file (WAV, MP3, M4A, FLAC, OPUS).

GUI MODE  : python yt_to_audio.pyw
CLI MODE  : python yt_to_audio.pyw <url> [output_directory]
"""

import sys
from pathlib import Path

from app_utils import log_exception
from cli_app import cli
from gui_app import launch_gui

sys.excepthook = log_exception


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        cli(sys.argv[1], sys.argv[2] if len(sys.argv) >= 3 else str(Path.cwd()))
    else:
        launch_gui()
