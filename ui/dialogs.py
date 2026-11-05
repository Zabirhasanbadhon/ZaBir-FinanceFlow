"""Modal dialog base class plus colour/icon pickers shared by several pages."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import colorchooser, ttk
from typing import Callable

from config import COLOR_PRESETS
from core.context import AppContext
from database.db_manager import DatabaseError
from ui.components import RoundedButton, make_label, rounded_points, set_dark_titlebar, styled_entry
from ui.theme import font
from utils.validators import ValidationError, parse_date


class Dialog(tk.Toplevel):
    """Themed modal dialog.

    Subclasses implement ``build(body)`` and ``submit()``. ``submit`` raises
    ValidationError/DatabaseError to show an inline message; on success the
    dialog closes and ``ctx.notify_data_changed()`` refreshes every page.
    """

    def __init__(self, parent: tk.Misc, ctx: AppContext, title: str, *, subtitle: str = "",
                 width: int = 480, submit_text: str | None = "Save", notify: bool = True) -> None:
        super().__init__(parent)
        self.ctx, self.p = ctx, ctx.theme.palette
        self.submit_text, self._notify, self._busy, self._width = submit_text, notify, False, width
        p = self.p
        self.withdraw()
        self.title(title)
        self.configure(bg=p.card)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())

        head = tk.Frame(self, bg=p.card)
        head.pack(fill="x", padx=26, pady=(22, 10))
        make_label(head, p, title, size=15, bold=True).pack(anchor="w")
        if subtitle:
            make_label(head, p, subtitle, size=9, muted=True, wraplength=width - 60, justify="left").pack(anchor="w", pady=(2, 0))
        self.body = tk.Frame(self, bg=p.card)
        self.body.pack(fill="x", padx=26)
        self.error = tk.Label(self, text="", fg=p.danger, bg=p.card, font=font(9), wraplength=width - 60,
                              justify="left", anchor="w")
        self.error.pack(fill="x", padx=26, pady=(8, 0))
        self.build(self.body)

        foot = tk.Frame(self, bg=p.card)
        foot.pack(fill="x", padx=26, pady=(12, 22))
        self._buttons: dict[str, RoundedButton] = {}
        for text, command, style in self.buttons():
            btn = RoundedButton(foot, p, text, command, style=style, outer=p.card, height=38)
            btn.pack(side="right", padx=(8, 0))
            self._buttons[text] = btn

        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", self._on_return)
        self.update_idletasks()
        self._center(parent)
        self.deiconify()
        set_dark_titlebar(self, p.is_dark)
        self.after(30, self._grab)

    # ---- hooks ---------------------------------------------------------- #
    def build(self, body: tk.Frame) -> None:
        raise NotImplementedError

    def submit(self) -> None:
        """Validate and persist. Raise ValidationError/DatabaseError on problems."""

    def buttons(self) -> list[tuple[str, Callable[[], None], str]]:
        items: list[tuple[str, Callable[[], None], str]] = []
        if self.submit_text:
            items.append((self.submit_text, self._submit, "primary"))
            items.append(("Cancel", self.destroy, "secondary"))
        else:
            items.append(("Close", self.destroy, "secondary"))
        return items

    # ---- mechanics ------------------------------------------------------ #
    def _center(self, parent: tk.Misc) -> None:
        top = parent.winfo_toplevel()
        w, h = max(self.winfo_reqwidth(), self._width), self.winfo_reqheight()
        x = top.winfo_rootx() + (top.winfo_width() - w) // 2
        y = top.winfo_rooty() + max((top.winfo_height() - h) // 3, 20)
        self.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

    def _grab(self) -> None:
        try:
            self.grab_set()
            self.focus_set()
        except tk.TclError:
            pass

    def _on_return(self, event: tk.Event) -> None:
        if self.submit_text and not isinstance(event.widget, (tk.Text, ttk.Combobox)):
            self._submit()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if self.submit_text and self.submit_text in self._buttons:
            self._buttons[self.submit_text].set_enabled(not busy)

    def _submit(self) -> None:
        if self._busy:  # prevents duplicate submissions from double clicks
            return
        self.error.configure(text="")
        self._set_busy(True)
        try:
            self.submit()
        except (ValidationError, DatabaseError) as exc:
            self.error.configure(text=str(exc))
            self._set_busy(False)
            return
        except Exception:
            self._set_busy(False)
            raise
        ctx, notify = self.ctx, self._notify
        self.destroy()
        if notify:
            ctx.notify_data_changed()

    # ---- form helpers ---------------------------------------------------- #
    def field(self, label: str, hint: str = "", pady: tuple[int, int] = (0, 12)) -> tk.Frame:
        row = tk.Frame(self.body, bg=self.p.card)
        row.pack(fill="x", pady=pady)
        make_label(row, self.p, label, size=9, bold=True, muted=True).pack(anchor="w", pady=(0, 4))
        if hint:
            make_label(row, self.p, hint, size=8, muted=True).pack(anchor="w", pady=(0, 3))
        return row

    def entry_field(self, label: str, initial: str = "", hint: str = "") -> tk.StringVar:
        var = tk.StringVar(value=initial)
        styled_entry(self.field(label, hint), self.p, var, width=10).pack(fill="x", ipady=7)
        return var

    def combo_field(self, label: str, values: list[str], initial: str = "", *, readonly: bool = True) -> ttk.Combobox:
        box = ttk.Combobox(self.field(label), values=values, state="readonly" if readonly else "normal", font=font(10))
        box.pack(fill="x", ipady=4)
        if initial:
            box.set(initial)
        elif values and readonly:
            box.set(values[0])
        return box

    def date_field(self, label: str, iso: str | None, optional: bool = False) -> tk.StringVar:
        example = self.ctx.date(date.today().isoformat())
        initial = self.ctx.date(iso) if iso else ""
        hint = f"Format: {example}" + (" \u2013 leave empty for none" if optional else "")
        return self.entry_field(label + (" (optional)" if optional else ""), initial, hint)

    def read_date(self, var: tk.StringVar, label: str, optional: bool = False) -> str | None:
        text = var.get().strip()
        if not text and optional:
            return None
        return parse_date(text, self.ctx.date_format, field=label)


class ColorPicker(tk.Frame):
    """Row of preset swatches plus a custom colour chooser."""

    def __init__(self, parent: tk.Misc, p, value: str) -> None:
        super().__init__(parent, bg=p.card)
        self.p, self.value = p, value
        self.canvas = tk.Canvas(self, height=64, width=1, bg=p.card, highlightthickness=0)
        self.canvas.pack(fill="x")
        self._cols = 6
        self.canvas.bind("<Configure>", lambda _e: self._draw())
        self._draw()

    def _cells(self) -> list[tuple[str, int, int]]:
        return [(c, 6 + (i % self._cols) * 42, 4 + (i // self._cols) * 30) for i, c in enumerate(COLOR_PRESETS)]

    def _draw(self) -> None:
        cv = self.canvas
        cv.delete("all")
        for color, x, y in self._cells():
            cv.create_oval(x, y, x + 24, y + 24, fill=color, outline=self.p.text if color.lower() == self.value.lower() else "",
                           width=3, tags=("sw", color))
        x = 6 + self._cols * 42
        cv.create_text(x + 10, 17, text="Custom\u2026", anchor="w", fill=self.p.primary, font=font(9, "bold"), tags="custom")
        cv.create_oval(x + 80, 6, x + 98, 24, fill=self.value, outline=self.p.border, tags="current")
        cv.tag_bind("sw", "<Button-1>", self._pick)
        cv.tag_bind("custom", "<Button-1>", self._custom)
        cv.configure(cursor="hand2")

    def _pick(self, event: tk.Event) -> None:
        item = self.canvas.find_closest(event.x, event.y)[0]
        for tag in self.canvas.gettags(item):
            if tag.startswith("#"):
                self.value = tag
        self._draw()

    def _custom(self, _e: tk.Event) -> None:
        chosen = colorchooser.askcolor(color=self.value, parent=self.winfo_toplevel(), title="Choose a colour")[1]
        if chosen:
            self.value = chosen.upper()
            self._draw()

    def get(self) -> str:
        return self.value


class IconPicker(tk.Frame):
    """Grid of selectable icons drawn with Pillow."""

    def __init__(self, parent: tk.Misc, ctx: AppContext, icons: list[str], value: str, accent: str,
                 per_row: int = 10) -> None:
        super().__init__(parent, bg=ctx.theme.palette.card)
        self.ctx, self.p, self.icons, self.value, self.accent = ctx, ctx.theme.palette, icons, value, accent
        self.per_row = per_row
        self.cells: dict[str, tk.Canvas] = {}
        for i, name in enumerate(icons):
            cell = tk.Canvas(self, width=36, height=36, bg=self.p.card, highlightthickness=0, cursor="hand2")
            cell.grid(row=i // per_row, column=i % per_row, padx=2, pady=2)
            cell.bind("<Button-1>", lambda _e, n=name: self.select(n))
            self.cells[name] = cell
        self._paint()

    def set_accent(self, color: str) -> None:
        self.accent = color
        self._paint()

    def _paint(self) -> None:
        for name, cell in self.cells.items():
            on = name == self.value
            cell.delete("all")
            if on:
                cell.create_polygon(rounded_points(1, 1, 35, 35, 10), smooth=True, fill=self.p.mix(self.accent, 0.2),
                                    outline=self.accent, width=1)
            img = self.ctx.images.icon(name, 20, self.accent if on else self.p.text_muted)
            cell._img = img
            cell.create_image(18, 18, image=img)

    def select(self, name: str) -> None:
        self.value = name
        self._paint()

    def get(self) -> str:
        return self.value
