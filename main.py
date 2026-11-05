"""ZaBir FinanceFlow – application entry point.

Run from the project folder with:  python main.py
"""
from __future__ import annotations

import logging
import sys


def _configure_logging() -> None:
    from config import LOG_PATH, ensure_directories

    ensure_directories()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler(sys.stderr)],
    )


def _enable_dpi_awareness() -> None:
    """Crisp text on high-DPI Windows displays (no-op elsewhere)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def main() -> int:
    try:
        import tkinter  # noqa: F401
        import PIL  # noqa: F401
        import matplotlib  # noqa: F401
    except ImportError as exc:
        print(f"Missing dependency: {exc}\nInstall everything with:  pip install -r requirements.txt")
        return 1

    _configure_logging()
    _enable_dpi_awareness()

    from core.context import AppContext
    from ui.main_window import MainWindow

    ctx = AppContext()
    app = MainWindow(ctx)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
