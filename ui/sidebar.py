"""Left navigation sidebar."""
from __future__ import annotations

import tkinter as tk
from typing import Callable

from PIL import ImageTk

from config import APP_TAGLINE, NAV_ITEMS, SIDEBAR_WIDTH
from core.context import AppContext
from ui.components import make_label, rounded_points
from ui.theme import font


class NavItem(tk.Canvas):
    """One rounded navigation entry with hover and active states."""

    def __init__(self, parent: tk.Misc, ctx: AppContext, key: str, label: str, icon: str,
                 on_click: Callable[[str], None]) -> None:
        self.p = ctx.theme.palette
        super().__init__(parent, height=44, width=1, bg=self.p.sidebar, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.ctx, self.key, self.label, self.icon = ctx, key, label, icon
        self.active, self._hover = False, False
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", lambda _e: on_click(key))

    def _draw(self) -> None:
        p, w = self.p, self.winfo_width()
        self.delete("all")
        if w < 10:
            return
        if self.active:
            fill = p.mix(p.primary, 0.16, p.sidebar)
        elif self._hover:
            fill = p.mix(p.text, 0.06, p.sidebar)
        else:
            fill = ""
        if fill:
            self.create_polygon(rounded_points(0, 2, w, 42, 12), smooth=True, fill=fill, outline="")
        if self.active:
            self.create_polygon(rounded_points(0, 12, 4, 32, 2), smooth=True, fill=p.primary, outline="")
        color = p.primary if self.active else (p.text if self._hover else p.text_muted)
        self._img = self.ctx.images.icon(self.icon, 20, color)
        self.create_image(28, 22, image=self._img)
        self.create_text(52, 22, text=self.label, anchor="w", fill=p.text if self.active or self._hover else p.text_muted,
                         font=font(10, "bold" if self.active else "normal"))

    def _set_hover(self, value: bool) -> None:
        self._hover = value
        self._draw()

    def set_active(self, active: bool) -> None:
        self.active = active
        self._draw()


class Sidebar(tk.Frame):
    def __init__(self, parent: tk.Misc, ctx: AppContext, active: str, on_select: Callable[[str], None]) -> None:
        p = ctx.theme.palette
        super().__init__(parent, bg=p.sidebar, width=SIDEBAR_WIDTH)
        self.pack_propagate(False)
        self.ctx = ctx
        # right-hand divider
        tk.Frame(self, bg=p.border, width=1).pack(side="right", fill="y")

        inner = tk.Frame(self, bg=p.sidebar)
        inner.pack(fill="both", expand=True, padx=14)
        make_label(inner, p, "MENU", size=8, bold=True, muted=True, bg=p.sidebar).pack(anchor="w", padx=12, pady=(18, 8))

        self.items: dict[str, NavItem] = {}
        for key, label, icon in NAV_ITEMS:
            item = NavItem(inner, ctx, key, label, icon, on_select)
            item.pack(fill="x", pady=1)
            self.items[key] = item
        self.set_active(active)
        self._build_promo(inner)

    def _build_promo(self, parent: tk.Misc) -> None:
        p = self.ctx.theme.palette
        w, h = SIDEBAR_WIDTH - 29, 150
        canvas = tk.Canvas(parent, width=w, height=h, bg=p.sidebar, highlightthickness=0, bd=0)
        canvas.pack(side="bottom", pady=(0, 18))
        self._promo = ImageTk.PhotoImage(self.ctx.images.banner_image(w, h, "#4F46E5", "#9333EA", radius=18))
        canvas.create_image(0, 0, anchor="nw", image=self._promo)
        for i, word in enumerate(APP_TAGLINE.split(" ")):
            canvas.create_text(18, 34 + i * 26, text=word, anchor="w", fill="#FFFFFF", font=font(14, "bold"))
        canvas.create_text(18, h - 18, text="Your money, clearly.", anchor="w", fill="#E0E7FF", font=font(8))

    def set_active(self, key: str) -> None:
        for item_key, item in self.items.items():
            item.set_active(item_key == key)
