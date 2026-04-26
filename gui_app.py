import ctypes
import os
import platform
import re
import subprocess
import sys
import threading
import traceback
import webbrowser
from io import BytesIO
from pathlib import Path
from typing import Any, TypedDict, cast

import user_settings
from app_utils import (
    append_error_log,
    ensure_taskbar_presence,
    is_supported_youtube_url,
    is_windows_dark_mode,
    normalize_youtube_url,
    open_error_log_externally,
    open_folder,
    reveal_in_explorer,
    thumbnail_cache_paths,
)
from converter_core import Converter
from preview_service import VideoPreviewService

DONATE_URL = os.environ.get("YT_TO_AUDIO_DONATE_URL", "https://www.paypal.com/ncp/payment/HRT6GEDYUBZ5C")
QR_CODE_PATH = Path(__file__).resolve().parent / "payment-qrcode.png"

Image: Any = None
ImageTk: Any = None
pil_available = False
try:
    from PIL import Image, ImageTk  # type: ignore[reportMissingImports]

    pil_available = True
except Exception:
    pil_available = False


class Palette(TypedDict):
    APP_IS_DARK: bool
    ACCENT: str
    BG: str
    SURF: str
    FG: str
    MUTED: str
    BORDER: str
    BTN_ACTIVE: str
    NEUTRAL_BTN_BG: str
    NEUTRAL_BTN_FG: str
    NEUTRAL_BTN_ACTIVE: str
    ON_ACCENT: str


class DragState(TypedDict):
    x: int
    y: int
    active: bool


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) != 6:
        return (0, 0, 0)
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"


def _blend_hex(c1: str, c2: str, t: float) -> str:
    a = _hex_to_rgb(c1)
    b = _hex_to_rgb(c2)
    return _rgb_to_hex(
        (
            int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t),
        )
    )


