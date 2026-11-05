"""Monthly budgets: overall limit, category limits, live progress and warnings."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from core.budget_manager import BudgetLine
from core.context import AppContext
from database.db_manager import DatabaseError
from ui.components import (Card, EmptyState, IconButton, PageHeader, ProgressBar, RoundedButton, StatCard,
                           card_header, make_label)
from ui.dialogs import Dialog
from ui.pages.base import ScrollPage
from ui.pages.dashboard import usage_color
from utils.helpers import current_month, minor_to_text, month_label, shift_month
from utils.validators import ValidationError, parse_amount


class BudgetDialog(Dialog):
    """Create or edit a budget for ``month``. ``line`` None creates; line.category_id None == overall."""

    def __init__(self, parent: tk.Misc, ctx: AppContext, month: str, line: BudgetLine | None = None,
                 overall: bool = False) -> None:
        self.month, self.line, self.overall = month, line, overall
        editing = line is not None
        super().__init__(parent, ctx, "Edit budget" if editing else "Set budget",
                         subtitle=f"Spending limit for {month_label(month)}.", width=470,
                         submit_text="Save changes" if editing else "Save budget")

    def build(self, body: tk.Frame) -> None:
        ctx = self.ctx
        self._map: dict[str, int | None] = {}
        if self.overall or (self.line and self.line.category_id is None):
            self._map = {"Overall monthly spending": None}
            self.scope = self.combo_field("Applies to", list(self._map))
            self.scope.configure(state="disabled")
        elif self.line:
            self._map = {self.line.name: self.line.category_id}
            self.scope = self.combo_field("Category", list(self._map))
            self.scope.configure(state="disabled")
        else:
            used = {c.category_id for c in ctx.budgets.overview(self.month).categories}
            self._map = {c.name: c.id for c in ctx.categories.list("expense") if c.id not in used}
            self.scope = self.combo_field("Expense category", list(self._map))
        initial = minor_to_text(self.line.limit) if self.line else ""
        self.amount = self.entry_field(f"Monthly limit ({ctx.currency.code})", initial)

    def submit(self) -> None:
        if not self._map:
            raise ValidationError("Every expense category already has a budget this month.")
        limit = parse_amount(self.amount.get(), field="Budget limit")
        self.ctx.budgets.set_budget(self.month, self._map[self.scope.get()], limit)


class BudgetsPage(ScrollPage):
    month = current_month()

    def build(self, content: tk.Frame) -> None:
        p, ctx, month = self.p, self.ctx, self.month
        head = PageHeader(content, p, "Budgets", f"Plan and track spending for {month_label(month)}.")
        head.pack(fill="x")
        RoundedButton(head.actions, p, "Add category budget", lambda: BudgetDialog(self, ctx, self.month),
                      icon=ctx.images.icon("plus", 16, p.on_primary), outer=p.bg).pack(side="right")
        RoundedButton(head.actions, p, "Copy last month", self._copy, style="secondary", outer=p.bg).pack(side="right", padx=10)
        nav = tk.Frame(head.actions, bg=p.bg)
        nav.pack(side="right", padx=(0, 6))
        IconButton(nav, p, ctx.images, "chevron-left", lambda: self._shift(-1), size=34, outer=p.bg).pack(side="left")
        make_label(nav, p, month_label(month), size=10, bold=True, bg=p.bg, width=15).pack(side="left")
        IconButton(nav, p, ctx.images, "chevron-right", lambda: self._shift(1), size=34, outer=p.bg).pack(side="left")

        try:
            ov = ctx.budgets.overview(month)
            alerts = ctx.budgets.alerts(month)
        except DatabaseError as exc:
            EmptyState(content, p, ctx.images, icon="bell", title="Could not load budgets", message=str(exc), bg=p.bg).pack(pady=40)
            return

        for alert in alerts:
            color = p.danger if alert.level == "danger" else p.warning
            banner = tk.Frame(content, bg=p.mix(color, 0.14, p.bg), highlightthickness=1, highlightbackground=color)
            banner.pack(fill="x", pady=(14, 0))
            make_label(banner, p, f"{'Over budget' if alert.level == 'danger' else 'Warning'}: {alert.title} \u2014 {alert.message}",
                       size=10, color=color, bg=banner["bg"], anchor="w").pack(fill="x", padx=14, pady=8)

        limit, remaining = ov.limit, ov.remaining
        row = self.grid_row((1, 1, 1))
        specs = [
            dict(title="Budgeted", value=ctx.money(limit) if limit is not None else "Not set",
                 subtitle="Overall limit" if ov.overall else ("Sum of category limits" if limit is not None else "Create a budget below"),
                 icon="budgets", accent=p.primary),
            dict(title="Spent this month", value=ctx.money(ov.total_spent), subtitle="All expense transactions",
                 icon="arrow_down", accent=p.danger),
            dict(title="Remaining", value=ctx.money(remaining) if remaining is not None else "\u2014",
                 subtitle="Over budget" if remaining is not None and remaining < 0 else "Left to spend",
                 icon="coin", accent=p.secondary if remaining is None or remaining >= 0 else p.danger,
                 subtitle_color=p.danger if remaining is not None and remaining < 0 else None),
        ]
        for i, spec in enumerate(specs):
            self.place(StatCard(row, p, ctx.images, **spec), i, 3)

        self._overall_card(content, ov.overall)
        self._category_card(content, ov.categories)

    def _shift(self, delta: int) -> None:
        BudgetsPage.month = shift_month(self.month, delta)
        self.refresh()

    def _overall_card(self, content: tk.Frame, line: BudgetLine | None) -> None:
        p, ctx = self.p, self.ctx
        card = Card(content, p)
        card.pack(fill="x", pady=(16, 0))
        card_header(card.body, p, "Overall monthly budget", "Total spending limit across all categories")
        if line is None:
            EmptyState(card.body, p, ctx.images, icon="budgets", title="No overall budget",
                       message="Set a limit for everything you spend this month.").pack(fill="x")
            RoundedButton(card.body, p, "Set overall budget", lambda: BudgetDialog(self, ctx, self.month, overall=True),
                          outer=p.card).pack(pady=(0, 6))
            return
        self._line(card.body, line, big=True)

    def _category_card(self, content: tk.Frame, lines: list[BudgetLine]) -> None:
        p, ctx = self.p, self.ctx
        card = Card(content, p)
        card.pack(fill="x", pady=(16, 0))
        card_header(card.body, p, "Category budgets", "Sorted by how much of each limit is used")
        if not lines:
            EmptyState(card.body, p, ctx.images, icon="categories", title="No category budgets",
                       message="Add limits for categories like Food or Shopping to track them here.").pack(fill="x")
            return
        for line in lines:
            self._line(card.body, line)
            tk.Frame(card.body, bg=p.border, height=1).pack(fill="x")

    def _line(self, body: tk.Frame, line: BudgetLine, big: bool = False) -> None:
        p, ctx = self.p, self.ctx
        block = tk.Frame(body, bg=p.card)
        block.pack(fill="x", pady=8)
        head = tk.Frame(block, bg=p.card)
        head.pack(fill="x")
        dot = tk.Canvas(head, width=12, height=12, bg=p.card, highlightthickness=0)
        dot.create_oval(1, 1, 11, 11, fill=line.color, outline="")
        dot.pack(side="left", padx=(0, 8))
        make_label(head, p, line.name, size=11 if big else 10, bold=True).pack(side="left")
        IconButton(head, p, ctx.images, "trash", lambda: self._delete(line), size=30, icon_size=15, outer=p.card).pack(side="right")
        IconButton(head, p, ctx.images, "edit", lambda: BudgetDialog(self, ctx, self.month, line), size=30, icon_size=15,
                   outer=p.card).pack(side="right")
        color = usage_color(p, line.ratio)
        make_label(head, p, f"{round(line.ratio * 100)}%", size=12 if big else 10, bold=True, color=color).pack(side="right", padx=10)
        ProgressBar(block, p, line.ratio, color, height=14 if big else 10).pack(fill="x", pady=(6, 4))
        info = tk.Frame(block, bg=p.card)
        info.pack(fill="x")
        make_label(info, p, f"{ctx.money(line.spent)} spent of {ctx.money(line.limit)}", size=9, muted=True).pack(side="left")
        if line.over:
            make_label(info, p, f"Over by {ctx.money(line.spent - line.limit)}", size=9, bold=True, color=p.danger).pack(side="right")
        else:
            make_label(info, p, f"{ctx.money(line.remaining)} remaining", size=9, color=p.secondary).pack(side="right")

    def _copy(self) -> None:
        try:
            copied = self.ctx.budgets.copy_from_previous(self.month)
        except DatabaseError as exc:
            messagebox.showerror("Could not copy", str(exc), parent=self)
            return
        if copied == 0:
            messagebox.showinfo("Nothing to copy", "Last month has no budgets that are missing from this month.", parent=self)
        else:
            self.ctx.notify_data_changed()

    def _delete(self, line: BudgetLine) -> None:
        if not messagebox.askyesno("Delete budget", f"Delete the budget for {line.name} ({month_label(self.month)})?",
                                   icon="warning", parent=self):
            return
        try:
            self.ctx.budgets.delete_budget(self.month, line.category_id)
        except DatabaseError as exc:
            messagebox.showerror("Could not delete", str(exc), parent=self)
            return
        self.ctx.notify_data_changed()
