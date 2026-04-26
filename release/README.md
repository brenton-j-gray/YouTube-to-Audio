# YouTube to Audio (Python)

Convert YouTube videos to audio files with a desktop GUI or CLI.

Supported output formats:
- WAV
- MP3
- M4A
- FLAC
- OPUS

## Features

- Clean Tkinter GUI with progress and status updates
- CLI mode for quick terminal workflows
- Video metadata preview (title, channel, duration, views, upload date)
- Thumbnail preview support
- Configurable output format/quality
- Persistent user settings (theme, recent folders, preview behavior, etc.)
- Cancelable downloads/conversions

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` available on your system `PATH`
- Python packages in `requirements.txt`

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

## Usage

### GUI

```bash
python yt_to_audio.pyw
```

### CLI

```bash
python yt_to_audio.pyw "https://www.youtube.com/watch?v=VIDEO_ID" "C:/path/to/output"
```

If `output_directory` is omitted, CLI uses the current working directory.

## Project Structure

- `yt_to_audio.pyw` - app entry point (GUI/CLI dispatch)
- `gui_app.py` - desktop GUI
- `cli_app.py` - CLI wrapper
- `converter_core.py` - conversion engine
- `preview_service.py` - metadata/thumbnail preview service
- `user_settings.py` - persisted settings
- `app_utils.py` - shared helpers (URL, SSL, logging, explorer ops)
- `requirements.txt` - Python dependencies

## Notes

- This project depends on `yt-dlp` behavior and YouTube site changes. Keeping `yt-dlp` updated is recommended.
- On Windows, app settings are stored in `%LOCALAPPDATA%\\YouTubeToAudio\\settings.json`.

## Troubleshooting

- **FFmpeg not found**
  - Install FFmpeg and ensure both `ffmpeg` and `ffprobe` are on `PATH`.
- **TLS/certificate errors**
  - Install/update dependencies: `python -m pip install -r requirements.txt`
  - If needed, update certifi: `python -m pip install -U certifi`

## Build a release (Windows)

Create a standalone executable and release zip:

```powershell
./build_release.ps1
```

Artifacts:
- `dist/YouTubeToAudio.exe` (raw PyInstaller output)
- `release/YouTubeToAudio.exe` (copied for distribution)
- `release/YouTubeToAudio-windows-x64.zip` (ready to share)

Optional self-contained FFmpeg packaging:
- Put `ffmpeg.exe` and `ffprobe.exe` in a local `ffmpeg/` folder at the project root.
- Run `./build_release.ps1` as usual; the script auto-bundles that folder.
- At runtime, the app auto-detects bundled ffmpeg binaries and uses them (no system PATH requirement).

## Disclaimer

Use responsibly and comply with YouTube's Terms of Service and applicable copyright laws.
