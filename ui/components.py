"""Reusable themed widgets: cards, buttons, progress bars, scroll frames, etc."""
from __future__ import annotations

import logging
import queue
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from typing import Any, Callable, Sequence

from ui.theme import Palette, blend, font
from utils.image_manager import ImageManager


def rounded_points(x1: float, y1: float, x2: float, y2: float, r: float) -> list[float]:
    """Polygon points that render as a rounded rectangle when ``smooth=True``."""
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
        x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1,
    ]


def make_label(parent: tk.Misc, p: Palette, text: str = "", *, size: int = 10, bold: bool = False,
               muted: bool = False, color: str | None = None, bg: str | None = None,
               **kwargs) -> tk.Label:
    return tk.Label(
        parent, text=text, font=font(size, "bold" if bold else "normal"),
        fg=color or (p.text_muted if muted else p.text), bg=bg or p.card, **kwargs,
    )


# --------------------------------------------------------------------------- #
# Card
# --------------------------------------------------------------------------- #
class Card(tk.Canvas):
    """Rounded, softly shadowed container. Put content inside ``card.body``.

    The canvas sizes itself to the body's requested height, and the body is
    stretched to the canvas width, so cards behave like normal responsive frames.
    """

    def __init__(self, parent: tk.Misc, p: Palette, *, radius: int = 16, padding: int = 18,
                 outer: str | None = None, fill: str | None = None) -> None:
        self.p = p
        self.radius = radius
        self.pad = padding
        self.fill = fill or p.card
        super().__init__(parent, bg=outer or p.bg, highlightthickness=0, bd=0, width=1, height=1)
        self.body = tk.Frame(self, bg=self.fill)
        self._win = self.create_window(padding, padding, anchor="nw", window=self.body)
        self.bind("<Configure>", self._on_canvas)
        self.body.bind("<Configure>", self._on_body)

    def _on_canvas(self, event: tk.Event) -> None:
        self.itemconfigure(self._win, width=max(1, event.width - 2 * self.pad))
        self._redraw(event.width, event.height)

    def _on_body(self, event: tk.Event) -> None:
        needed = event.height + 2 * self.pad + 3
        if int(self.cget("height")) != needed:
            self.configure(height=needed)

    def _redraw(self, w: int, h: int) -> None:
        self.delete("bg")
        if w < 4 or h < 4:
            return
        self.create_polygon(rounded_points(1, 4, w - 1, h - 1, self.radius), smooth=True,
                            fill=self.p.shadow, outline="", tags="bg")
        self.create_polygon(rounded_points(1, 1, w - 1, h - 4, self.radius), smooth=True,
                            fill=self.fill, outline=self.p.border, tags="bg")
        self.tag_lower("bg")


def card_header(parent: tk.Misc, p: Palette, title: str, subtitle: str | None = None, *,
                action: tuple[str, Callable[[], None]] | None = None, bg: str | None = None) -> tk.Frame:
    """Title row used at the top of dashboard cards, with an optional link action."""
    bg = bg or p.card
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", pady=(0, 12))
    left = tk.Frame(row, bg=bg)
    left.pack(side="left")
    make_label(left, p, title, size=12, bold=True, bg=bg).pack(anchor="w")
    if subtitle:
        make_label(left, p, subtitle, size=9, muted=True, bg=bg).pack(anchor="w")
    if action:
        link = tk.Label(row, text=action[0], font=font(9, "bold"), fg=p.primary, bg=bg, cursor="hand2")
        link.pack(side="right", anchor="n")
        link.bind("<Button-1>", lambda _e: action[1]())
        link.bind("<Enter>", lambda _e: link.configure(fg=p.primary_hover))
        link.bind("<Leave>", lambda _e: link.configure(fg=p.primary))
    return row


