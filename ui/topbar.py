"""Top navigation bar: brand, date, global search, notifications, theme, profile."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import messagebox
from typing import Callable

from config import APP_NAME, APP_VERSION, SIDEBAR_WIDTH, TOPBAR_HEIGHT
from core.context import AppContext
from ui.components import IconButton, make_label, rounded_points
from ui.theme import font
from utils.helpers import initials, today_iso


class SearchBox(tk.Canvas):
    """Rounded global-search field with placeholder and Enter-to-submit."""

    PLACEHOLDER = "Search transactions by description\u2026"

    def __init__(self, parent: tk.Misc, ctx: AppContext, on_submit: Callable[[str], None]) -> None:
        self.p = ctx.theme.palette
        p = self.p
        super().__init__(parent, height=42, width=1, bg=p.sidebar, highlightthickness=0, bd=0)
        self.on_submit, self._focused, self._placeholder_active = on_submit, False, False
        self._icon = ctx.images.icon("search", 18, p.text_muted)
        self.entry = tk.Entry(self, bd=0, relief="flat", bg=p.card_alt, fg=p.text, insertbackground=p.text,
                              font=font(10), highlightthickness=0)
        self._win = self.create_window(44, 21, anchor="w", window=self.entry, height=24)
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Return>", lambda _e: self._submit())
        self.entry.bind("<Escape>", lambda _e: self._clear())
        self.bind("<Configure>", lambda e: self._draw(e.width, e.height))
        if ctx.search_query:
            self.entry.insert(0, ctx.search_query)
        else:
            self._show_placeholder()

    def _draw(self, w: int, h: int) -> None:
        self.delete("bg")
        self.create_polygon(rounded_points(1, 1, w - 1, h - 1, 14), smooth=True, fill=self.p.card_alt,
                            outline=self.p.primary if self._focused else self.p.border, tags="bg")
        self.create_image(24, h / 2, image=self._icon, tags="bg")
        self.tag_lower("bg")
        self.itemconfigure(self._win, width=max(20, w - 64))

    def _show_placeholder(self) -> None:
        self._placeholder_active = True
        self.entry.delete(0, "end")
        self.entry.insert(0, self.PLACEHOLDER)
        self.entry.configure(fg=self.p.text_muted)

    def _on_focus_in(self, _e: tk.Event) -> None:
        self._focused = True
        if self._placeholder_active:
            self.entry.delete(0, "end")
            self.entry.configure(fg=self.p.text)
            self._placeholder_active = False
        self._draw(self.winfo_width(), self.winfo_height())

    def _on_focus_out(self, _e: tk.Event) -> None:
        self._focused = False
        if not self.entry.get().strip():
            self._show_placeholder()
        self._draw(self.winfo_width(), self.winfo_height())

    def _submit(self) -> None:
        text = "" if self._placeholder_active else self.entry.get().strip()
        self.on_submit(text)

    def _clear(self) -> None:
        self.entry.delete(0, "end")
        self.on_submit("")
        self.winfo_toplevel().focus_set()


class Topbar(tk.Frame):
    def __init__(self, parent: tk.Misc, ctx: AppContext, on_search: Callable[[str], None],
                 on_toggle_theme: Callable[[], None]) -> None:
        p = ctx.theme.palette
        super().__init__(parent, bg=p.sidebar, height=TOPBAR_HEIGHT)
        self.pack_propagate(False)
        self.ctx, self.p = ctx, p
        self.on_toggle_theme = on_toggle_theme

        # Brand (aligned with the sidebar width)
        brand = tk.Frame(self, bg=p.sidebar, width=SIDEBAR_WIDTH)
        brand.pack(side="left", fill="y")
        brand.pack_propagate(False)
        self._logo = ctx.images.logo(36)
        tk.Label(brand, image=self._logo, bg=p.sidebar).pack(side="left", padx=(20, 10))
        make_label(brand, p, APP_NAME, size=12, bold=True, bg=p.sidebar).pack(side="left")

        # Right-hand controls (packed before the expanding search box)
        right = tk.Frame(self, bg=p.sidebar)
        right.pack(side="right", fill="y", padx=(8, 22))
        self._build_profile(right)
        self.theme_btn = IconButton(right, p, ctx.images, "sun" if p.is_dark else "moon",
                                    on_toggle_theme, outer=p.sidebar)
        self.theme_btn.pack(side="right", padx=(0, 8), pady=14)
        self.bell_btn = IconButton(right, p, ctx.images, "bell", self._show_notifications, outer=p.sidebar)
        self.bell_btn.pack(side="right", padx=(0, 4), pady=14)

        today = date.today()
        make_label(self, p, f"{today:%A}, {ctx.date(today_iso())}", size=10, muted=True,
                   bg=p.sidebar).pack(side="right", padx=(0, 16))

        self.search = SearchBox(self, ctx, on_search)
        self.search.pack(side="left", fill="x", expand=True, padx=(8, 16), pady=13)
        self.refresh_notifications()

    def _build_profile(self, parent: tk.Misc) -> None:
        p, ctx = self.p, self.ctx
        box = tk.Frame(parent, bg=p.sidebar, cursor="hand2")
        box.pack(side="right", padx=(8, 0), pady=14)
        self._avatar = ctx.images.avatar(initials(ctx.user_name), 38)
        avatar = tk.Label(box, image=self._avatar, bg=p.sidebar)
        avatar.pack(side="left")
        text = tk.Frame(box, bg=p.sidebar)
        text.pack(side="left", padx=(10, 0))
        name = make_label(text, p, ctx.user_name, size=10, bold=True, bg=p.sidebar)
        name.pack(anchor="w")
        role = make_label(text, p, "Personal account", size=8, muted=True, bg=p.sidebar)
        role.pack(anchor="w")
        for widget in (box, avatar, text, name, role):
            widget.bind("<Button-1>", self._show_profile_menu)

    def _menu(self) -> tk.Menu:
        p = self.p
        return tk.Menu(self, tearoff=0, bg=p.card, fg=p.text, activebackground=p.primary,
                       activeforeground=p.on_primary, bd=0, relief="flat", font=font(10))

    def _show_profile_menu(self, event: tk.Event) -> None:
        menu = self._menu()
        menu.add_command(label="Settings", command=lambda: self.ctx.navigate("settings"))
        menu.add_command(label="Switch to light theme" if self.p.is_dark else "Switch to dark theme",
                         command=self.on_toggle_theme)
        menu.add_separator()
        menu.add_command(label=f"About {APP_NAME}", command=self._about)
        try:
            menu.tk_popup(event.x_root, event.y_root + 12)
        finally:
            menu.grab_release()

    def _about(self) -> None:
        messagebox.showinfo(f"About {APP_NAME}",
                            f"{APP_NAME}\nVersion {APP_VERSION}\n\nA local-first personal finance manager.\n"
                            "All data is stored on this computer.")

    def refresh_notifications(self) -> None:
        self.alerts = self.ctx.alerts()
        self.bell_btn.set_badge(len(self.alerts))

    def _show_notifications(self) -> None:
        menu = self._menu()
        menu.add_command(label="Notifications", state="disabled")
        menu.add_separator()
        if not self.alerts:
            menu.add_command(label="You're all caught up", state="disabled")
        for alert in self.alerts[:8]:
            marker = "\u25cf " if alert.level == "danger" else "\u25b2 "
            menu.add_command(label=f"{marker}{alert.title} \u2014 {alert.message}",
                             command=lambda t=alert.target: self.ctx.navigate(t))
        x = self.bell_btn.winfo_rootx() - 200
        y = self.bell_btn.winfo_rooty() + self.bell_btn.winfo_height() + 4
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()
