"""Reports: live preview plus CSV / PDF export (run in the background)."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config import EXPORT_DIR
from core.context import AppContext
from core.report_manager import REPORT_TYPES, Money, ReportData
from database.db_manager import DatabaseError
from ui.components import (Card, EmptyState, PageHeader, RoundedButton, card_header, make_label, run_in_background)
from ui.pages.base import ScrollPage
from ui.theme import font
from utils import export_manager as export
from utils.helpers import current_month, month_label, open_path, recent_months
from utils.validators import ValidationError

MODE_LABELS = {"month": "Month", "year": "Year", "all": "All time"}


class ReportsPage(ScrollPage):
    key = "monthly_summary"
    mode = "month"
    value = current_month()

    def build(self, content: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        PageHeader(content, p, "Reports", "Preview a report, then export it as CSV or PDF.").pack(fill="x")
        self._controls(content)
        self.status_row = tk.Frame(content, bg=p.bg)
        self.status_row.pack(fill="x", pady=(10, 0))
        self._preview(content)

    # ------------------------------------------------------------------ #
    def _period_values(self, mode: str) -> list[tuple[str, str]]:
        if mode == "month":
            return [(month_label(m), m) for m in recent_months(36)]
        if mode == "year":
            this = int(current_month()[:4])
            first = min(self.ctx.finance.earliest_year(), this)
            return [(str(y), str(y)) for y in range(this, first - 1, -1)]
        return [("All goals", "")]

    def _controls(self, content: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        card = Card(content, p, padding=16)
        card.pack(fill="x", pady=(16, 0))
        body = card.body
        row = tk.Frame(body, bg=p.card)
        row.pack(fill="x")
        types = {label: (key, modes) for key, label, modes in REPORT_TYPES}
        self._types = types

        def labeled(text, widget_factory, padx=(0, 14)):
            box = tk.Frame(row, bg=p.card)
            box.pack(side="left", padx=padx)
            make_label(box, p, text, size=8, bold=True, muted=True).pack(anchor="w", pady=(0, 3))
            w = widget_factory(box)
            w.pack(ipady=4)
            return w

        current_label = next(l for k, l, _ in REPORT_TYPES if k == self.key)
        self.type_box = labeled("REPORT", lambda b: ttk.Combobox(b, values=list(types), state="readonly", width=28, font=font(10)))
        self.type_box.set(current_label)
        self.mode_box = labeled("PERIOD", lambda b: ttk.Combobox(b, state="readonly", width=10, font=font(10)))
        self.value_box = labeled("SELECT", lambda b: ttk.Combobox(b, state="readonly", width=20, font=font(10)))
        self._sync_mode_values(initial=True)
        self.type_box.bind("<<ComboboxSelected>>", lambda _e: self._on_type())
        self.mode_box.bind("<<ComboboxSelected>>", lambda _e: self._on_mode())
        self.value_box.bind("<<ComboboxSelected>>", lambda _e: self._on_value())

        self.pdf_btn = RoundedButton(row, p, "Export PDF", lambda: self._export("pdf"), outer=p.card,
                                     icon=ctx.images.icon("reports", 16, p.on_primary))
        self.pdf_btn.pack(side="right", pady=(18, 0))
        self.csv_btn = RoundedButton(row, p, "Export CSV", lambda: self._export("csv"), style="secondary", outer=p.card,
                                     icon=ctx.images.icon("table", 16, p.text))
        self.csv_btn.pack(side="right", padx=10, pady=(18, 0))
        hint = ("Tip: the Monthly financial summary exports as the premium statement PDF with charts, budgets, "
                "recent transactions and goals. Other reports export as formatted tables.")
        make_label(body, p, hint, size=9, muted=True, wraplength=900, justify="left").pack(anchor="w", pady=(10, 0))

    def _sync_mode_values(self, initial: bool = False) -> None:
        key, modes = self._types[self.type_box.get()]
        self.mode = self.mode if self.mode in modes else modes[0]
        self.mode_box.configure(values=[MODE_LABELS[m] for m in modes])
        self.mode_box.set(MODE_LABELS[self.mode])
        self.mode_box.configure(state="readonly" if len(modes) > 1 else "disabled")
        self._period = self._period_values(self.mode)
        self.value_box.configure(values=[l for l, _ in self._period], state="disabled" if self.mode == "all" else "readonly")
        labels = {v: l for l, v in self._period}
        if self.value not in labels:
            self.value = self._period[0][1]
        self.value_box.set(labels[self.value])
        self.key = key

    def _on_type(self) -> None:
        self.key = self._types[self.type_box.get()][0]
        self._sync_mode_values()
        self.refresh()

    def _on_mode(self) -> None:
        self.mode = next(m for m, l in MODE_LABELS.items() if l == self.mode_box.get())
        self.value = self._period_values(self.mode)[0][1]
        self._sync_mode_values()
        self.refresh()

    def _on_value(self) -> None:
        self.value = next(v for l, v in self._period if l == self.value_box.get())
        self.refresh()

    # ------------------------------------------------------------------ #
    def _preview(self, content: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        card = Card(content, p, padding=18)
        card.pack(fill="x", pady=(10, 0))
        try:
            data = ctx.reports.build(self.key, self.mode, self.value)
        except (ValidationError, DatabaseError) as exc:
            EmptyState(card.body, p, ctx.images, icon="bell", title="Could not build the report", message=str(exc)).pack()
            return
        self.data = data
        card_header(card.body, p, data.title, data.subtitle)
        if data.summary:
            grid = tk.Frame(card.body, bg=p.card)
            grid.pack(fill="x", pady=(0, 12))
            for i, (label, value) in enumerate(data.summary):
                cell = tk.Frame(grid, bg=p.card_alt, padx=14, pady=8, highlightthickness=1, highlightbackground=p.border)
                cell.grid(row=i // 4, column=i % 4, sticky="nsew", padx=(0, 10), pady=(0, 10))
                grid.columnconfigure(i % 4, weight=1, uniform="s")
                make_label(cell, p, label, size=8, muted=True, bg=p.card_alt).pack(anchor="w")
                make_label(cell, p, self._text(value), size=11, bold=True, bg=p.card_alt).pack(anchor="w")
        if not data.rows:
            EmptyState(card.body, p, ctx.images, icon="reports", title="No data for this period",
                       message="Try another month, year or report type.").pack(fill="x")
            return
        cols = list(range(len(data.headers)))
        tree = ttk.Treeview(card.body, columns=[f"c{i}" for i in cols], show="headings", style="App.Treeview",
                            height=min(len(data.rows) + (1 if data.total_row else 0), 14))
        for i, head in enumerate(data.headers):
            anchor = "e" if i in data.numeric_cols else "w"
            tree.heading(f"c{i}", text=head, anchor=anchor)
            tree.column(f"c{i}", anchor=anchor, width=120 if i else 180, stretch=True, minwidth=70)
        tree.tag_configure("odd", background=p.mix(p.text, 0.035))
        tree.tag_configure("total", foreground=p.primary)
        for n, row in enumerate(data.rows):
            tree.insert("", "end", tags=("odd",) if n % 2 else (), values=[self._text(c) for c in row])
        if data.total_row:
            tree.insert("", "end", tags=("total",), values=[self._text(c) for c in data.total_row])
        scrollbar = ttk.Scrollbar(card.body, orient="vertical", command=tree.yview, style="App.Vertical.TScrollbar")
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        tree.pack(fill="x", expand=True)

    def _text(self, cell: object) -> str:
        return self.ctx.money(cell.minor) if isinstance(cell, Money) else str(cell)

    # ------------------------------------------------------------------ #
    def _set_status(self, text: str = "", *, busy: bool = False, path=None, error: bool = False) -> None:
        p = self.p
        for child in self.status_row.winfo_children():
            child.destroy()
        if busy:
            bar = ttk.Progressbar(self.status_row, mode="indeterminate", length=160, style="App.Horizontal.TProgressbar")
            bar.pack(side="left")
            bar.start(12)
        if text:
            make_label(self.status_row, p, text, size=10, color=p.danger if error else p.text_muted, bg=p.bg).pack(side="left", padx=10)
        if path:
            RoundedButton(self.status_row, p, "Open file", lambda: open_path(path), style="secondary", outer=p.bg, height=30).pack(side="left")
            RoundedButton(self.status_row, p, "Open folder", lambda: open_path(path.parent), style="ghost", outer=p.bg,
                          height=30).pack(side="left", padx=6)

    def _export(self, kind: str) -> None:
        ctx, key, mode, value = self.ctx, self.key, self.mode, self.value
        if not getattr(self, "data", None):
            return
        label = self.type_box.get().replace(" ", "_").replace("-", "_")
        stamp = value or "all"
        path = filedialog.asksaveasfilename(
            parent=self, title=f"Export {kind.upper()}", defaultextension=f".{kind}",
            filetypes=[("PDF document", "*.pdf")] if kind == "pdf" else [("CSV file", "*.csv")],
            initialdir=str(EXPORT_DIR), initialfile=f"ZaBir_{label}_{stamp}.{kind}")
        if not path:
            return

        def work():
            data = ctx.reports.build(key, mode, value)
            if kind == "csv":
                return export.export_report_csv(data, path, ctx.currency)
            if key == "monthly_summary":
                return export.export_monthly_pdf(ctx.reports.monthly_statement(value), path, ctx.currency)
            return export.export_report_pdf(data, path, ctx.currency)

        def done(result, error):
            self.pdf_btn.set_enabled(True)
            self.csv_btn.set_enabled(True)
            if error:
                self._set_status(f"Export failed: {error}", error=True)
                messagebox.showerror("Export failed", str(error), parent=self)
            else:
                self._set_status(f"Saved {result.name}", path=result)

        self.pdf_btn.set_enabled(False)
        self.csv_btn.set_enabled(False)
        self._set_status(f"Generating {kind.upper()}\u2026", busy=True)
        run_in_background(self, work, done)