# --------------------------------------------------------------------------- #
# Buttons
# --------------------------------------------------------------------------- #
class RoundedButton(tk.Canvas):
    """Flat rounded button with hover feedback. Styles: primary, secondary, danger, ghost."""

    def __init__(self, parent: tk.Misc, p: Palette, text: str, command: Callable[[], None], *,
                 style: str = "primary", icon: tk.PhotoImage | None = None, height: int = 38,
                 radius: int = 10, outer: str | None = None, min_width: int = 0) -> None:
        self.p, self.command, self._text, self._icon = p, command, text, icon
        self.style, self.radius, self._enabled, self._bhover = style, radius, True, False
        self._fnt = font(10, "bold")
        measured = tkfont.Font(font=self._fnt).measure(text)
        width = max(min_width, measured + 32 + (26 if icon else 0))
        super().__init__(parent, width=width, height=height, bg=outer or p.bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._bw, self._bh = width, height
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._on_release)
        self._draw()

    def _colors(self) -> tuple[str, str, str]:
        p = self.p
        if not self._enabled:
            return p.card_alt, p.text_muted, p.border
        if self.style == "primary":
            return (p.primary_hover if self._bhover else p.primary), p.on_primary, ""
        if self.style == "danger":
            return (blend(p.danger, "#000000", 0.15) if self._bhover else p.danger), "#FFFFFF", ""
        if self.style == "ghost":
            return (p.hover if self._bhover else self.cget("bg")), p.text, ""
        return (p.hover if self._bhover else p.card_alt), p.text, p.border

    def _draw(self) -> None:
        self.delete("all")
        fill, fg, border = self._colors()
        self.create_polygon(rounded_points(1, 1, self._bw - 1, self._bh - 1, self.radius), smooth=True,
                            fill=fill, outline=border)
        cy = self._bh / 2
        if self._icon:
            tw = tkfont.Font(font=self._fnt).measure(self._text)
            start = (self._bw - (tw + 26)) / 2
            self.create_image(start + 9, cy, image=self._icon)
            self.create_text(start + 26, cy, text=self._text, fill=fg, font=self._fnt, anchor="w")
        else:
            self.create_text(self._bw / 2, cy, text=self._text, fill=fg, font=self._fnt)

    def _set_hover(self, value: bool) -> None:
        self._bhover = value
        self._draw()

    def _on_release(self, event: tk.Event) -> None:
        if self._enabled and 0 <= event.x <= self._bw and 0 <= event.y <= self._bh:
            self.command()

    def set_text(self, text: str) -> None:
        self._text = text
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()


class IconButton(tk.Canvas):
    """Square icon button with hover background and optional notification badge."""

    def __init__(self, parent: tk.Misc, p: Palette, images: ImageManager, icon: str,
                 command: Callable[[], None], *, size: int = 40, icon_size: int = 20,
                 outer: str | None = None, badge: int = 0, tooltip_color: str | None = None) -> None:
        super().__init__(parent, width=size, height=size, bg=outer or p.bg, highlightthickness=0,
                         bd=0, cursor="hand2")
        self.p, self.images, self.command = p, images, command
        self.dim, self.icon_size, self.badge, self.icon_name = size, icon_size, badge, icon
        self._tint = tooltip_color or p.text_muted
        self._hover = False
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", lambda _e: self.command())
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        s = self.dim
        if self._hover:
            self.create_polygon(rounded_points(1, 1, s - 1, s - 1, 12), smooth=True,
                                fill=self.p.hover, outline="")
        color = self.p.text if self._hover else self._tint
        self._img = self.images.icon(self.icon_name, self.icon_size, color)
        self.create_image(s / 2, s / 2, image=self._img)
        if self.badge > 0:
            self.create_oval(s - 17, 4, s - 3, 18, fill=self.p.danger, outline=self.cget("bg"), width=2)
            self.create_text(s - 10, 11, text=str(min(self.badge, 9)), fill="#FFFFFF", font=font(7, "bold"))

    def _set_hover(self, value: bool) -> None:
        self._hover = value
        self._draw()

    def set_icon(self, icon: str) -> None:
        self.icon_name = icon
        self._draw()

    def set_badge(self, count: int) -> None:
        self.badge = count
        self._draw()


