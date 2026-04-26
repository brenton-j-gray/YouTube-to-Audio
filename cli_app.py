import sys
import threading
from pathlib import Path
from typing import Any

from converter_core import Converter


def cli(url: str, out_dir: str | Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    done = threading.Event()
    res: dict[str, Any] = {}

    def on_progress(p: float) -> None:
        b = int(p / 5)
        sys.stdout.write(f"\r  [{'█' * b}{'░' * (20 - b)}] {p:5.1f}%")
        sys.stdout.flush()

    def on_done(ok: bool, val: str) -> None:
        res.update(ok=ok, val=val)
        done.set()

    print(f"\n  URL : {url}")
    print(f"  Out : {out_dir}\n")
    # Quality label must match Converter.QUALITY_MAP (codec is WAV; quality key is ignored for lossless).
    c = Converter(url, out_dir, "Medium (192 kbps)", "WAV (44.1kHz 16-bit stereo)", on_progress, lambda s: None, on_done)
    threading.Thread(target=c.run, daemon=True).start()
    done.wait()
    print()
    if res.get("ok"):
        print(f"\n  ✓  Saved: {res['val']}\n")
    else:
        print(f"\n  ✗  Error: {res['val']}\n")
        sys.exit(1)
