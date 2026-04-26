#!/usr/bin/env python3
"""
YouTube -> Audio File Converter
Outputs an audio file (WAV, MP3, M4A, FLAC, OPUS).

GUI MODE  : python yt_to_audio.pyw
CLI MODE  : python yt_to_audio.pyw <url> [output_directory]
"""

import sys
from tkinter import messagebox
from pathlib import Path
from typing import Any, cast

from app_utils import ffmpeg_help_message, log_exception, missing_ffmpeg_binaries
from cli_app import cli
from gui_app import launch_gui

sys.excepthook = log_exception


if __name__ == "__main__":
    missing_tools = missing_ffmpeg_binaries()
    if missing_tools:
        msg = ffmpeg_help_message(missing_tools)
        if len(sys.argv) >= 2:
            print(msg, file=sys.stderr)
        else:
            try:
                cast(Any, messagebox).showerror("FFmpeg not found", msg)
            except Exception:
                print(msg, file=sys.stderr)
        sys.exit(1)

    if len(sys.argv) >= 2:
        cli(sys.argv[1], sys.argv[2] if len(sys.argv) >= 3 else str(Path.cwd()))
    else:
        launch_gui()