# --------------------------------------------------------------------------- #
# Progress bar
# --------------------------------------------------------------------------- #
class ProgressBar(tk.Canvas):
    """Pill-shaped progress bar; ``value`` is a 0..1 ratio (values >1 are clamped)."""

    def __init__(self, parent: tk.Misc, p: Palette, value: float, color: str, *,
                 height: int = 10, outer: str | None = None, track: str | None = None) -> None:
        super().__init__(parent, width=1, height=height, bg=outer or p.card, highlightthickness=0, bd=0)
        self.value = max(0.0, min(value, 1.0))
        self.color = color
        self.track = track or p.card_alt
        self.bind("<Configure>", lambda e: self._draw(e.width, e.height))

    def _draw(self, w: int, h: int) -> None:
        self.delete("all")
        if w < 4:
            return
        r = h / 2
        self.create_polygon(rounded_points(0, 0, w, h, r), smooth=True, fill=self.track, outline="")
        fill_w = max(h, w * self.value) if self.value > 0 else 0
        if fill_w:
            self.create_polygon(rounded_points(0, 0, fill_w, h, r), smooth=True, fill=self.color, outline="")


# --------------------------------------------------------------------------- #
# Scrollable container
# --------------------------------------------------------------------------- #
class ScrollableFrame(tk.Frame):
    """Vertically scrollable frame with mouse-wheel support. Add widgets to ``.inner``."""

    _wheel_installed = False

    def __init__(self, parent: tk.Misc, p: Palette) -> None:
        from tkinter import ttk

        super().__init__(parent, bg=p.bg)
        self.canvas = tk.Canvas(self, bg=p.bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                       style="App.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=p.bg)
        self._win = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        if not ScrollableFrame._wheel_installed:
            root = self.winfo_toplevel()
            root.bind_all("<MouseWheel>", ScrollableFrame._on_wheel, add="+")
            root.bind_all("<Button-4>", ScrollableFrame._on_wheel, add="+")
            root.bind_all("<Button-5>", ScrollableFrame._on_wheel, add="+")
            ScrollableFrame._wheel_installed = True

    @staticmethod
    def _on_wheel(event: tk.Event) -> None:
        try:
            widget = event.widget.winfo_containing(event.x_root, event.y_root)
        except (KeyError, AttributeError, tk.TclError):
            return
        while widget is not None:
            if isinstance(widget, ScrollableFrame):
                canvas = widget.canvas
                if canvas.yview() != (0.0, 1.0):
                    if event.num == 4:
                        step = -1
                    elif event.num == 5:
                        step = 1
                    else:
                        step = -1 if event.delta > 0 else 1
                    canvas.yview_scroll(step * 2, "units")
                return
            widget = getattr(widget, "master", None)


# --------------------------------------------------------------------------- #
# Composite widgets
# --------------------------------------------------------------------------- #
class StatCard(Card):
    """KPI card: title, big value, coloured subtitle and a tinted icon bubble."""

    def __init__(self, parent: tk.Misc, p: Palette, images: ImageManager, *, title: str, value: str,
                 subtitle: str, icon: str, accent: str, subtitle_color: str | None = None) -> None:
        super().__init__(parent, p, padding=16)
        body = self.body
        top = tk.Frame(body, bg=p.card)
        top.pack(fill="x")
        make_label(top, p, title, size=9, muted=True).pack(side="left", anchor="n", pady=(2, 0))
        self._bubble = images.circle_icon(icon, 38, p.mix(accent, 0.16), accent)
        tk.Label(top, image=self._bubble, bg=p.card).pack(side="right")
        make_label(body, p, value, size=16, bold=True).pack(anchor="w", pady=(2, 2))
        make_label(body, p, subtitle, size=9, color=subtitle_color or p.text_muted).pack(anchor="w")


class EmptyState(tk.Frame):
    """Friendly placeholder shown when a section has no data yet."""

    def __init__(self, parent: tk.Misc, p: Palette, images: ImageManager, *, icon: str, title: str,
                 message: str, bg: str | None = None, pady: int = 18) -> None:
        bg = bg or p.card
        super().__init__(parent, bg=bg)
        self._img = images.circle_icon(icon, 52, p.mix(p.primary, 0.14, bg), p.primary)
        tk.Label(self, image=self._img, bg=bg).pack(pady=(pady, 8))
        make_label(self, p, title, size=11, bold=True, bg=bg).pack()
        make_label(self, p, message, size=9, muted=True, bg=bg, wraplength=260, justify="center").pack(pady=(2, pady))


class PageHeader(tk.Frame):
    """Page title + subtitle with a slot (``.actions``) for right-aligned controls."""

    def __init__(self, parent: tk.Misc, p: Palette, title: str, subtitle: str = "") -> None:
        super().__init__(parent, bg=p.bg)
        left = tk.Frame(self, bg=p.bg)
        left.pack(side="left")
        make_label(left, p, title, size=20, bold=True, bg=p.bg).pack(anchor="w")
        if subtitle:
            make_label(left, p, subtitle, size=10, muted=True, bg=p.bg).pack(anchor="w", pady=(2, 0))
        self.actions = tk.Frame(self, bg=p.bg)
        self.actions.pack(side="right")


# --------------------------------------------------------------------------- #
# Inputs, segmented control, background tasks
# --------------------------------------------------------------------------- #
def styled_entry(parent: tk.Misc, p: Palette, variable: tk.StringVar | None = None, *, width: int = 24,
                 bg: str | None = None, justify: str = "left") -> tk.Entry:
    """Flat entry with a border that turns accent-coloured on focus."""
    return tk.Entry(parent, textvariable=variable, width=width, font=font(10), bg=bg or p.card_alt, fg=p.text,
                    insertbackground=p.text, bd=0, relief="flat", highlightthickness=1,
                    highlightbackground=p.border, highlightcolor=p.primary, justify=justify,
                    disabledbackground=p.card_alt, disabledforeground=p.text_muted)


class Segmented(tk.Frame):
    """Pill-style toggle between a few options, e.g. Income | Expense."""

    def __init__(self, parent: tk.Misc, p: Palette, options: Sequence[tuple[str, str]], value: str,
                 command: Callable[[str], None], *, outer: str | None = None) -> None:
        super().__init__(parent, bg=p.card_alt, highlightthickness=1, highlightbackground=p.border)
        self.p, self.value, self.command, self._labels = p, value, command, {}
        for label, key in options:
            lbl = tk.Label(self, text=label, font=font(10, "bold"), padx=18, pady=6, cursor="hand2")
            lbl.pack(side="left", padx=2, pady=2)
            lbl.bind("<Button-1>", lambda _e, k=key: self.set(k, fire=True))
            self._labels[key] = lbl
        self._paint()

    def _paint(self) -> None:
        for key, lbl in self._labels.items():
            on = key == self.value
            lbl.configure(bg=self.p.primary if on else self.p.card_alt,
                          fg=self.p.on_primary if on else self.p.text_muted)

    def set(self, key: str, fire: bool = False) -> None:
        self.value = key
        self._paint()
        if fire:
            self.command(key)


def set_dark_titlebar(window: tk.Misc, dark: bool) -> None:
    """Use the immersive dark title bar on Windows 10/11 (best effort, silent elsewhere)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        logging.getLogger(__name__).debug("Title bar theming unavailable", exc_info=True)


def run_in_background(widget: tk.Misc, work: Callable[[], Any],
                      on_done: Callable[[Any, Exception | None], None]) -> None:
    """Run ``work`` in a thread; ``on_done(result, error)`` fires on the Tk thread.

    Keeps the interface responsive during long exports.
    """
    results: queue.Queue = queue.Queue()

    def target() -> None:
        try:
            results.put((work(), None))
        except Exception as exc:  # noqa: BLE001 - forwarded to the caller
            logging.getLogger(__name__).exception("Background task failed")
            results.put((None, exc))

    threading.Thread(target=target, daemon=True).start()

    def poll() -> None:
        try:
            result, error = results.get_nowait()
        except queue.Empty:
            try:
                widget.after(80, poll)
            except tk.TclError:
                pass
            return
        try:
            if widget.winfo_exists():
                on_done(result, error)
        except tk.TclError:
            pass

    widget.after(80, poll)
