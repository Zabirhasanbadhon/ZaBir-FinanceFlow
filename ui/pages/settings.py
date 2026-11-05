"""Settings: theme, currency, date format, dashboard month, backup and app info."""
from __future__ import annotations

import platform
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config import APP_NAME, APP_VERSION, BACKUP_DIR, CURRENCIES, DATE_FORMATS, DB_PATH
from core.context import AppContext
from database.db_manager import DatabaseError
from ui.components import (Card, PageHeader, RoundedButton, ScrollableFrame, Segmented, card_header, make_label,
                           rounded_points, run_in_background)
from ui.pages.base import BasePage
from ui.theme import PALETTES, font
from utils.helpers import open_path
from utils.validators import ValidationError, require_text

MONTH_CHOICES = [("Current month", "current"), ("Previous month", "previous")]


class ThemeTile(tk.Canvas):
    """Clickable mini-preview of a theme; the active theme gets an accent border."""

    W, H = 190, 118

    def __init__(self, parent: tk.Misc, ctx: AppContext, name: str, selected: bool) -> None:
        cur = ctx.theme.palette
        super().__init__(parent, width=self.W, height=self.H + 30, bg=cur.card, highlightthickness=0,
                         bd=0, cursor="hand2")
        pal = PALETTES[name]
        border = cur.primary if selected else cur.border
        self.create_polygon(rounded_points(2, 2, self.W - 2, self.H, 14), smooth=True, fill=pal.bg,
                            outline=border, width=2 if selected else 1)
        self.create_rectangle(10, 10, 46, self.H - 8, fill=pal.sidebar, outline="")
        self.create_polygon(rounded_points(54, 12, self.W - 12, 46, 6), smooth=True, fill=pal.card, outline=pal.border)
        self.create_polygon(rounded_points(54, 54, 112, self.H - 12, 6), smooth=True, fill=pal.card, outline=pal.border)
        self.create_polygon(rounded_points(118, 54, self.W - 12, self.H - 12, 6), smooth=True, fill=pal.primary, outline="")
        self.create_rectangle(62, 20, 100, 26, fill=pal.text_muted, outline="")
        self.create_rectangle(62, 32, 90, 38, fill=pal.secondary, outline="")
        label = f"{name.capitalize()} theme" + ("  \u2713" if selected else "")
        self.create_text(self.W / 2, self.H + 16, text=label, fill=cur.primary if selected else cur.text,
                         font=font(10, "bold" if selected else "normal"))
        self.bind("<ButtonRelease-1>", lambda _e: ctx.set_theme(name))


