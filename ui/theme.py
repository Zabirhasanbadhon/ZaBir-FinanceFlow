"""Dark / light colour palettes, font helper and ttk styling."""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from config import FONT_FAMILY


def _rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def blend(base: str, over: str, amount: float) -> str:
    """Mix ``over`` into ``base`` by ``amount`` (0..1) and return a hex colour."""
    b, o = _rgb(base), _rgb(over)
    mixed = tuple(round(b[i] * (1 - amount) + o[i] * amount) for i in range(3))
    return "#{:02X}{:02X}{:02X}".format(*mixed)


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    sidebar: str
    card: str
    card_alt: str
    border: str
    hover: str
    primary: str
    primary_hover: str
    secondary: str
    danger: str
    warning: str
    text: str
    text_muted: str
    on_primary: str
    shadow: str

    @property
    def is_dark(self) -> bool:
        return self.name == "dark"

    def mix(self, color: str, amount: float, base: str | None = None) -> str:
        """Tinted version of ``color`` over ``base`` (default: card colour)."""
        return blend(base or self.card, color, amount)


DARK = Palette(
    name="dark", bg="#0F172A", sidebar="#111C31", card="#1E293B", card_alt="#273449",
    border="#2C3B54", hover="#243248", primary="#6366F1", primary_hover="#7C7FF5",
    secondary="#22C55E", danger="#EF4444", warning="#F59E0B", text="#F8FAFC",
    text_muted="#94A3B8", on_primary="#FFFFFF", shadow="#080D1A",
)

LIGHT = Palette(
    name="light", bg="#F5F7FB", sidebar="#FFFFFF", card="#FFFFFF", card_alt="#F1F5F9",
    border="#E2E8F0", hover="#EEF2FF", primary="#4F46E5", primary_hover="#6159F0",
    secondary="#16A34A", danger="#DC2626", warning="#D97706", text="#172033",
    text_muted="#64748B", on_primary="#FFFFFF", shadow="#DDE3EE",
)

PALETTES = {"dark": DARK, "light": LIGHT}


class ThemeManager:
    """Holds the active palette. Persistence is handled by the AppContext."""

    def __init__(self, name: str = "dark") -> None:
        self.name = name if name in PALETTES else "dark"

    @property
    def palette(self) -> Palette:
        return PALETTES[self.name]

    def set(self, name: str) -> None:
        if name in PALETTES:
            self.name = name

    def toggle(self) -> str:
        self.name = "light" if self.name == "dark" else "dark"
        return self.name


def font(size: int = 10, weight: str = "normal") -> tuple[str, int, str]:
    return (FONT_FAMILY, size, weight)


def apply_ttk_styles(root: tk.Misc, p: Palette) -> None:
    """Style the few native ttk widgets used (Combobox, Scrollbar) for the theme."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(
        "TCombobox", fieldbackground=p.card_alt, background=p.card_alt, foreground=p.text,
        arrowcolor=p.text_muted, bordercolor=p.border, lightcolor=p.card_alt,
        darkcolor=p.card_alt, padding=6, relief="flat",
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", p.card_alt)],
        foreground=[("readonly", p.text)],
        selectbackground=[("readonly", p.card_alt)],
        selectforeground=[("readonly", p.text)],
        bordercolor=[("focus", p.primary)],
    )
    root.option_add("*TCombobox*Listbox.background", p.card)
    root.option_add("*TCombobox*Listbox.foreground", p.text)
    root.option_add("*TCombobox*Listbox.selectBackground", p.primary)
    root.option_add("*TCombobox*Listbox.selectForeground", p.on_primary)
    root.option_add("*TCombobox*Listbox.font", font(10))

    style.layout(
        "App.Vertical.TScrollbar",
        [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})],
    )
    style.configure(
        "App.Vertical.TScrollbar", troughcolor=p.bg, background=p.border,
        bordercolor=p.bg, lightcolor=p.border, darkcolor=p.border, width=10, relief="flat",
    )
    style.map("App.Vertical.TScrollbar", background=[("active", p.text_muted)])

    style.configure("App.Treeview", background=p.card, fieldbackground=p.card, foreground=p.text,
                    bordercolor=p.card, borderwidth=0, rowheight=40, font=font(10), relief="flat")
    style.map("App.Treeview", background=[("selected", p.mix(p.primary, 0.24))],
              foreground=[("selected", p.text)])
    style.layout("App.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("App.Treeview.Heading", background=p.card_alt, foreground=p.text_muted, relief="flat",
                    font=font(9, "bold"), padding=(10, 10), borderwidth=0)
    style.map("App.Treeview.Heading", background=[("active", p.hover)])
    style.configure("App.Horizontal.TProgressbar", troughcolor=p.card_alt, background=p.primary,
                    bordercolor=p.card_alt, lightcolor=p.primary, darkcolor=p.primary, thickness=6)
