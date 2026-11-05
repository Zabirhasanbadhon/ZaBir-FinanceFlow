"""Analytics: Matplotlib charts and insights for a selectable period."""
from __future__ import annotations

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from core.context import AppContext
from database.db_manager import DatabaseError
from ui.charts import (ChartView, budget_utilization_chart, daily_bars_chart, donut_chart, hbar_chart,
                       income_expense_chart, savings_trend_chart)
from ui.components import Card, EmptyState, PageHeader, StatCard, card_header, make_label
from ui.pages.base import ScrollPage
from ui.theme import font
from utils.helpers import (compact_number, current_month, month_bounds, month_label, month_short, recent_months,
                           shift_month)

PRESETS = ["This month", "Last 3 months", "Last 6 months", "Last 12 months", "This year", "Custom range"]
COLORS = ["#6366F1", "#22C55E", "#F97316", "#EC4899", "#06B6D4", "#EAB308", "#8B5CF6", "#14B8A6"]


class AnalyticsPage(ScrollPage):
    preset = "Last 6 months"
    custom_from = shift_month(current_month(), -5)
    custom_to = current_month()

    def range(self) -> tuple[str, str]:
        now = current_month()
        return {
            "This month": (now, now),
            "Last 3 months": (shift_month(now, -2), now),
            "Last 6 months": (shift_month(now, -5), now),
            "Last 12 months": (shift_month(now, -11), now),
            "This year": (f"{now[:4]}-01", now),
        }.get(self.preset, (self.custom_from, self.custom_to))

    def build(self, content: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        first, last = self.range()
        head = PageHeader(content, p, "Analytics", f"{month_label(first)} \u2013 {month_label(last)}" if first != last
                          else month_label(first))
        head.pack(fill="x")
        self._controls(head.actions)
        try:
            self._load(first, last)
        except DatabaseError as exc:
            EmptyState(content, p, ctx.images, icon="bell", title="Could not load analytics", message=str(exc), bg=p.bg).pack(pady=40)
            return
        self._insights(content)
        r1 = self.grid_row((1, 1))
        self._income_expense(r1)
        self._distribution(r1)
        r2 = self.grid_row((1, 1))
        self._savings_trend(r2)
        self._category_bars(r2)
        r3 = self.grid_row((1, 1))
        self._daily(r3)
        self._income_sources(r3)
        self._budget_chart(content)

    # ------------------------------------------------------------------ #
    def _controls(self, parent: tk.Frame) -> None:
        p = self.p
        months = recent_months(36)
        labels = [month_label(m) for m in months]
        if self.preset == "Custom range":
            to_box = ttk.Combobox(parent, values=labels, state="readonly", width=15, font=font(10))
            to_box.set(month_label(self.custom_to))
            to_box.pack(side="right", ipady=3)
            make_label(parent, p, "to", size=9, muted=True, bg=p.bg).pack(side="right", padx=6)
            from_box = ttk.Combobox(parent, values=labels, state="readonly", width=15, font=font(10))
            from_box.set(month_label(self.custom_from))
            from_box.pack(side="right", ipady=3)

            def apply(_e=None):
                a, b = months[labels.index(from_box.get())], months[labels.index(to_box.get())]
                AnalyticsPage.custom_from, AnalyticsPage.custom_to = (a, b) if a <= b else (b, a)
                self.refresh()
            from_box.bind("<<ComboboxSelected>>", apply)
            to_box.bind("<<ComboboxSelected>>", apply)
        preset = ttk.Combobox(parent, values=PRESETS, state="readonly", width=16, font=font(10))
        preset.set(self.preset)
        preset.pack(side="right", ipady=3, padx=(0, 10))
        preset.bind("<<ComboboxSelected>>", lambda _e: self._set_preset(preset.get()))

    def _set_preset(self, value: str) -> None:
        AnalyticsPage.preset = value
        self.refresh()

    def _load(self, first: str, last: str) -> None:
        f, c = self.ctx.finance, self.ctx
        self.first, self.last = first, last
        self.start, self.end = month_bounds(first)[0], month_bounds(last)[1]
        self.series = f.monthly_series_between(first, last)
        self.expense_cats = f.category_breakdown_between(self.start, self.end, "expense")
        self.income_cats = f.category_breakdown_between(self.start, self.end, "income")
        self.daily = f.daily_series_between(self.start, self.end, "expense")
        self.ins = f.insights(first, last)
        self.budget = c.budgets.overview(last)

    # ------------------------------------------------------------------ #
    def _insights(self, content: tk.Frame) -> None:
        p, ctx, ins = self.p, self.ctx, self.ins
        row = self.grid_row((1, 1, 1, 1, 1))
        change = ins.expense_change_pct
        if change is None:
            change_text, change_sub, change_color = "\u2014", "No earlier period to compare", None
        else:
            change_text = f"{change:+.1f}%"
            change_sub = "Spending vs previous period"
            change_color = p.secondary if change <= 0 else p.danger
        specs = [
            dict(title="Top spending category", value=ins.top_category or "\u2014",
                 subtitle=ctx.money(ins.top_category_amount) if ins.top_category else "No expenses yet", icon="pie", accent=p.primary),
            dict(title="Avg. monthly expense", value=ctx.money(ins.avg_monthly_expense), subtitle="Across the period",
                 icon="arrow_down", accent=p.danger),
            dict(title="Best savings month", value=month_label(ins.best_month).split()[0] if ins.best_month else "\u2014",
                 subtitle=ctx.money(ins.best_month_savings, signed=True) if ins.best_month else "No activity yet",
                 icon="coin", accent=p.secondary),
            dict(title="Biggest expense", value=ctx.money(ins.biggest_expense) if ins.biggest_expense else "\u2014",
                 subtitle=(ins.biggest_expense_desc[:26] if ins.biggest_expense_desc else "No expenses yet"), icon="wallet",
                 accent=p.warning),
            dict(title="Spending change", value=change_text, subtitle=change_sub, icon="analytics",
                 accent=change_color or p.primary, subtitle_color=change_color),
        ]
        for i, spec in enumerate(specs):
            self.place(StatCard(row, p, ctx.images, **spec), i, 5)

    def _chart_card(self, row: tk.Frame, col: int, title: str, subtitle: str, builder, has_data: bool, *,
                    height: int = 250, empty=("analytics", "No data in this period", "Record transactions to see this chart.")):
        p, ctx = self.p, self.ctx
        card = Card(row, p)
        self.place(card, col, 2)
        card_header(card.body, p, title, subtitle)
        if has_data:
            ChartView(card.body, p, builder, height=height).pack(fill="x")
        else:
            EmptyState(card.body, p, ctx.images, icon=empty[0], title=empty[1], message=empty[2]).pack(fill="x", pady=20)
        return card

    def _labels(self) -> list[str]:
        multi_year = self.first[:4] != self.last[:4]
        return [f"{month_short(pt.month)} {pt.month[2:4]}" if multi_year else month_short(pt.month) for pt in self.series]

    def _income_expense(self, row: tk.Frame) -> None:
        labels, inc, exp = self._labels(), [x.income / 100 for x in self.series], [x.expense / 100 for x in self.series]
        self._chart_card(row, 0, "Income vs Expenses", "Monthly comparison",
                         lambda fig, pal: income_expense_chart(fig, pal, labels, inc, exp, annotate=len(labels) <= 6),
                         any(inc) or any(exp))

    def _distribution(self, row: tk.Frame) -> None:
        cats = self.expense_cats
        top, rest = cats[:6], cats[6:]
        names = [c.name for c in top] + (["Others"] if rest else [])
        vals = [c.amount / 100 for c in top] + ([sum(c.amount for c in rest) / 100] if rest else [])
        cols = [c.color for c in top] + (["#64748B"] if rest else [])
        center = compact_number(sum(vals))
        self._chart_card(row, 1, "Expense Distribution", "Share of spending by category",
                         lambda fig, pal: donut_chart(fig, pal, names, vals, cols, center), bool(cats),
                         empty=("pie", "No expenses in this period", "Spending by category will appear here."))

    def _savings_trend(self, row: tk.Frame) -> None:
        labels, net = self._labels(), [(x.income - x.expense) / 100 for x in self.series]
        self._chart_card(row, 0, "Monthly Savings Trend", "Income minus expenses per month",
                         lambda fig, pal: savings_trend_chart(fig, pal, labels, net), any(net))

    def _category_bars(self, row: tk.Frame) -> None:
        ctx = self.ctx
        cats = self.expense_cats[:8]
        total = sum(c.amount for c in self.expense_cats) or 1
        labels = [c.name for c in cats]
        vals = [c.amount / 100 for c in cats]
        cols = [c.color for c in cats]
        texts = [f"{ctx.money_chart(c.amount)}  ({c.amount / total * 100:.0f}%)" for c in cats]
        self._chart_card(row, 1, "Category-wise Spending", "Top categories with amounts",
                         lambda fig, pal: hbar_chart(fig, pal, labels, vals, cols, texts), bool(cats),
                         empty=("categories", "No expenses in this period", "Top spending categories will appear here."))

    def _daily(self, row: tk.Frame) -> None:
        start, end = date.fromisoformat(self.start), date.fromisoformat(self.end)
        days = (end - start).days
        if days <= 62:
            labels = [(start + timedelta(d)).strftime("%d %b") for d in range(days)]
            vals = [self.daily.get((start + timedelta(d)).isoformat(), 0) / 100 for d in range(days)]
            sub = "Spending per day"
        else:
            weeks = (days + 6) // 7
            vals = [0.0] * weeks
            for iso, amount in self.daily.items():
                vals[(date.fromisoformat(iso) - start).days // 7] += amount / 100
            labels = [(start + timedelta(7 * w)).strftime("%d %b") for w in range(weeks)]
            sub = "Spending per week"
        self._chart_card(row, 0, "Daily Spending Activity", sub,
                         lambda fig, pal: daily_bars_chart(fig, pal, labels, vals), any(vals),
                         empty=("calendar", "No spending in this period", "Daily activity will appear here."))

    def _income_sources(self, row: tk.Frame) -> None:
        ctx = self.ctx
        cats = self.income_cats[:8]
        total = sum(c.amount for c in self.income_cats) or 1
        labels, vals = [c.name for c in cats], [c.amount / 100 for c in cats]
        cols = [c.color for c in cats]
        texts = [f"{ctx.money_chart(c.amount)}  ({c.amount / total * 100:.0f}%)" for c in cats]
        self._chart_card(row, 1, "Income Sources", "Where your money comes from",
                         lambda fig, pal: hbar_chart(fig, pal, labels, vals, cols, texts), bool(cats),
                         empty=("arrow_up", "No income in this period", "Income sources will appear here."))

    def _budget_chart(self, content: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        card = Card(content, p)
        card.pack(fill="x", pady=(16, 0))
        lines = ([self.budget.overall] if self.budget.overall else []) + self.budget.categories
        card_header(card.body, p, "Budget Utilization", f"{month_label(self.last)} \u2013 dashed line marks 100% of the limit")
        if lines:
            labels = [ln.name for ln in lines]
            ratios = [ln.ratio for ln in lines]
            ChartView(card.body, p, lambda fig, pal: budget_utilization_chart(fig, pal, labels, ratios),
                      height=max(160, 46 * len(lines))).pack(fill="x")
        else:
            EmptyState(card.body, p, ctx.images, icon="budgets", title="No budgets for this month",
                       message="Set budgets to see how much of each limit you have used.").pack(fill="x", pady=16)