def launch_gui() -> None:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import filedialog, messagebox, ttk
    show_info = cast(Any, messagebox.showinfo)
    show_warning = cast(Any, messagebox.showwarning)
    show_error = cast(Any, messagebox.showerror)

    def palette_for_mode(dark: bool) -> Palette:
        accent = "#cc0000" if dark else "#d60000"
        if dark:
            return {
                "APP_IS_DARK": True,
                "ACCENT": accent,
                "BG": "#1a1a1a",
                "SURF": "#000000",
                "FG": "#f0f0f0",
                "MUTED": "#b8b8b8",
                "BORDER": "#6a6a6a",
                "BTN_ACTIVE": "#404040",
                "NEUTRAL_BTN_BG": "#8f8f8f",
                "NEUTRAL_BTN_FG": "#111111",
                "NEUTRAL_BTN_ACTIVE": "#7a7a7a",
                "ON_ACCENT": "#ffffff",
            }
        return {
            "APP_IS_DARK": False,
            "ACCENT": accent,
            "BG": "#e9edf1",
            "SURF": "#f2f3f5",
            "FG": "#555555",
            "MUTED": "#3f3f3f",
            "BORDER": "#a9adb3",
            "BTN_ACTIVE": "#e2e6ea",
            "NEUTRAL_BTN_BG": "#d7d7d7",
            "NEUTRAL_BTN_FG": "#111111",
            "NEUTRAL_BTN_ACTIVE": "#c6c6c6",
            "ON_ACCENT": "#ffffff",
        }

    palette = palette_for_mode(is_windows_dark_mode())
    label_widgets: list[Any] = []
    preview_service = VideoPreviewService()

    ACCENT = palette["ACCENT"]
    app_is_dark = palette["APP_IS_DARK"]
    BG = palette["BG"]
    SURF = palette["SURF"]
    FG = palette["FG"]
    MUTED = palette["MUTED"]
    BORDER = palette["BORDER"]
    BTN_ACTIVE = palette["BTN_ACTIVE"]
    NEUTRAL_BTN_BG = palette["NEUTRAL_BTN_BG"]
    NEUTRAL_BTN_FG = palette["NEUTRAL_BTN_FG"]
    NEUTRAL_BTN_ACTIVE = palette["NEUTRAL_BTN_ACTIVE"]
    ON_ACCENT = palette["ON_ACCENT"]
    ROUNDNESS = 8
    BTN_PAD_X = ROUNDNESS + 4
    BTN_PAD_Y = max(5, ROUNDNESS // 2 + 1)
    FIELD_PAD_X = ROUNDNESS + 2
    FIELD_PAD_Y = max(5, ROUNDNESS // 2 + 2)
    INLINE_PAD_X = ROUNDNESS + 2
    INLINE_PAD_Y = max(5, ROUNDNESS // 2 + 1)
    COMBO_PAD_Y = max(3, ROUNDNESS // 2)
    PROGRESS_THICKNESS = max(10, ROUNDNESS + 4)
    PROGRESS_PAD_Y = max(2, ROUNDNESS // 2)
    BORDER_STYLE = {
        "accent_thickness": 2,
        "side_accent_thickness": 2,
        "control_thickness": 1,
        "menu_popup_border_width": 0,
        "menu_popup_active_border_width": 0,
        "menu_button_thickness": 0,
    }
    FONT_FAMILY = "Segoe UI"
    TITLE_FONT = (FONT_FAMILY, 24, "bold")
    SUBTITLE_FONT = (FONT_FAMILY, 12)
    SECTION_LABEL_FONT = (FONT_FAMILY, 10, "bold")
    BODY_LABEL_FONT = (FONT_FAMILY, 11)
    SMALL_LABEL_FONT = (FONT_FAMILY, 9)

    root = tk.Tk()
    root.title("YouTube-2-Audio")
    root.resizable(False, False)
    root.configure(bg=BG)
    root.overrideredirect(True)

    def register_preferred_title_font() -> None:
        preferred = Path(__file__).resolve().parent / "Frijole-Regular.ttf"
        if not preferred.is_file() or not sys.platform.startswith("win"):
            return
        try:
            fr_private = 0x10
            ctypes.windll.gdi32.AddFontResourceExW(str(preferred), fr_private, 0)
            hwnd_broadcast = 0xFFFF
            wm_fontchange = 0x001D
            ctypes.windll.user32.SendMessageW(hwnd_broadcast, wm_fontchange, 0, 0)
        except Exception:
            pass

    register_preferred_title_font()
    families = {f.lower() for f in tkfont.families(root)}
    if "frijole" in families:
        TITLE_FONT = ("Frijole", 30, "normal")
    else:
        TITLE_FONT = (FONT_FAMILY, 24, "bold")

    saved = user_settings.load()
    force_topmost_var = tk.BooleanVar(master=root, value=bool(saved.get("force_remain_on_top", False)))
    root.attributes("-topmost", force_topmost_var.get())
    last_download_path = [saved.get("last_download_path")]
    if last_download_path[0] and not Path(last_download_path[0]).is_file():
        last_download_path[0] = None
    recent_folders_state = [list(saved.get("recent_folders") or [])]

    def _valid_start_dir(s: str) -> str:
        try:
            p = Path(s)
        except (OSError, TypeError, ValueError):
            return str(Path.home() / "Downloads")
        return s if p.is_dir() else str(Path.home() / "Downloads")

    theme_mode_var = tk.StringVar(master=root, value=saved.get("theme", "system"))
    _persist_job: list[str | None] = [None]
    _cv: list[Converter | None] = [None]
    _drag: DragState = {"x": 0, "y": 0, "active": False}

    def can_drag_from(widget: Any) -> bool:
        return widget.winfo_class() in {"Tk", "Frame", "TFrame", "Label"}

    def begin_drag(event: Any) -> None:
        if not can_drag_from(event.widget):
            _drag["active"] = False
            return
        _drag["active"] = True
        _drag["x"] = event.x_root - root.winfo_x()
        _drag["y"] = event.y_root - root.winfo_y()

    def do_drag(event: Any) -> None:
        if not _drag["active"]:
            return
        x = event.x_root - _drag["x"]
        y = event.y_root - _drag["y"]
        root.geometry(f"+{x}+{y}")

    def end_drag(_event: Any) -> None:
        _drag["active"] = False

    def close_window() -> None:
        do_persist(save_geo=True)
        root.destroy()

    def minimize_window() -> None:
        root.overrideredirect(False)
        root.iconify()

    def open_youtube_home() -> None:
        webbrowser.open("https://www.youtube.com", new=2)

    def open_github() -> None:
        webbrowser.open("https://www.github.com/brenton-j-gray", new=2)

    def open_linkedin() -> None:
        webbrowser.open("https://www.linkedin.com/in/brenton-gray", new=2)

    def open_donate() -> None:
        webbrowser.open(DONATE_URL, new=2)

    def show_payment_qr() -> None:
        popup = tk.Toplevel(root)
        popup.title("Donation QR Code")
        popup.resizable(False, False)
        popup.configure(bg=BG)
        popup.transient(root)
        popup.geometry(f"+{root.winfo_rootx() + 80}+{root.winfo_rooty() + 80}")

        if not QR_CODE_PATH.is_file():
            tk.Label(
                popup,
                text=f"Could not find:\n{QR_CODE_PATH.name}",
                bg=BG,
                fg=FG,
                font=BODY_LABEL_FONT,
                justify="center",
            ).pack(padx=18, pady=(18, 10))
            tk.Button(
                popup,
                text="Close",
                command=popup.destroy,
                bg=SURF,
                fg=FG,
                relief="flat",
                bd=0,
                padx=12,
                pady=6,
                cursor="hand2",
            ).pack(pady=(0, 14))
            popup.grab_set()
            popup.focus_set()
            return

        photo = None
        try:
            if pil_available:
                img = Image.open(QR_CODE_PATH)
                img.thumbnail((320, 320))
                photo = ImageTk.PhotoImage(img)
            else:
                photo = tk.PhotoImage(file=str(QR_CODE_PATH))
        except Exception:
            photo = None

        if photo is None:
            tk.Label(
                popup,
                text="Unable to render payment-qrcode.png",
                bg=BG,
                fg=FG,
                font=BODY_LABEL_FONT,
            ).pack(padx=18, pady=(18, 10))
        else:
            img_label = tk.Label(popup, image=photo, bg=BG, bd=0, highlightthickness=0)
            setattr(img_label, "image", photo)
            img_label.pack(padx=14, pady=(14, 8))

        tk.Button(
            popup,
            text="Close",
            command=popup.destroy,
            bg=SURF,
            fg=FG,
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
        ).pack(pady=(0, 14))
        popup.grab_set()
        popup.focus_set()

    def on_deiconify(_event: Any) -> None:
        root.after(10, lambda: root.overrideredirect(True))

    def lbl(p: Any, t: str, **kw: Any) -> Any:
        w = tk.Label(p, text=t, bg=BG, **kw)
        label_widgets.append(w)
        return w

    def btn(p: Any, t: str, cmd: Any, primary: bool = False) -> Any:
        return tk.Button(
            p,
            text=t,
            command=cmd,
            bg=ACCENT if primary else NEUTRAL_BTN_BG,
            fg=ON_ACCENT if primary else NEUTRAL_BTN_FG,
            font=("Helvetica", 12, "bold" if primary else "normal"),
            activebackground=ACCENT if primary else NEUTRAL_BTN_ACTIVE,
            activeforeground=ON_ACCENT if primary else NEUTRAL_BTN_FG,
            relief="flat",
            bd=0,
            padx=BTN_PAD_X,
            pady=BTN_PAD_Y,
            cursor="hand2",
            highlightthickness=BORDER_STYLE["control_thickness"],
            highlightbackground=BORDER,
            highlightcolor=BORDER,
        )

    def attach_entry_context_menu(entry_widget: Any) -> None:
        menu = tk.Menu(root, tearoff=0, bg=SURF, fg=FG, activebackground=BTN_ACTIVE, activeforeground=FG)
        menu.add_command(label="Cut", command=lambda: entry_widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: entry_widget.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: entry_widget.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: entry_widget.select_range(0, tk.END))

        def show_context_menu(event: Any) -> None:
            entry_widget.focus_set()
            menu.tk_popup(event.x_root, event.y_root)

        entry_widget.bind("<Button-3>", show_context_menu)

    def render_thumbnail(thumb_bytes: bytes | None) -> Any:
        if not thumb_bytes:
            return None
        if pil_available:
            img = Image.open(BytesIO(thumb_bytes))
            img.thumbnail((160, 90))
            return ImageTk.PhotoImage(img)
        in_path, out_path = thumbnail_cache_paths(thumb_bytes)
        with open(in_path, "wb") as f:
            f.write(thumb_bytes)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                in_path,
                "-vf",
                "scale='min(160,iw)':'min(90,ih)':force_original_aspect_ratio=decrease",
                out_path,
            ],
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return tk.PhotoImage(file=out_path)

    root.bind("<Map>", on_deiconify)
    root.bind("<ButtonPress-1>", begin_drag, add="+")
    root.bind("<B1-Motion>", do_drag, add="+")
    root.bind("<ButtonRelease-1>", end_drag, add="+")
    root.after(0, lambda: ensure_taskbar_presence(root))

    top_accent_border = tk.Frame(root, bg=ACCENT, height=BORDER_STYLE["accent_thickness"])
    top_accent_border.pack(fill="x", side="top")
    left_accent_border = tk.Frame(root, bg=ACCENT, width=BORDER_STYLE["side_accent_thickness"])
    left_accent_border.pack(fill="y", side="left")
    right_accent_border = tk.Frame(root, bg=ACCENT, width=BORDER_STYLE["side_accent_thickness"])
    right_accent_border.pack(fill="y", side="right")
    top_controls = tk.Frame(root, bg=BG)
    top_controls.pack(fill="x", padx=8, pady=(6, 0))

    all_menu_popups: list[tk.Menu] = []

    def _menu_kws() -> dict[str, Any]:
        return {
            "tearoff": 0,
            "bg": NEUTRAL_BTN_BG,
            "fg": NEUTRAL_BTN_FG,
            "activebackground": NEUTRAL_BTN_ACTIVE,
            "activeforeground": NEUTRAL_BTN_FG,
            "borderwidth": 1,
            "activeborderwidth": 0,
            "relief": "solid",
        }

    file_menu = tk.Menu(root, **_menu_kws())
    file_menu.configure(
        bd=1,
        relief="solid",
        activeborderwidth=0,
    )
    all_menu_popups.append(file_menu)

    recent_menu = tk.Menu(file_menu, **_menu_kws())
    all_menu_popups.append(recent_menu)

    file_menu.add_command(
        label="Choose output folder…",
        command=lambda: choose_output_folder(),
        accelerator="Ctrl+O",
    )
    file_menu.add_command(label="Open output folder", command=lambda: open_output_folder())
    file_menu.add_command(label="Reveal last file in Explorer", command=lambda: reveal_last_downloaded())
    file_menu.add_command(label="Open error log", command=open_error_log_externally, accelerator="Ctrl+Shift+O")
    file_menu.add_separator()
    file_menu.add_command(label="Reset form", command=lambda: reset_form())
    file_menu.add_separator()
    file_menu.add_command(label="Set current folder as default on launch", command=lambda: set_default_output_folder())
    file_menu.add_cascade(label="Recent folders", menu=recent_menu)
    file_menu.add_separator()
    file_menu.add_command(label="Exit", command=close_window, accelerator="Alt+F4")

    settings_menu = tk.Menu(root, **_menu_kws())
    settings_menu.configure(
        bd=1,
        relief="solid",
        activeborderwidth=0,
    )
    all_menu_popups.append(settings_menu)

    appearance_menu = tk.Menu(settings_menu, **_menu_kws())
    all_menu_popups.append(appearance_menu)
    appearance_menu.add_radiobutton(label="Follow system", variable=theme_mode_var, value="system", selectcolor=ACCENT)
    appearance_menu.add_radiobutton(label="Light", variable=theme_mode_var, value="light", selectcolor=ACCENT)
    appearance_menu.add_radiobutton(label="Dark", variable=theme_mode_var, value="dark", selectcolor=ACCENT)
    settings_menu.add_cascade(label="Appearance", menu=appearance_menu)

    settings_menu.add_separator()
    # Checkbuttons for download/preview are appended in append_settings_extras() after form variables exist.

    def show_file_menu() -> None:
        fresh_recent_folders()
        file_menu.tk_popup(file_menu_btn.winfo_rootx(), file_menu_btn.winfo_rooty() + file_menu_btn.winfo_height())

    def show_settings_menu() -> None:
        settings_menu.tk_popup(
            settings_menu_btn.winfo_rootx(),
            settings_menu_btn.winfo_rooty() + settings_menu_btn.winfo_height(),
        )

    def show_help_menu() -> None:
        help_menu.tk_popup(help_menu_btn.winfo_rootx(), help_menu_btn.winfo_rooty() + help_menu_btn.winfo_height())

    def show_network_help() -> None:
        from tkinter import scrolledtext

        t = tk.Toplevel(root)
        t.title("Network & SSL")
        t.resizable(True, True)
        t.minsize(400, 300)
        t.configure(bg=BG)
        help_text = (
            "If you see errors about SSL or certificate verification:\n\n"
            "1. Install/upgrade the CA bundle used by this app:\n"
            "   python -m pip install -U certifi\n\n"
            "2. Optional: install the full dependency set (see requirements.txt in the app folder):\n"
            "   python -m pip install -r requirements.txt\n\n"
            "3. As a last resort (e.g. strict corporate proxy; less secure for HTTPS), set this\n"
            "   environment variable and restart the app:\n"
            "   YT_TO_AUDIO_NO_CHECK_CERT=1\n"
            "   (PowerShell) $env:YT_TO_AUDIO_NO_CHECK_CERT = '1'\n\n"
            "4. YouTube changes often; keep yt-dlp up to date:\n"
            "   python -m pip install -U yt-dlp"
        )
        tx = scrolledtext.ScrolledText(
            t,
            wrap=tk.WORD,
            width=64,
            height=16,
            font=(FONT_FAMILY, 10),
            bg=SURF,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            highlightthickness=0,
        )
        tx.insert("1.0", help_text)
        tx.config(state=tk.DISABLED)
        tx.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12, 6))
        tk.Button(
            t,
            text="Close",
            command=t.destroy,
            bg=ACCENT,
            fg=ON_ACCENT,
            font=("Helvetica", 10, "bold"),
            relief="flat",
            activebackground=ACCENT,
        ).pack(pady=(0, 12))
        t.transient(root)
        t.geometry(f"520x420+{root.winfo_rootx() + 40}+{root.winfo_rooty() + 40}")
        t.grab_set()
        t.focus_set()

    def check_ytdlp_version() -> None:
        try:
            import yt_dlp  # type: ignore[reportMissingTypeStubs]
            v = str(getattr(yt_dlp, "__version__", "unknown"))
        except Exception as e:
            v = f"(error: {e})"
        show_info("yt-dlp", f"Installed version: {v}\n\nUpdate: python -m pip install -U yt-dlp")

    def about_dialog() -> None:
        yv = "unknown"
        try:
            from yt_dlp.version import __version__ as yv  # type: ignore[reportMissingTypeStubs]
        except Exception:
            try:
                import yt_dlp  # type: ignore[reportMissingTypeStubs]

                yv = str(getattr(yt_dlp, "__version__", yv))
            except Exception:
                pass
        app_dir = str(Path(__file__).resolve().parent)
        show_info(
            "About",
            f"YouTube 2 Audio\n\n"
            f"Creator: Brenton Gray\n\n"
            f"Python {platform.python_version()}\n"
            f"yt-dlp {yv}\n\n"
            f"Config: {user_settings.settings_path()}\n\n"
            f"{app_dir}",
        )

    def open_repo() -> None:
        webbrowser.open("https://www.github.com/brenton-j-gray", new=2)

    def show_shortcuts() -> None:
        show_info(
            "Shortcuts",
            "Global:\n"
            "Ctrl+O — Choose output folder\n"
            "Ctrl+Shift+O — Open error log\n"
            "Ctrl+Shift+F — Reveal last downloaded file\n\n"
            "Conversion confirm modal:\n"
            "Enter — Start conversion\n"
            "Esc — Cancel",
        )

    help_menu = tk.Menu(root, **_menu_kws())
    help_menu.configure(
        bd=1,
        relief="solid",
        activeborderwidth=0,
    )
    all_menu_popups.append(help_menu)
    help_menu.add_command(label="About", command=about_dialog)
    help_menu.add_command(label="Donate", command=open_donate)
    help_menu.add_command(label="View error log", command=open_error_log_externally)
    help_menu.add_command(label="Network & certificate help…", command=show_network_help)
    help_menu.add_command(label="Check yt-dlp version…", command=check_ytdlp_version)
    help_menu.add_command(label="Open GitHub", command=open_repo)
    help_menu.add_command(label="Keyboard shortcuts…", command=show_shortcuts)

    file_menu_btn = tk.Button(
        top_controls,
        text="File ▾",
        command=show_file_menu,
        bg=SURF,
        fg=FG,
        activebackground=BTN_ACTIVE,
        activeforeground=FG,
        relief="flat",
        bd=0,
        font=("Helvetica", 10),
        padx=10,
        pady=4,
        cursor="hand2",
        highlightthickness=BORDER_STYLE["menu_button_thickness"],
        highlightbackground=SURF,
        highlightcolor=SURF,
    )
    file_menu_btn.pack(side="left")

    settings_menu_btn = tk.Button(
        top_controls,
        text="Settings ▾",
        command=show_settings_menu,
        bg=SURF,
        fg=FG,
        activebackground=BTN_ACTIVE,
        activeforeground=FG,
        relief="flat",
        bd=0,
        font=("Helvetica", 10),
        padx=10,
        pady=4,
        cursor="hand2",
        highlightthickness=BORDER_STYLE["menu_button_thickness"],
        highlightbackground=SURF,
        highlightcolor=SURF,
    )
    settings_menu_btn.pack(side="left", padx=(6, 0))

    help_menu_btn = tk.Button(
        top_controls,
        text="Help ▾",
        command=show_help_menu,
        bg=SURF,
        fg=FG,
        activebackground=BTN_ACTIVE,
        activeforeground=FG,
        relief="flat",
        bd=0,
        font=("Helvetica", 10),
        padx=10,
        pady=4,
        cursor="hand2",
        highlightthickness=BORDER_STYLE["menu_button_thickness"],
        highlightbackground=SURF,
        highlightcolor=SURF,
    )
    help_menu_btn.pack(side="left", padx=(6, 0))

    close_btn = tk.Button(
        top_controls,
        text="✕",
        command=close_window,
        bg=SURF,
        fg=FG,
        activebackground=BG,
        activeforeground=FG,
        relief="flat",
        bd=0,
        font=("Segoe UI", 10, "bold"),
        width=3,
        cursor="hand2",
        highlightthickness=BORDER_STYLE["control_thickness"],
        highlightbackground=BORDER,
        highlightcolor=BORDER,
    )
    close_btn.pack(side="right", padx=(4, 0))
    min_btn = tk.Button(
        top_controls,
        text="—",
        command=minimize_window,
        bg=SURF,
        fg=FG,
        activebackground=BG,
        activeforeground=FG,
        relief="flat",
        bd=0,
        font=("Segoe UI", 10, "bold"),
        width=3,
        cursor="hand2",
        highlightthickness=BORDER_STYLE["control_thickness"],
        highlightbackground=BORDER,
        highlightcolor=BORDER,
    )
    min_btn.pack(side="right")

    top_right_options = tk.Frame(root, bg=BG)
    top_right_options.pack(fill="x", padx=8, pady=(2, 0))
    top_right_options_inner = tk.Frame(top_right_options, bg=BG)
    top_right_options_inner.pack(side="right")
    topmost_check = tk.Checkbutton(
        top_right_options_inner,
        text="Always on top",
        variable=force_topmost_var,
        command=lambda: root.attributes("-topmost", force_topmost_var.get()),
        bg=BG,
        fg=FG,
        selectcolor=SURF,
        activebackground=BG,
        activeforeground=FG,
        font=(FONT_FAMILY, 9),
        bd=0,
        highlightthickness=0,
        cursor="hand2",
    )
    topmost_check.pack(side="right")

    logo_row = tk.Frame(root, bg=BG)
    logo_row.pack(fill="x", padx=24, pady=(8, 2))
    youtube_logo_btn = tk.Canvas(logo_row, width=116, height=24, bg=BG, highlightthickness=0, bd=0, relief="flat", cursor="hand2")
    youtube_logo_btn.pack(side="left")
    youtube_logo_btn.create_rectangle(2, 3, 36, 21, fill="#FF0033", outline="#FF0033")
    youtube_logo_btn.create_polygon(16, 8, 16, 16, 25, 12, fill="#ffffff", outline="#ffffff")
    yt_logo_text_id = youtube_logo_btn.create_text(44, 12, text="YouTube", fill=FG, font=("Segoe UI", 11, "bold"), anchor="w")
    youtube_logo_btn.bind("<Button-1>", lambda _e: open_youtube_home())

    title_label = lbl(root, "YouTube 2 Audio", font=TITLE_FONT, fg=FG)
    if TITLE_FONT[0] == "Frijole":
        try:
            frijole_font = tkfont.Font(root=root, family="Frijole", size=30, weight="normal")
            title_label.configure(font=frijole_font)
            setattr(title_label, "_title_font_ref", frijole_font)
        except tk.TclError:
            pass
    title_label.pack(pady=(20, 2))
    lbl(root, "Download any YouTube video as an audio file in seconds.", font=SUBTITLE_FONT, fg=MUTED).pack(pady=(0, 16))

    preview_var = tk.StringVar(value="Preview: paste a YouTube URL below to auto-load video details.")
    preview_after_id: list[str | None] = [None]
    preview_pending_url: list[str | None] = [None]
    preview_request_id = [0]
    preview_title_text = ["Unknown title"]
    preview_channel_text = ["Unknown channel"]
    is_downloading = [False]
    busy_anim_job: list[str | None] = [None]
    busy_anim_offset = [0]
    progress_display = [0.0]

    preview_title = lbl(root, "Video preview", font=SECTION_LABEL_FONT, fg=MUTED)
    preview_row = tk.Frame(root, bg=SURF, highlightthickness=BORDER_STYLE["control_thickness"], highlightbackground=BORDER)
    preview_thumb_ref = [None]

    thumb_frame = tk.Frame(preview_row, bg=SURF, highlightthickness=BORDER_STYLE["control_thickness"], highlightbackground=BORDER)
    thumb_frame.pack(side="left", padx=(10, 10), pady=10)
    thumb_frame.pack_propagate(False)
    thumb_frame.configure(width=164, height=96)
    thumb_label = tk.Label(thumb_frame, text="No preview", bg=SURF, fg=MUTED, font=SMALL_LABEL_FONT)
    thumb_label.pack(fill="both", expand=True)

    preview_text_frame = tk.Frame(preview_row, bg=SURF, width=420)
    preview_text_frame.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=10)
    preview_text_frame.pack_propagate(False)

    preview_label = lbl(
        preview_text_frame,
        "",
        textvariable=preview_var,
        font=BODY_LABEL_FONT,
        fg=FG,
        anchor="w",
        justify="left",
        wraplength=400,
    )
    preview_label.pack(fill="both", expand=True)

    lbl(root, "YouTube URL", font=SECTION_LABEL_FONT, fg=MUTED).pack(anchor="w", padx=24)
    url_var = tk.StringVar()
    uf = tk.Frame(root, bg=SURF, highlightbackground=BORDER, highlightthickness=BORDER_STYLE["control_thickness"])
    uf.pack(fill="x", padx=24, pady=(3, 12))
    url_row = tk.Frame(uf, bg=SURF)
    url_row.pack(fill="x", expand=True)
    url_entry = tk.Entry(
        url_row,
        textvariable=url_var,
        font=("Helvetica", 12),
        bg=SURF,
        fg=FG,
        insertbackground=FG,
        bd=0,
        relief="flat",
    )
    url_entry.pack(side="left", fill="x", expand=True, padx=(FIELD_PAD_X, 0), pady=FIELD_PAD_Y)
    paste_url_btn = tk.Button(
        url_row,
        text="Paste",
        font=("Helvetica", 10),
        relief="flat",
        bd=0,
        padx=INLINE_PAD_X,
        pady=FIELD_PAD_Y,
        cursor="hand2",
        highlightthickness=BORDER_STYLE["control_thickness"],
        highlightbackground=BORDER,
        highlightcolor=BORDER,
    )
    paste_url_btn.pack(side="right", padx=(4, FIELD_PAD_X), pady=FIELD_PAD_Y)
    attach_entry_context_menu(url_entry)

    lbl(root, "Save to folder", font=SECTION_LABEL_FONT, fg=MUTED).pack(anchor="w", padx=24)
    dir_var = tk.StringVar(value=_valid_start_dir(saved.get("default_output_dir") or str(Path.home() / "Downloads")))

    def fresh_recent_folders() -> None:
        recent_menu.delete(0, "end")
        for p in recent_folders_state[0]:
            disp = f"…{p[-56:]}" if len(p) > 60 else p
            recent_menu.add_command(
                label=disp,
                command=lambda fp=p: (dir_var.set(fp), do_persist()),
            )
        if not recent_folders_state[0]:
            recent_menu.add_command(label="(none yet)", state="disabled")
    dr = tk.Frame(root, bg=BG)
    dr.pack(fill="x", padx=24, pady=(3, 12))
    dir_input_wrap = tk.Frame(dr, bg=SURF, highlightbackground=BORDER, highlightthickness=BORDER_STYLE["control_thickness"])
    dir_input_wrap.pack(side="left", fill="x", expand=True)
    dir_icon = tk.Label(dir_input_wrap, text="📄", bg=SURF, fg=MUTED, font=BODY_LABEL_FONT)
    dir_icon.pack(side="left", padx=(FIELD_PAD_X, 6))
    dir_entry = tk.Entry(
        dir_input_wrap,
        textvariable=dir_var,
        font=("Helvetica", 11),
        bg=SURF,
        fg=FG,
        insertbackground=FG,
        bd=0,
        relief="flat",
    )
    dir_entry.pack(side="left", fill="x", expand=True, padx=(0, FIELD_PAD_X), pady=FIELD_PAD_Y)
    attach_entry_context_menu(dir_entry)

    def browse() -> None:
        d = filedialog.askdirectory(initialdir=dir_var.get())
        if d:
            dir_var.set(d)
            recent_folders_state[0] = user_settings.bump_recent(recent_folders_state[0], d)
            do_persist()

    browse_btn = tk.Button(
        dr,
        text="Browse…",
        command=browse,
        bg=SURF,
        fg=FG,
        font=("Helvetica", 10),
        activebackground=BTN_ACTIVE,
        activeforeground=FG,
        relief="flat",
        bd=0,
        padx=INLINE_PAD_X,
        pady=INLINE_PAD_Y,
        cursor="hand2",
        highlightthickness=BORDER_STYLE["control_thickness"],
        highlightbackground=BORDER,
        highlightcolor=BORDER,
    )
    browse_btn.pack(side="left", padx=(8, 0))
    open_btn = tk.Button(
        dr,
        text="Open Output Folder",
        bg=SURF,
        fg=FG,
        font=("Helvetica", 10),
        activebackground=BTN_ACTIVE,
        activeforeground=FG,
        relief="flat",
        bd=0,
        padx=INLINE_PAD_X,
        pady=INLINE_PAD_Y,
        cursor="hand2",
        highlightthickness=BORDER_STYLE["control_thickness"],
        highlightbackground=BORDER,
        highlightcolor=BORDER,
    )
    open_btn.pack(side="left", padx=(8, 0))

    q_var = tk.StringVar(value=saved.get("quality", "Medium (192 kbps)"))
    if q_var.get() not in Converter.QUALITY_MAP:
        q_var.set("Medium (192 kbps)")
    fmt_var = tk.StringVar(value=saved.get("format", "WAV (44.1kHz 16-bit stereo)"))
    if fmt_var.get() not in Converter.FORMAT_MAP:
        fmt_var.set("WAV (44.1kHz 16-bit stereo)")

    _deb = int(saved.get("preview_debounce_ms", 650) or 650)
    if _deb not in user_settings.DEBOUNCE_CHOICES:
        _deb = 650
    preview_debounce_intvar = tk.IntVar(master=root, value=_deb)
    auto_preview_var = tk.BooleanVar(master=root, value=bool(saved.get("auto_preview", True)))
    play_after_var = tk.BooleanVar(master=root, value=bool(saved.get("play_after_download", False)))
    auto_open_var = tk.BooleanVar(master=root, value=bool(saved.get("auto_open_folder", True)))
    st = ttk.Style()
    st_any = cast(Any, st)
    root_any = cast(Any, root)
    st.theme_use("clam")
    combo_bg = SURF
    combo_fg = FG
    st_any.configure(
        "ThemeAware.TCombobox",
        fieldbackground=combo_bg,
        background=combo_bg,
        foreground=combo_fg,
        arrowcolor=combo_fg,
        bordercolor=BORDER,
        lightcolor=combo_bg,
        darkcolor=combo_bg,
        padding=(FIELD_PAD_X, COMBO_PAD_Y, FIELD_PAD_X, COMBO_PAD_Y),
    )
    st_any.map(
        "ThemeAware.TCombobox",
        fieldbackground=[("readonly", combo_bg), ("disabled", combo_bg), ("!disabled", combo_bg)],
        foreground=[("readonly", combo_fg), ("disabled", MUTED), ("!disabled", combo_fg)],
        selectbackground=[("readonly", combo_bg)],
        selectforeground=[("readonly", combo_fg)],
    )
    root_any.option_add("*TCombobox*Listbox.background", combo_bg)
    root_any.option_add("*TCombobox*Listbox.foreground", combo_fg)
    root_any.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root_any.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT)

    selection_row = tk.Frame(root, bg=BG)
    selection_row.pack(fill="x", padx=24, pady=(0, 12))

    format_col = tk.Frame(selection_row, bg=BG)
    format_col.pack(side="left", fill="x", expand=True)
    lbl(format_col, "Output format", font=SECTION_LABEL_FONT, fg=MUTED).pack(anchor="w")
    format_combo = ttk.Combobox(
        format_col,
        textvariable=fmt_var,
        values=list(Converter.FORMAT_MAP.keys()),
        state="readonly",
        font=("Helvetica", 11),
        width=24,
        style="ThemeAware.TCombobox",
    )
    format_combo.pack(fill="x", pady=(3, 0))

    quality_col = tk.Frame(selection_row, bg=BG)
    quality_col.pack(side="left", fill="x", expand=True, padx=(12, 0))
    quality_label = lbl(quality_col, "Audio quality", font=SECTION_LABEL_FONT, fg=MUTED)
    quality_label.pack(anchor="w")
    quality_combo = ttk.Combobox(
        quality_col,
        textvariable=q_var,
        values=list(Converter.QUALITY_MAP.keys()),
        state="readonly",
        font=("Helvetica", 11),
        width=24,
        style="ThemeAware.TCombobox",
    )
    quality_combo.pack(fill="x", pady=(3, 0))

    quality_hint_var = tk.StringVar(value="")
    quality_hint_label = lbl(root, "", textvariable=quality_hint_var, font=BODY_LABEL_FONT, fg=MUTED)
    quality_hint_label.pack(anchor="w", padx=24, pady=(0, 12))

    def update_quality_state(*_args: Any) -> None:
        codec = Converter.FORMAT_MAP.get(fmt_var.get(), "wav")
        try:
            go_btn.config(text=f"Download {codec.upper()}")
        except NameError:
            pass
        if codec in Converter.LOSSLESS_FORMATS:
            quality_col.pack_forget()
            quality_hint_var.set("")
        else:
            if not quality_col.winfo_manager():
                quality_col.pack(side="left", fill="x", expand=True, padx=(12, 0))
            quality_combo.config(state="readonly")
            quality_label.config(fg=MUTED)
            quality_hint_label.config(fg=MUTED)
            quality_hint_var.set("Quality preset applies to lossy output formats.")

    fmt_var.trace_add("write", update_quality_state)
    update_quality_state()

    preview_title.pack(anchor="w", padx=24, pady=(2, 0))
    preview_row.pack(fill="x", padx=24, pady=(3, 10))

    status_var = tk.StringVar(value="Ready.")
    lbl(root, "", textvariable=status_var, font=BODY_LABEL_FONT, fg=MUTED).pack()
    st_any.configure(
        "Red.Horizontal.TProgressbar",
        troughcolor=BORDER if not app_is_dark else SURF,
        background=ACCENT,
        thickness=PROGRESS_THICKNESS,
    )
    progress_host = tk.Frame(root, bg=BG, width=500, height=PROGRESS_THICKNESS + (PROGRESS_PAD_Y * 2))
    progress_host.pack(padx=24, pady=(4, 16))
    progress_host.pack_propagate(False)
    bar = ttk.Progressbar(progress_host, style="Red.Horizontal.TProgressbar", orient="horizontal", mode="determinate")
    bar.place(relx=0, rely=0, relwidth=1, relheight=1)
    busy_bar_canvas = tk.Canvas(progress_host, highlightthickness=0, bd=0, relief="flat")
    busy_bar_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
    stripe_overlay_canvas = tk.Canvas(progress_host, highlightthickness=0, bd=0, relief="flat")
    stripe_overlay_canvas.place_forget()

    busy_palette = {
        "trough": BORDER if not app_is_dark else SURF,
        "stripe_a": ACCENT,
        "stripe_b": _blend_hex(ACCENT, "#ffffff", 0.22),
        "done_a": "#2f8f4e",
        "done_b": "#48b86c",
    }

    def draw_busy_bar() -> None:
        w = max(1, progress_host.winfo_width())
        h = max(1, progress_host.winfo_height())
        fill_w = int(max(0.0, min(100.0, progress_display[0])) / 100.0 * w)
        is_complete = progress_display[0] >= 100.0 and not is_downloading[0]
        busy_bar_canvas.configure(bg=busy_palette["trough"])
        busy_bar_canvas.delete("all")
        busy_bar_canvas.create_rectangle(0, 0, w, h, fill=busy_palette["trough"], outline=busy_palette["trough"])
        if fill_w <= 0:
            stripe_overlay_canvas.place_forget()
            return
        fill_a = busy_palette["done_a"] if is_complete else busy_palette["stripe_a"]
        fill_b = busy_palette["done_b"] if is_complete else busy_palette["stripe_b"]
        busy_bar_canvas.create_rectangle(0, 0, fill_w, h, fill=fill_a, outline=fill_a)
        stripe_overlay_canvas.place(x=0, y=0, width=fill_w, height=h)
        stripe_overlay_canvas.configure(bg=fill_a)
        stripe_overlay_canvas.delete("all")
        stripe_spacing = 16
        stripe_width = 7
        offset = busy_anim_offset[0]
        for x in range(-h + offset, fill_w + h, stripe_spacing):
            stripe_overlay_canvas.create_line(
                x,
                h,
                x + h,
                0,
                fill=fill_b,
                width=stripe_width,
            )

    br = tk.Frame(root, bg=BG)
    br.pack(pady=(0, 24))
    go_btn = btn(br, "Download WAV", None, primary=True)
    stop_btn = btn(br, "Cancel", None)
    go_btn.pack(side="left", padx=(0, 10))
    stop_btn.pack(side="left")
    stop_btn.config(state="disabled")
    # Ensure the primary action label matches the saved/restored format on startup.
    update_quality_state()

    footer_row = tk.Frame(root, bg=BG)
    footer_row.pack(fill="x", padx=24, pady=(0, 8))
    auto_open_check = tk.Checkbutton(
        footer_row,
        text="Open folder when done",
        variable=auto_open_var,
        command=lambda: do_persist(),
        bg=BG,
        fg=FG,
        selectcolor=SURF,
        activebackground=BG,
        activeforeground=FG,
        font=("Helvetica", 10),
        bd=0,
        highlightthickness=0,
    )
    auto_open_check.pack(side="left")

    play_after_check = tk.Checkbutton(
        footer_row,
        text="Play when done",
        variable=play_after_var,
        command=lambda: do_persist(),
        bg=BG,
        fg=FG,
        selectcolor=SURF,
        activebackground=BG,
        activeforeground=FG,
        font=("Helvetica", 10),
        bd=0,
        highlightthickness=0,
    )
    play_after_check.pack(side="left", padx=(12, 0))

    donate_box = tk.Frame(footer_row, bg=MUTED)
    donate_box.pack(side="right")

    qr_link = tk.Label(
        donate_box,
        text="Donate: QR Code",
        bg=BG,
        fg=ACCENT,
        cursor="hand2",
        font=(FONT_FAMILY, 10, "underline"),
    )
    qr_link.pack(side="left", padx=(0, 8))

    donate_btn = tk.Button(
        donate_box,
        text="Donate with PayPal",
        command=open_donate,
        cursor="hand2",
        font=(FONT_FAMILY, 10, "bold"),
        relief="flat",
        bd=0,
        padx=12,
        pady=4,
        highlightthickness=BORDER_STYLE["control_thickness"],
    )
    donate_btn.pack(side="left")

    donate_sep = tk.Label(footer_row, text="  |  ", bg=BG, fg=MUTED, font=SMALL_LABEL_FONT)
    donate_sep.pack(side="right")

    linkedin_link = tk.Label(footer_row, text="LinkedIn", bg=BG, fg=ACCENT, cursor="hand2", font=(FONT_FAMILY, 10, "underline"))
    linkedin_link.pack(side="right")

    def new_social_separator() -> Any:
        sep = tk.Label(footer_row, text="  |  ", bg=BG, fg=MUTED, font=SMALL_LABEL_FONT)
        sep.pack(side="right")
        return sep

    social_separators = [new_social_separator()]

    github_link = tk.Label(footer_row, text="GitHub", bg=BG, fg=ACCENT, cursor="hand2", font=(FONT_FAMILY, 10, "underline"))
    github_link.pack(side="right")

    github_link.bind("<Button-1>", lambda _e: open_github())
    linkedin_link.bind("<Button-1>", lambda _e: open_linkedin())
    qr_link.bind("<Button-1>", lambda _e: show_payment_qr())

    social_separators.append(new_social_separator())

    bottom_accent_border = tk.Frame(root, bg=ACCENT, height=BORDER_STYLE["accent_thickness"])
    bottom_accent_border.pack(fill="x", side="bottom")

    def set_busy(b: bool) -> None:
        is_downloading[0] = b
        go_btn.config(state="disabled" if b else "normal")
        stop_btn.config(state="normal" if b else "disabled")
        if not b:
            stripe_overlay_canvas.place_forget()
            if busy_anim_job[0] is not None:
                try:
                    root.after_cancel(busy_anim_job[0])
                except Exception:
                    pass
                busy_anim_job[0] = None
            busy_anim_offset[0] = 0
            draw_busy_bar()

    def on_progress(p: float) -> None:
        def _apply() -> None:
            progress_display[0] = float(p)
            bar.configure(value=p)
            draw_busy_bar()

        root.after(0, _apply)

    def on_status(s: str) -> None:
        root.after(0, lambda: status_var.set(s))

    def on_preview_result(
        text: str,
        request_id: int,
        thumb_bytes: bytes | None = None,
        title: str | None = None,
        channel: str | None = None,
    ) -> None:
        def apply_preview() -> None:
            if request_id == preview_request_id[0]:
                preview_var.set(text)
                preview_title_text[0] = title or "Unknown title"
                preview_channel_text[0] = channel or "Unknown channel"
                if thumb_bytes:
                    try:
                        photo = render_thumbnail(thumb_bytes)
                        preview_thumb_ref[0] = photo
                        if photo:
                            thumb_label.configure(image=photo, text="")
                            # Quick pulse to make new thumbnail arrivals feel responsive.
                            for step in range(7):
                                color = _blend_hex(SURF, ACCENT, max(0.0, 0.32 - step * 0.05))
                                root.after(step * 34, lambda c=color: thumb_frame.configure(highlightbackground=c))
                            root.after(7 * 34, lambda: thumb_frame.configure(highlightbackground=BORDER))
                        else:
                            thumb_label.configure(image="", text="No preview")
                    except Exception as thumb_exc:
                        append_error_log("preview_thumbnail_render", str(thumb_exc))
                        preview_thumb_ref[0] = None
                        thumb_label.configure(image="", text="No preview")
                elif not thumb_bytes:
                    preview_thumb_ref[0] = None
                    thumb_label.configure(image="", text="No preview")

        root.after(0, apply_preview)

    def preview_url(url_override: str | None = None) -> None:
        if is_downloading[0]:
            preview_var.set("Preview is disabled while downloading.")
            return
        if not auto_preview_var.get():
            preview_var.set("Auto-preview is off (use Settings to enable).")
            return
        url = (url_override if url_override is not None else url_var.get()).strip()
        url = normalize_youtube_url(url)
        preview_pending_url[0] = url
        preview_request_id[0] += 1
        request_id = preview_request_id[0]
        if not url:
            preview_var.set("Preview: paste a URL first.")
            return
        if not is_supported_youtube_url(url):
            preview_var.set("Preview: invalid YouTube URL.")
            return
        preview_var.set("Preview: loading…")

        def run_preview() -> None:
            try:
                preview = preview_service.fetch(url)
                on_preview_result(
                    preview.text,
                    request_id,
                    thumb_bytes=preview.thumb_bytes,
                    title=preview.title,
                    channel=preview.channel,
                )
            except Exception as e:
                append_error_log("preview_exception", f"URL: {url}\n{e}\n{traceback.format_exc()}")
                on_preview_result(
                    "Preview failed. See error log for details.",
                    request_id,
                    thumb_bytes=None,
                    title=None,
                    channel=None,
                )

        threading.Thread(target=run_preview, daemon=True).start()

    def schedule_preview(_event: Any = None) -> None:
        if is_downloading[0]:
            return
        if not auto_preview_var.get():
            return
        current_url = url_var.get().strip()
        if preview_after_id[0] is not None:
            root.after_cancel(preview_after_id[0])
            preview_after_id[0] = None
        if not current_url:
            preview_var.set("Preview: paste a URL first.")
            preview_pending_url[0] = None
            return
        if not is_supported_youtube_url(current_url):
            preview_var.set("Preview: invalid YouTube URL.")
            preview_pending_url[0] = None
            return
        if current_url == preview_pending_url[0]:
            return
        preview_var.set("Preview: waiting…")
        deb = max(200, int(preview_debounce_intvar.get() or 650))
        preview_after_id[0] = root.after(deb, lambda u=current_url: preview_url(u))

    def paste_url_from_clipboard() -> None:
        try:
            text = root.clipboard_get()
        except tk.TclError:
            return
        url_var.set(text.strip())

    paste_url_btn.config(command=paste_url_from_clipboard)

    def _schedule_preview_trace(*_: Any) -> None:
        schedule_preview()

    cast(Any, url_var).trace_add("write", _schedule_preview_trace)
    url_entry.bind("<Control-v>", schedule_preview, add="+")
    url_entry.bind("<<Paste>>", schedule_preview, add="+")

    def on_done(ok: bool, result: str) -> None:
        def _() -> None:
            if ok:
                progress_display[0] = 100.0
                bar.configure(value=100)
                set_busy(False)
                rpath = Path(result).resolve()
                last_download_path[0] = str(rpath)
                recent_folders_state[0] = user_settings.bump_recent(recent_folders_state[0], str(rpath.parent))
                do_persist()
                status_var.set(f"✓  Saved: {rpath}")
                show_completion_toast(f"Saved: {rpath.name}")
                if play_after_var.get() and rpath.is_file():
                    try:
                        if os.name == "nt":
                            os.startfile(result)  # type: ignore[attr-defined]
                        elif sys.platform == "darwin":
                            subprocess.Popen(["open", str(rpath)], close_fds=True)
                        else:
                            subprocess.Popen(["xdg-open", str(rpath)], close_fds=True)
                    except (OSError, TypeError, ValueError):
                        pass
                if auto_open_var.get():
                    open_folder(rpath.parent)
            elif result == "Cancelled by user.":
                set_busy(False)
                progress_display[0] = 0.0
                bar.configure(value=0)
                status_var.set("Cancelled.")
                draw_busy_bar()
            else:
                set_busy(False)
                progress_display[0] = 0.0
                bar.configure(value=0)
                status_var.set("Download failed.")
                show_error("Download failed", result)
                draw_busy_bar()

        root.after(0, _)

    def show_completion_toast(message: str) -> None:
        toast = tk.Toplevel(root)
        toast.overrideredirect(True)
        toast.configure(bg=ACCENT)
        toast.attributes("-topmost", True)
        try:
            toast.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        tx = tk.Label(
            toast,
            text=f"✓ {message}",
            bg=ACCENT,
            fg=ON_ACCENT,
            font=(FONT_FAMILY, 10, "bold"),
            padx=12,
            pady=8,
        )
        tx.pack()
        root.update_idletasks()
        x = root.winfo_rootx() + root.winfo_width() - 260
        y_final = root.winfo_rooty() + root.winfo_height() - 70
        y_start = y_final + 18
        toast.geometry(f"+{x}+{y_start}")

        def animate_in(step: int = 0) -> None:
            if step > 8:
                root.after(1300, animate_out)
                return
            frac = step / 8.0
            y = int(y_start - (y_start - y_final) * frac)
            toast.geometry(f"+{x}+{y}")
            try:
                toast.attributes("-alpha", min(0.95, frac))
            except tk.TclError:
                pass
            root.after(22, lambda: animate_in(step + 1))

        def animate_out(step: int = 0) -> None:
            if step > 8:
                toast.destroy()
                return
            frac = step / 8.0
            try:
                toast.attributes("-alpha", max(0.0, 0.95 * (1.0 - frac)))
            except tk.TclError:
                pass
            root.after(28, lambda: animate_out(step + 1))

        animate_in()

    def confirm_conversion_settings(
        video_title: str,
        channel_name: str,
        output_dir: str,
        format_label: str,
        quality_label: str,
    ) -> bool:
        modal = tk.Toplevel(root)
        modal.resizable(False, False)
        modal.configure(bg=BG)
        modal.transient(root)
        modal.overrideredirect(True)
        modal.attributes("-topmost", True)
        modal_w = 560
        modal_h = 380
        modal.geometry(f"{modal_w}x{modal_h}")
        modal.withdraw()

        decision = {"ok": False}

        def short_text(value: str, max_len: int = 72) -> str:
            s = value.strip()
            return s if len(s) <= max_len else f"{s[: max_len - 3]}..."

        top_border = tk.Frame(modal, bg=ACCENT, height=2)
        top_border.pack(fill="x", side="top")
        left_border = tk.Frame(modal, bg=ACCENT, width=2)
        left_border.pack(fill="y", side="left")
        right_border = tk.Frame(modal, bg=ACCENT, width=2)
        right_border.pack(fill="y", side="right")
        bottom_border = tk.Frame(modal, bg=ACCENT, height=2)
        bottom_border.pack(fill="x", side="bottom")

        header = tk.Frame(modal, bg=BG)
        header.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(
            header,
            text="Confirm conversion",
            bg=BG,
            fg=FG,
            font=(FONT_FAMILY, 13, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            header,
            text="Review settings before starting",
            bg=BG,
            fg=MUTED,
            font=(FONT_FAMILY, 9),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        settings_card = tk.Frame(
            modal,
            bg=SURF,
            highlightthickness=BORDER_STYLE["control_thickness"],
            highlightbackground=BORDER,
        )
        settings_card.pack(fill="both", expand=False, padx=16, pady=(2, 8))

        tk.Label(
            settings_card,
            text="Title",
            bg=SURF,
            fg=MUTED,
            font=(FONT_FAMILY, 9, "bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(
            settings_card,
            text=short_text(video_title, 78),
            bg=SURF,
            fg=FG,
            font=(FONT_FAMILY, 10),
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=12, pady=(1, 8))

        tk.Label(
            settings_card,
            text="Channel",
            bg=SURF,
            fg=MUTED,
            font=(FONT_FAMILY, 9, "bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 0))
        tk.Label(
            settings_card,
            text=short_text(channel_name, 78),
            bg=SURF,
            fg=FG,
            font=(FONT_FAMILY, 10),
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=12, pady=(1, 8))

        tk.Label(
            settings_card,
            text="Output folder",
            bg=SURF,
            fg=MUTED,
            font=(FONT_FAMILY, 9, "bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 0))
        tk.Label(
            settings_card,
            text=short_text(output_dir, 78),
            bg=SURF,
            fg=FG,
            font=(FONT_FAMILY, 10),
            anchor="w",
            justify="left",
        ).pack(fill="x", padx=12, pady=(1, 8))

        row = tk.Frame(settings_card, bg=SURF)
        row.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(
            row,
            text=f"Format: {short_text(format_label, 26)}",
            bg=SURF,
            fg=FG,
            font=(FONT_FAMILY, 10, "bold"),
            anchor="w",
        ).pack(side="left")
        tk.Label(
            row,
            text=f"Quality: {short_text(quality_label, 24)}",
            bg=SURF,
            fg=MUTED,
            font=(FONT_FAMILY, 10),
            anchor="w",
        ).pack(side="right")

        tk.Label(
            modal,
            text="Proceed with these settings?",
            bg=BG,
            fg=MUTED,
            font=(FONT_FAMILY, 9),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 8))

        btn_row = tk.Frame(modal, bg=BG)
        btn_row.pack(fill="x", side="bottom", padx=16, pady=(0, 12))

        def on_cancel() -> None:
            decision["ok"] = False
            modal.destroy()

        def on_confirm() -> None:
            decision["ok"] = True
            modal.destroy()

        tk.Button(
            btn_row,
            text="Cancel",
            command=on_cancel,
            bg=NEUTRAL_BTN_BG,
            fg=NEUTRAL_BTN_FG,
            activebackground=NEUTRAL_BTN_ACTIVE,
            activeforeground=NEUTRAL_BTN_FG,
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            highlightthickness=BORDER_STYLE["control_thickness"],
            highlightbackground=BORDER,
            highlightcolor=BORDER,
        ).pack(side="right", padx=(8, 0))
        confirm_btn = tk.Button(
            btn_row,
            text="Start conversion",
            command=on_confirm,
            bg=ACCENT,
            fg=ON_ACCENT,
            activebackground=ACCENT,
            activeforeground=ON_ACCENT,
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            highlightthickness=BORDER_STYLE["control_thickness"],
            highlightbackground=BORDER,
            highlightcolor=BORDER,
        )
        confirm_btn.pack(side="right")

        modal.protocol("WM_DELETE_WINDOW", on_cancel)

        def center_modal() -> None:
            root.update_idletasks()
            modal.update_idletasks()
            rx = int(root.winfo_rootx())
            ry = int(root.winfo_rooty())
            rw = int(root.winfo_width())
            rh = int(root.winfo_height())
            if (rx == 0 and ry == 0) or rw <= 1 or rh <= 1:
                # Fallback for borderless windows that sometimes report stale root coords on first paint.
                m = re.match(r"^\d+x\d+([+-]\d+)([+-]\d+)$", str(root.winfo_geometry()))
                if m:
                    rx = int(m.group(1))
                    ry = int(m.group(2))
            x = rx + max(0, (rw - modal_w) // 2)
            y = ry + max(0, (rh - modal_h) // 2)
            modal.geometry(f"{modal_w}x{modal_h}+{x}+{y}")

        center_modal()
        modal.deiconify()
        modal.lift()
        modal.grab_set()
        modal.focus_force()
        confirm_btn.focus_set()
        # One extra pass after map for Windows placement quirks.
        modal.after(10, lambda: (center_modal(), modal.lift()))
        modal.bind("<Escape>", lambda _e: on_cancel())
        modal.bind("<Return>", lambda _e: on_confirm())
        root.wait_window(modal)
        return bool(decision["ok"])

    def run_busy_progress_animation() -> None:
        if not is_downloading[0]:
            busy_anim_job[0] = None
            return
        busy_anim_offset[0] = (busy_anim_offset[0] + 4) % 16
        draw_busy_bar()
        busy_anim_job[0] = root.after(36, run_busy_progress_animation)

    def start() -> None:
        url = url_var.get().strip()
        out = dir_var.get().strip()
        normalized_out: str | None = None
        if out:
            try:
                candidate = Path(os.path.expandvars(os.path.expanduser(out)))
                if candidate.is_file():
                    candidate = candidate.parent
                if candidate.is_dir():
                    normalized_out = str(candidate.resolve())
            except (OSError, RuntimeError, ValueError):
                normalized_out = None
        if not url:
            show_warning("Missing URL", "Please paste a YouTube URL.")
            return
        if not is_supported_youtube_url(url):
            show_warning(
                "Invalid URL",
                "Please use a valid YouTube URL (youtube.com/watch, youtube.com/shorts, or youtu.be).",
            )
            return
        if not normalized_out:
            show_warning("Bad folder", "Choose a valid output folder.")
            return
        if out != normalized_out:
            dir_var.set(normalized_out)
        if not confirm_conversion_settings(
            preview_title_text[0],
            preview_channel_text[0],
            normalized_out,
            fmt_var.get(),
            q_var.get(),
        ):
            status_var.set("Conversion cancelled before start.")
            return
        set_busy(True)
        progress_display[0] = 0.0
        bar.configure(value=0)
        status_var.set("Starting…")
        if busy_anim_job[0] is None:
            run_busy_progress_animation()
        _cv[0] = Converter(url, normalized_out, q_var.get(), fmt_var.get(), on_progress, on_status, on_done)
        threading.Thread(target=_cv[0].run, daemon=True).start()

    def cancel() -> None:
        if _cv[0]:
            _cv[0].cancel()
        progress_display[0] = 0.0
        bar.configure(value=0)
        draw_busy_bar()
        status_var.set("Cancelled.")
        set_busy(False)

    def open_output_folder() -> None:
        out = dir_var.get().strip()
        if not out:
            show_warning("Bad folder", "Choose a valid output folder.")
            return
        try:
            target = Path(os.path.expandvars(os.path.expanduser(out)))
            if target.is_file():
                target = target.parent
            if not target.is_dir():
                raise ValueError("Not a directory")
            resolved_target = target.resolve()
        except (OSError, RuntimeError, ValueError):
            show_warning("Bad folder", "Choose a valid output folder.")
            return
        if str(resolved_target) != out:
            dir_var.set(str(resolved_target))
        open_folder(resolved_target)

    def choose_output_folder() -> None:
        browse()

    def do_persist(save_geo: bool = False) -> None:
        if save_geo:
            try:
                geo = root.winfo_geometry()
            except tk.TclError:
                geo = None
        else:
            geo = user_settings.load().get("window_geometry")
        lp = last_download_path[0]
        if lp and not Path(lp).is_file():
            lp = None
        try:
            deb = int(preview_debounce_intvar.get() or 650)
        except (TypeError, ValueError, tk.TclError):
            deb = 650
        if deb not in user_settings.DEBOUNCE_CHOICES:
            deb = 650
        user_settings.save(
            theme=theme_mode_var.get(),
            default_output_dir=dir_var.get().strip() or str(Path.home() / "Downloads"),
            recent_folders=recent_folders_state[0],
            format_key=fmt_var.get(),
            quality_key=q_var.get(),
            auto_open_folder=auto_open_var.get(),
            play_after_download=play_after_var.get(),
            force_remain_on_top=force_topmost_var.get(),
            auto_preview=auto_preview_var.get(),
            preview_debounce_ms=deb,
            last_download_path=lp,
            window_geometry=geo,
        )

    def reveal_last_downloaded() -> None:
        p = last_download_path[0]
        if p and Path(p).is_file():
            reveal_in_explorer(p)
        else:
            show_info("Reveal in Explorer", "No saved file from this session yet. Download a video first.")

    def reset_form() -> None:
        if preview_after_id[0] is not None:
            try:
                root.after_cancel(preview_after_id[0])
            except Exception:
                pass
            preview_after_id[0] = None
        url_var.set("")
        progress_display[0] = 0.0
        bar.configure(value=0)
        draw_busy_bar()
        preview_var.set("Preview: paste a YouTube URL below to auto-load video details.")
        preview_thumb_ref[0] = None
        preview_pending_url[0] = None
        preview_title_text[0] = "Unknown title"
        preview_channel_text[0] = "Unknown channel"
        thumb_label.configure(image="", text="No preview")
        status_var.set("Ready.")

    def set_default_output_folder() -> None:
        d = dir_var.get().strip()
        if not d or not Path(d).is_dir():
            show_warning("Bad folder", "Choose a valid output folder first.")
            return
        do_persist()
        show_info("Default folder", "The current output folder is saved and will be restored next time.")

    def append_settings_extras() -> None:
        settings_menu.add_checkbutton(
            label="Open folder when download completes",
            variable=auto_open_var,
            command=do_persist,
            selectcolor=ACCENT,
        )
        settings_menu.add_checkbutton(
            label="Play file after download (default app)",
            variable=play_after_var,
            command=do_persist,
            selectcolor=ACCENT,
        )
        settings_menu.add_checkbutton(
            label="Force remain on top",
            variable=force_topmost_var,
            command=lambda: root.attributes("-topmost", force_topmost_var.get()),
            selectcolor=ACCENT,
        )
        settings_menu.add_separator()
        preview_opts_menu = tk.Menu(settings_menu, **_menu_kws())
        all_menu_popups.append(preview_opts_menu)
        preview_opts_menu.add_checkbutton(
            label="Load preview when URL changes",
            variable=auto_preview_var,
            command=do_persist,
            selectcolor=ACCENT,
        )
        preview_opts_menu.add_separator()
        for ms in user_settings.DEBOUNCE_CHOICES:
            preview_opts_menu.add_radiobutton(
                label=f"Preview delay: {ms} ms",
                variable=preview_debounce_intvar,
                value=ms,
                command=do_persist,
                selectcolor=ACCENT,
            )
        settings_menu.add_cascade(label="Preview", menu=preview_opts_menu)
        settings_menu.add_separator()

    append_settings_extras()

    def apply_theme() -> None:
        mode = theme_mode_var.get()
        dark = is_windows_dark_mode() if mode == "system" else (mode == "dark")
        p = palette_for_mode(dark)

        root.configure(bg=p["BG"])
        for border_frame in (top_accent_border, left_accent_border, right_accent_border, bottom_accent_border):
            border_frame.configure(bg=p["ACCENT"])
        for w in label_widgets:
            current_fg = str(w.cget("fg"))
            target_fg = p["MUTED"] if current_fg in {MUTED, p["MUTED"]} else p["FG"]
            w.configure(bg=p["BG"], fg=target_fg)
        title_label.configure(font=TITLE_FONT, fg=p["FG"])

        for frame in (
            top_controls,
            top_right_options,
            top_right_options_inner,
            logo_row,
            dr,
            selection_row,
            format_col,
            quality_col,
            br,
            footer_row,
            donate_box,
        ):
            frame.configure(bg=p["BG"])
        progress_host.configure(bg=p["BG"])
        for frame in (uf, url_row, dir_input_wrap, preview_row, thumb_frame, preview_text_frame):
            frame.configure(bg=p["SURF"], highlightbackground=p["BORDER"])
        thumb_label.configure(bg=p["SURF"], fg=p["MUTED"])
        dir_icon.configure(bg=p["SURF"], fg=p["MUTED"])
        for sep in social_separators:
            sep.configure(bg=p["BG"], fg=p["MUTED"])
        donate_sep.configure(bg=p["BG"], fg=p["MUTED"])
        github_link.configure(bg=p["BG"], fg=p["ACCENT"])
        linkedin_link.configure(bg=p["BG"], fg=p["ACCENT"])
        qr_link.configure(bg=p["BG"], fg=p["ACCENT"])
        donate_btn.configure(
            bg="#FFC439",
            fg="#111111",
            activebackground="#FFB347",
            activeforeground="#111111",
            highlightbackground="#005EA6",
            highlightcolor="#005EA6",
        )

        url_entry.configure(bg=p["SURF"], fg=p["FG"], insertbackground=p["FG"])
        dir_entry.configure(bg=p["SURF"], fg=p["FG"], insertbackground=p["FG"])
        preview_label.configure(fg=p["FG"])
        quality_label.configure(fg=p["MUTED"])
        quality_hint_label.configure(fg=p["MUTED"])

        for b in (file_menu_btn, settings_menu_btn, help_menu_btn, paste_url_btn, browse_btn, open_btn, stop_btn):
            b.configure(
                bg=p["NEUTRAL_BTN_BG"],
                fg=p["NEUTRAL_BTN_FG"],
                activebackground=p["NEUTRAL_BTN_ACTIVE"],
                activeforeground=p["NEUTRAL_BTN_FG"],
                highlightbackground=p["BORDER"],
                highlightcolor=p["BORDER"],
            )
        youtube_logo_btn.configure(bg=p["BG"])
        youtube_logo_btn.itemconfigure(yt_logo_text_id, fill=p["FG"])
        go_btn.configure(
            bg=p["ACCENT"],
            fg=p["ON_ACCENT"],
            activebackground=p["ACCENT"],
            activeforeground=p["ON_ACCENT"],
            highlightbackground=p["BORDER"],
            highlightcolor=p["BORDER"],
        )
        for chk in (auto_open_check, play_after_check):
            chk.configure(
                bg=p["BG"],
                fg=p["FG"],
                selectcolor=p["SURF"],
                activebackground=p["BG"],
                activeforeground=p["FG"],
            )
        topmost_check.configure(
            bg=p["BG"],
            fg=p["FG"],
            selectcolor=p["SURF"],
            activebackground=p["BG"],
            activeforeground=p["FG"],
        )
        for title_btn in (min_btn, close_btn):
            title_btn.configure(
                bg=p["NEUTRAL_BTN_BG"],
                fg=p["NEUTRAL_BTN_FG"],
                activebackground=p["NEUTRAL_BTN_ACTIVE"],
                activeforeground=p["NEUTRAL_BTN_FG"],
                highlightbackground=p["BORDER"],
                highlightcolor=p["BORDER"],
            )
        for m in all_menu_popups:
            m.configure(
                bg=p["NEUTRAL_BTN_BG"],
                fg=p["NEUTRAL_BTN_FG"],
                activebackground=p["NEUTRAL_BTN_ACTIVE"],
                activeforeground=p["NEUTRAL_BTN_FG"],
                borderwidth=1,
                activeborderwidth=0,
                relief="solid",
            )
            try:
                n = m.index("end")
            except tk.TclError:
                n = -1
            if n is None:
                n = -1
            for idx in range(n + 1):
                t = m.type(idx)
                if t in ("radiobutton", "checkbutton"):
                    m.entryconfigure(idx, selectcolor=p["ACCENT"])

        st_any.configure(
            "ThemeAware.TCombobox",
            fieldbackground=p["SURF"],
            background=p["SURF"],
            foreground=p["FG"],
            arrowcolor=p["FG"],
            bordercolor=p["BORDER"],
            lightcolor=p["SURF"],
            darkcolor=p["SURF"],
            padding=(FIELD_PAD_X, COMBO_PAD_Y, FIELD_PAD_X, COMBO_PAD_Y),
        )
        st_any.map(
            "ThemeAware.TCombobox",
            fieldbackground=[("readonly", p["SURF"]), ("disabled", p["SURF"]), ("!disabled", p["SURF"])],
            foreground=[("readonly", p["FG"]), ("disabled", p["MUTED"]), ("!disabled", p["FG"])],
            selectbackground=[("readonly", p["SURF"])],
            selectforeground=[("readonly", p["FG"])],
        )
        root_any.option_add("*TCombobox*Listbox.background", p["SURF"])
        root_any.option_add("*TCombobox*Listbox.foreground", p["FG"])
        root_any.option_add("*TCombobox*Listbox.selectBackground", p["ACCENT"])
        root_any.option_add("*TCombobox*Listbox.selectForeground", p["ON_ACCENT"])
        st_any.configure(
            "Red.Horizontal.TProgressbar",
            troughcolor=p["BORDER"] if not p["APP_IS_DARK"] else p["SURF"],
            background=p["ACCENT"],
            thickness=PROGRESS_THICKNESS,
        )
        busy_palette["trough"] = p["BORDER"] if not p["APP_IS_DARK"] else p["SURF"]
        busy_palette["stripe_a"] = p["ACCENT"]
        busy_palette["stripe_b"] = _blend_hex(p["ACCENT"], "#ffffff", 0.22)
        draw_busy_bar()

    last_system_dark = [is_windows_dark_mode()]

    def watch_system_theme() -> None:
        if theme_mode_var.get() == "system":
            current = is_windows_dark_mode()
            if current != last_system_dark[0]:
                last_system_dark[0] = current
                apply_theme()
        root.after(1200, watch_system_theme)

    def _theme_trace(*_: Any) -> None:
        apply_theme()
        do_persist()

    def _persist_trace(*_: Any) -> None:
        do_persist()

    cast(Any, theme_mode_var).trace_add("write", _theme_trace)
    cast(Any, fmt_var).trace_add("write", _persist_trace)
    cast(Any, q_var).trace_add("write", _persist_trace)
    cast(Any, auto_preview_var).trace_add("write", _persist_trace)
    cast(Any, play_after_var).trace_add("write", _persist_trace)
    cast(Any, force_topmost_var).trace_add("write", _persist_trace)
    cast(Any, preview_debounce_intvar).trace_add("write", _persist_trace)

    def _dir_persist(_a: Any = None, _b: Any = None, _c: Any = None) -> None:
        if _persist_job[0] is not None:
            try:
                root.after_cancel(_persist_job[0])
            except Exception:
                pass
        _persist_job[0] = root.after(400, do_persist)

    dir_var.trace_add("write", _dir_persist)

    def _k_o(_e: Any) -> str:
        choose_output_folder()
        return "break"

    def _k_err(_e: Any) -> str:
        open_error_log_externally()
        return "break"

    def _k_reveal(_e: Any) -> str:
        reveal_last_downloaded()
        return "break"

    root.bind_all("<Control-o>", _k_o)
    root.bind_all("<Control-Shift-O>", _k_err)
    root.bind_all("<Control-Shift-F>", _k_reveal)
    go_btn.config(command=start)
    stop_btn.config(command=cancel)
    open_btn.config(command=open_output_folder)
    apply_theme()
    watch_system_theme()

    root.update_idletasks()
    fixed_w = root.winfo_width()
    fixed_h = root.winfo_height()
    root.minsize(fixed_w, fixed_h)
    root.maxsize(fixed_w, fixed_h)
    gsave = saved.get("window_geometry")
    placed = False
    if gsave and isinstance(gsave, str) and re.fullmatch(r"\d+x\d+[-+]\d+[-+]\d+", gsave):
        try:
            root.geometry(gsave)
            placed = True
        except tk.TclError:
            placed = False
    if not placed:
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(
            f"{fixed_w}x{fixed_h}+{(sw - fixed_w) // 2}+{(sh - fixed_h) // 2}"
        )
    root.mainloop()
