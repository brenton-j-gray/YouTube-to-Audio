---
name: cloud-agent-run-and-test
description: Practical setup, execution, and testing workflows for Cloud agents working on this YouTube-to-audio Python app.
---

# Cloud agent run and test guide

Use this skill when you need to run, debug, or test this repository in Cursor Cloud.

## Whole repo setup

- Start from the repository root: `/workspace`.
- Use Python 3.10 or newer. In Cursor Cloud this may be `python3`; if `python` is missing, replace `python` with `python3` in commands.
- Install Python dependencies:
  - `python3 -m pip install -r requirements.txt`
- Ensure media tools are available before launching the app:
  - `ffmpeg -version`
  - `ffprobe -version`
- If system FFmpeg is unavailable, put binaries in one of the app's auto-detected locations:
  - `./ffmpeg/ffmpeg` and `./ffmpeg/ffprobe`
  - `./ffmpeg/bin/ffmpeg` and `./ffmpeg/bin/ffprobe`
- No product login is required for the app. YouTube itself may block or rate-limit unauthenticated extraction, so prefer mocked tests for converter and preview behavior unless the task specifically requires a live site check.
- Useful environment toggles:
  - `YT_TO_AUDIO_NO_CHECK_CERT=0` forces normal TLS verification.
  - `YT_TO_AUDIO_NO_CHECK_CERT=1` skips certificate verification for yt-dlp troubleshooting.
  - `YT_TO_AUDIO_DONATE_URL=http://127.0.0.1:9` prevents the Donate button from opening the real payment URL during GUI tests.
- GUI settings are stored at `~/.config/youtube-to-audio/settings.json` on Linux Cloud agents. Delete or rewrite this file when you need a clean GUI state.
- Runtime error logs may be written to `/tmp/yt_to_audio_error.log` and `./yt_to_audio_error.log`.
- Current Linux Cloud note: if importing `app_utils.py` fails with `ModuleNotFoundError: No module named 'winreg'`, the Windows registry import needs to be guarded before CLI or GUI runtime tests can execute on Linux.

## CLI area

Files: `yt_to_audio.pyw`, `cli_app.py`, `converter_core.py`, `app_utils.py`.

Run the CLI:

- `python3 yt_to_audio.pyw "https://www.youtube.com/watch?v=VIDEO_ID" /tmp/yt-to-audio-output`

Recommended CLI testing workflow:

1. Verify startup prerequisites with `ffmpeg -version`, `ffprobe -version`, and `app_utils.missing_ffmpeg_binaries()` once `app_utils.py` imports successfully on Linux.
2. For unit-style tests, mock `yt_dlp.YoutubeDL` and test `Converter.run()` without network access.
3. Use a temporary output directory and create a fake converted file before `_resolve_output_path()` assertions.
4. Run `python3 -m compileall -q yt_to_audio.pyw cli_app.py converter_core.py app_utils.py preview_service.py user_settings.py gui_app.py` after edits.
5. Only run a live YouTube conversion when the request explicitly needs one; live extraction depends on external site behavior, network access, and rate limits.

## GUI area

Files: `gui_app.py`, `user_settings.py`, `preview_service.py`, `converter_core.py`, `app_utils.py`.

Run the GUI in Cloud:

- `python3 yt_to_audio.pyw`

Recommended GUI testing workflow:

1. Use the `computerUse` subagent for manual GUI testing.
2. If the display is not already available, run through an X virtual display such as `xvfb-run -a python3 yt_to_audio.pyw`.
3. Set `YT_TO_AUDIO_DONATE_URL=http://127.0.0.1:9` before launching when testing the Donate button.
4. Seed or clear `~/.config/youtube-to-audio/settings.json` to test themes, recent folders, auto preview, topmost, and saved output directories.
5. Prefer monkeypatching `VideoPreviewService` and `Converter` for repeatable GUI tests; live preview/download flows depend on YouTube and yt-dlp.
6. Capture a short screen recording for user-visible GUI changes.

## Preview and thumbnail area

Files: `preview_service.py`, `app_utils.py`.

Recommended testing workflow:

1. Mock the `ydl_factory` argument to `VideoPreviewService` with a context manager that returns fixed metadata.
2. Mock `thumbnail_fetcher` to return small byte strings or raise exceptions.
3. Cover playlist-like metadata by returning an `entries` list with one dict.
4. Test formatting helpers in `app_utils.py` directly for duration, upload date, view count, thumbnail selection, URL safety, and preview text.
5. Avoid live thumbnail fetches unless the task is specifically about HTTP behavior.

## Settings area

Files: `user_settings.py`.

Recommended testing workflow:

1. Isolate state by setting `HOME` to a temporary directory before importing or invoking settings code.
2. Validate `load()` against missing files, invalid JSON, invalid enum values, and nonexistent recent folders.
3. Validate `save()` and `bump_recent()` with real temporary directories.
4. On Linux Cloud agents, expected settings path is `$HOME/.config/youtube-to-audio/settings.json`.

## Release and CI area

Files: `build_release.ps1`, `.github/workflows/bandit.yml`, `release/README.md`.

Recommended testing workflow:

1. For Python source changes, run compile checks locally.
2. For security-sensitive changes, run Bandit if available: `python3 -m bandit -r . -x .venv,typings,release`.
3. Treat `build_release.ps1` as the Windows packaging path. It installs requirements, installs PyInstaller, optionally bundles `./ffmpeg`, and writes `dist/` plus `release/` artifacts.
4. Do not rebuild or commit packaged release artifacts unless the task explicitly asks for a release build.

## Updating this skill

- Add new run commands, environment variables, mock patterns, and failure fixes as soon as they are learned during real work.
- Keep entries short and copy-pasteable.
- Put instructions in the relevant codebase area instead of adding a long general checklist.
- Remove stale workarounds once the codebase no longer needs them.