class SettingsPage(BasePage):
    def __init__(self, parent: tk.Misc, ctx: AppContext) -> None:
        super().__init__(parent, ctx)
        self.scroll = ScrollableFrame(self, self.p)
        self.scroll.pack(fill="both", expand=True)
        content = tk.Frame(self.scroll.inner, bg=self.p.bg)
        content.pack(fill="x", padx=28, pady=(24, 30))
        PageHeader(content, self.p, "Settings", "Personalise ZaBir FinanceFlow.").pack(fill="x")
        self._appearance(self._card(content))
        self._regional(self._card(content))
        self._data(self._card(content))
        self._about(self._card(content))

    def _card(self, parent: tk.Misc) -> tk.Frame:
        card = Card(parent, self.p, padding=22)
        card.pack(fill="x", pady=(16, 0))
        return card.body

    # ---- sections ------------------------------------------------------ #
    def _appearance(self, body: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        card_header(body, p, "Appearance", "Choose how the app looks. Your choice is saved automatically.")
        tiles = tk.Frame(body, bg=p.card)
        tiles.pack(anchor="w")
        for i, name in enumerate(("dark", "light")):
            ThemeTile(tiles, ctx, name, ctx.theme.name == name).pack(side="left", padx=(0 if i == 0 else 18, 0))

    def _field(self, body: tk.Frame, label: str, hint: str = "") -> tk.Frame:
        p = self.p
        row = tk.Frame(body, bg=p.card)
        row.pack(fill="x", pady=8)
        text = tk.Frame(row, bg=p.card)
        text.pack(side="left")
        make_label(text, p, label, size=10, bold=True).pack(anchor="w")
        if hint:
            make_label(text, p, hint, size=8, muted=True, wraplength=420, justify="left").pack(anchor="w")
        holder = tk.Frame(row, bg=p.card)
        holder.pack(side="right")
        return holder

    def _regional(self, body: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        card_header(body, p, "Regional & Display", "Formats used throughout the application.")

        currency_labels = {f"{c.code}  \u2014  {c.symbol}  {c.name}": c.code for c in CURRENCIES.values()}
        holder = self._field(body, "Currency", "Only changes how amounts are displayed. "
                             "No currency conversion is ever performed.")
        box = ttk.Combobox(holder, state="readonly", values=list(currency_labels), width=34, font=font(10))
        box.set(next(k for k, v in currency_labels.items() if v == ctx.currency.code))
        box.pack(ipady=3)
        box.bind("<<ComboboxSelected>>", lambda _e: ctx.update_setting("currency", currency_labels[box.get()]))

        fmt_labels = {f"{example}": fmt for example, fmt in DATE_FORMATS}
        holder = self._field(body, "Date format", "How dates appear in lists and reports.")
        box = ttk.Combobox(holder, state="readonly", values=list(fmt_labels), width=34, font=font(10))
        box.set(next((k for k, v in fmt_labels.items() if v == ctx.date_format), DATE_FORMATS[0][0]))
        box.pack(ipady=3)
        box.bind("<<ComboboxSelected>>", lambda _e: ctx.update_setting("date_format", fmt_labels[box.get()]))

        month_labels = dict(MONTH_CHOICES)
        holder = self._field(body, "Default dashboard month", "Month shown when the dashboard opens.")
        box = ttk.Combobox(holder, state="readonly", values=list(month_labels), width=34, font=font(10))
        current = ctx.db.get_setting("default_dashboard_month", "current")
        box.set(next(k for k, v in month_labels.items() if v == current))
        box.pack(ipady=3)
        box.bind("<<ComboboxSelected>>", lambda _e: ctx.update_setting("default_dashboard_month", month_labels[box.get()]))

        holder = self._field(body, "Display name", "Shown in the greeting and profile area.")
        self.name_entry = tk.Entry(holder, width=26, font=font(10), bg=p.card_alt, fg=p.text, bd=0,
                                   insertbackground=p.text, highlightthickness=1,
                                   highlightbackground=p.border, highlightcolor=p.primary)
        self.name_entry.insert(0, ctx.user_name)
        self.name_entry.pack(side="left", ipady=6, padx=(0, 10))
        RoundedButton(holder, p, "Save", self._save_name, outer=p.card, height=34).pack(side="left")

    def _save_name(self) -> None:
        try:
            name = require_text(self.name_entry.get(), field="Display name", max_length=30)
        except ValidationError as exc:
            messagebox.showwarning("Check your input", str(exc), parent=self)
            return
        self.ctx.update_setting("user_name", name)

    def _data(self, body: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        card_header(body, p, "Data & Backup", "All data is stored locally in a SQLite database.")
        make_label(body, p, f"Database: {DB_PATH}", size=9, muted=True, wraplength=700, justify="left").pack(anchor="w")
        make_label(body, p, f"Backups folder: {BACKUP_DIR}", size=9, muted=True, wraplength=700,
                   justify="left").pack(anchor="w", pady=(2, 12))
        row = tk.Frame(body, bg=p.card)
        row.pack(anchor="w", fill="x")
        RoundedButton(row, p, "Create backup now", self._backup, outer=p.card,
                      icon=ctx.images.icon("download", 16, p.on_primary)).pack(side="left")
        RoundedButton(row, p, "Restore from backup\u2026", self._restore, style="secondary", outer=p.card,
                      icon=ctx.images.icon("refresh", 16, p.text)).pack(side="left", padx=10)
        RoundedButton(row, p, "Open backups folder", lambda: open_path(BACKUP_DIR), style="ghost", outer=p.card,
                      icon=ctx.images.icon("folder", 16, p.text)).pack(side="left")
        holder = self._field(body, "Automatic backup on exit", f"Keeps a snapshot each time you close the app (newest 10 kept).")
        Segmented(holder, p, [("On", "1"), ("Off", "0")], ctx.db.get_setting("auto_backup", "1"),
                  lambda v: ctx.db.set_setting("auto_backup", v)).pack()
        holder = self._field(body, "Optimise database", "Compacts the file and refreshes query statistics. Safe to run any time.")
        self.opt_btn = RoundedButton(holder, p, "Optimise now", self._optimise, style="secondary", outer=p.card)
        self.opt_btn.pack()

    def _backup(self) -> None:
        try:
            path = self.ctx.db.backup()
        except DatabaseError as exc:
            messagebox.showerror("Backup failed", str(exc), parent=self)
            return
        messagebox.showinfo("Backup created", f"Your data was saved to:\n\n{path}", parent=self)

    def _restore(self) -> None:
        ctx = self.ctx
        chosen = filedialog.askopenfilename(parent=self, title="Choose a backup to restore", initialdir=str(BACKUP_DIR),
                                            filetypes=[("FinanceFlow backup", "*.db"), ("All files", "*.*")])
        if not chosen:
            return
        try:
            ctx.db.validate_backup(chosen)
        except DatabaseError as exc:
            messagebox.showerror("Cannot restore", str(exc), parent=self)
            return
        if not messagebox.askyesno(
                "Restore backup", "Restoring replaces ALL current data (transactions, budgets, goals, settings) "
                "with the contents of:\n\n" + chosen + "\n\nA safety backup of your current data is created first. Continue?",
                icon="warning", parent=self):
            return
        try:
            safety = ctx.db.backup(prefix="pre_restore")
            ctx.db.restore_from(chosen)
        except DatabaseError as exc:
            messagebox.showerror("Restore failed", str(exc), parent=self)
            return
        ctx.reload_after_restore()
        ctx.notify_data_changed()
        messagebox.showinfo("Restore complete", f"Your data was restored.\nPrevious data was saved to:\n{safety}")

    def _optimise(self) -> None:
        self.opt_btn.set_enabled(False)

        def done(_result, error):
            self.opt_btn.set_enabled(True)
            if error:
                messagebox.showerror("Optimisation failed", str(error), parent=self)
            else:
                messagebox.showinfo("Done", "The database was optimised.", parent=self)

        run_in_background(self, self.ctx.db.optimize, done)

    def _about(self, body: tk.Frame) -> None:
        p = self.p
        card_header(body, p, "About")
        info = [
            ("Application", APP_NAME), ("Version", APP_VERSION),
            ("Python", platform.python_version()), ("Platform", platform.platform(terse=True)),
            ("Currency", f"{self.ctx.currency.code} ({self.ctx.currency.symbol})"),
        ]
        for label, value in info:
            line = tk.Frame(body, bg=p.card)
            line.pack(fill="x", pady=3)
            make_label(line, p, label, size=10, muted=True).pack(side="left")
            make_label(line, p, value, size=10, bold=True).pack(side="right")
