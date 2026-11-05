"""Dashboard: summary cards, charts, recent activity, budgets and goals.

Every number comes from SQLite via the manager classes; the page re-renders
whenever ``ctx.notify_data_changed()`` fires.
"""
from __future__ import annotations

import logging
import tkinter as tk
from datetime import date
from tkinter import font as tkfont
from tkinter import ttk

from PIL import ImageTk

from core.context import AppContext
from database.db_manager import DatabaseError
from ui.charts import ChartView, donut_chart, income_expense_chart, spending_trend_chart
from ui.components import (Card, EmptyState, ProgressBar, ScrollableFrame, StatCard,
                           card_header, make_label)
from ui.pages.base import BasePage
from ui.theme import Palette, blend, font
from utils.helpers import (compact_number, current_month, days_in_month, month_label, month_short,
                           shift_month, truncate)

log = logging.getLogger(__name__)


def usage_color(p: Palette, ratio: float) -> str:
    """Budget utilisation colour: normal < 80%, warning to 100%, danger above."""
    if ratio > 1.0:
        return p.danger
    return p.warning if ratio >= 0.8 else p.primary


class HeroBanner(tk.Canvas):
    """Gradient welcome banner rendered with Pillow and resized with the window."""

    def __init__(self, parent: tk.Misc, ctx: AppContext, title: str, subtitle: str, chips: list[str]) -> None:
        super().__init__(parent, height=136, width=1, bg=ctx.theme.palette.bg, highlightthickness=0, bd=0)
        self.ctx, self.title, self.subtitle, self.chips = ctx, title, subtitle, chips
        self._photo: ImageTk.PhotoImage | None = None
        self._job: str | None = None
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event: tk.Event) -> None:
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(40, lambda: self._render(event.width, event.height))

    def _render(self, w: int, h: int) -> None:
        self._job = None
        if w < 50:
            return
        self._photo = ImageTk.PhotoImage(self.ctx.images.banner_image(w, h, "#4F46E5", "#9333EA"))
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._photo)
        self.create_text(28, 34, text=self.title, anchor="w", fill="#FFFFFF", font=font(17, "bold"))
        self.create_text(28, 64, text=self.subtitle, anchor="w", fill="#E0E7FF", font=font(10))
        fnt = font(9, "bold")
        measure = tkfont.Font(font=fnt).measure
        x = 28
        pill = blend("#5B50EA", "#FFFFFF", 0.22)
        for chip in self.chips:
            width = measure(chip) + 24
            self.create_polygon(self._pill(x, 90, x + width, 114), smooth=True, fill=pill, outline="")
            self.create_text(x + width / 2, 102, text=chip, fill="#FFFFFF", font=fnt)
            x += width + 10

    @staticmethod
    def _pill(x1: float, y1: float, x2: float, y2: float) -> list[float]:
        from ui.components import rounded_points
        return rounded_points(x1, y1, x2, y2, (y2 - y1) / 2)


class DashboardPage(BasePage):
    def __init__(self, parent: tk.Misc, ctx: AppContext) -> None:
        super().__init__(parent, ctx)
        self.month = ctx.default_dashboard_month()
        self.scroll = ScrollableFrame(self, self.p)
        self.scroll.pack(fill="both", expand=True)
        self._build()

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        position = self.scroll.canvas.yview()[0]
        self._build()
        self.after_idle(lambda: self.scroll.canvas.yview_moveto(position))

    def _build(self) -> None:
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        p = self.p
        self.content = tk.Frame(self.scroll.inner, bg=p.bg)
        self.content.pack(fill="x", padx=28, pady=(24, 30))
        try:
            self._load_data()
        except DatabaseError as exc:
            log.exception("Dashboard data failed to load")
            EmptyState(self.content, p, self.ctx.images, icon="bell", title="Could not load your data",
                       message=str(exc), bg=p.bg).pack(pady=60)
            return
        self._header()
        self._banner()
        self._stat_row()
        self._charts_row()
        self._trend_row()
        self._bottom_row()

    def _load_data(self) -> None:
        f, c, month = self.ctx.finance, self.ctx, self.month
        self.income_all, self.expense_all = f.totals()
        self.summary = f.month_summary(month)
        self.series = f.monthly_series(month, 6)
        self.categories = f.category_breakdown(month)
        self.daily = f.daily_totals(month)
        self.prev_daily = f.daily_totals(shift_month(month, -1))
        self.recent = f.recent_transactions(6)
        self.budget = c.budgets.overview(month)
        self.goals = c.savings.list_goals()

    # ------------------------------------------------------------------ #
    def _row(self, weights: tuple[int, ...], top: int = 16) -> tk.Frame:
        row = tk.Frame(self.content, bg=self.p.bg)
        row.pack(fill="x", pady=(top, 0))
        for i, weight in enumerate(weights):
            row.columnconfigure(i, weight=weight, uniform="col")
        row.rowconfigure(0, weight=1)
        return row

    @staticmethod
    def _place(card: tk.Widget, col: int, count: int) -> None:
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0 if col == count - 1 else 8))

    def _header(self) -> None:
        p, ctx = self.p, self.ctx
        row = tk.Frame(self.content, bg=p.bg)
        row.pack(fill="x")
        left = tk.Frame(row, bg=p.bg)
        left.pack(side="left")
        make_label(left, p, "Dashboard", size=20, bold=True, bg=p.bg).pack(anchor="w")
        make_label(left, p, f"Financial overview for {month_label(self.month)}", size=10, muted=True,
                   bg=p.bg).pack(anchor="w", pady=(2, 0))

        months = [shift_month(current_month(), -i) for i in range(12)]
        if self.month not in months:
            months.insert(0, self.month)
        labels = [month_label(m) for m in months]
        box = ttk.Combobox(row, state="readonly", values=labels, width=18, font=font(10))
        box.set(month_label(self.month))
        box.pack(side="right", ipady=3)
        box.bind("<<ComboboxSelected>>", lambda _e: self._on_month(months[labels.index(box.get())]))
        make_label(row, p, "Month", size=9, muted=True, bg=p.bg).pack(side="right", padx=(0, 8))

    def _on_month(self, month: str) -> None:
        self.month = month
        self._build()

    def _banner(self) -> None:
        s, ctx = self.summary, self.ctx
        chips = [f"Net savings {ctx.money(s.savings)}", f"Savings rate {s.savings_rate:.0f}%",
                 f"{s.transaction_count} transactions"]
        greeting = f"Welcome back, {ctx.user_name}"
        sub = f"Here is how your money moved in {month_label(self.month)}."
        HeroBanner(self.content, ctx, greeting, sub, chips).pack(fill="x", pady=(16, 0))

    def _stat_row(self) -> None:
        p, ctx, s = self.p, self.ctx, self.summary
        row = self._row((1, 1, 1, 1, 1))
        balance = self.income_all - self.expense_all
        remaining, limit = self.budget.remaining, self.budget.limit
        cards = [
            dict(title="Total Balance", value=ctx.money(balance), subtitle="Across all transactions",
                 icon="wallet", accent=p.primary),
            dict(title="Total Income", value=ctx.money(self.income_all),
                 subtitle=f"{ctx.money(s.income)} this month", icon="arrow_up", accent=p.secondary),
            dict(title="Total Expenses", value=ctx.money(self.expense_all),
                 subtitle=f"{ctx.money(s.expense)} this month", icon="arrow_down", accent=p.danger),
            dict(title="Monthly Savings", value=ctx.money(s.savings, signed=s.savings > 0),
                 subtitle=f"{s.savings_rate:.0f}% savings rate", icon="coin",
                 accent=p.secondary if s.savings >= 0 else p.danger,
                 subtitle_color=p.secondary if s.savings >= 0 else p.danger),
            dict(title="Remaining Budget",
                 value=ctx.money(remaining) if remaining is not None else "Not set",
                 subtitle=(f"of {ctx.money(limit)} limit" if limit is not None else "No budget this month"),
                 icon="pie", accent=p.warning if remaining is None or remaining >= 0 else p.danger,
                 subtitle_color=p.danger if remaining is not None and remaining < 0 else None),
        ]
        for i, spec in enumerate(cards):
            self._place(StatCard(row, p, ctx.images, **spec), i, len(cards))

    # ------------------------------------------------------------------ #
    def _charts_row(self) -> None:
        p, ctx = self.p, self.ctx
        row = self._row((3, 2))

        card = Card(row, p)
        self._place(card, 0, 2)
        card_header(card.body, p, "Income vs Expenses", "Last 6 months")
        if any(pt.income or pt.expense for pt in self.series):
            labels = [month_short(pt.month) for pt in self.series]
            income = [pt.income / 100 for pt in self.series]
            expense = [pt.expense / 100 for pt in self.series]
            ChartView(card.body, p, lambda fig, pal: income_expense_chart(fig, pal, labels, income, expense),
                      height=250).pack(fill="x")
        else:
            EmptyState(card.body, p, ctx.images, icon="analytics", title="No activity yet",
                       message="Income and expense transactions will appear here.").pack(fill="x", pady=22)

        card = Card(row, p)
        self._place(card, 1, 2)
        card_header(card.body, p, "Expense Breakdown", month_label(self.month))
        if self.categories:
            top, rest = self.categories[:5], self.categories[5:]
            names = [c.name for c in top]
            values = [c.amount / 100 for c in top]
            colors = [c.color for c in top]
            if rest:
                names.append("Others")
                values.append(sum(c.amount for c in rest) / 100)
                colors.append("#64748B")
            center = compact_number(sum(values))
            ChartView(card.body, p, lambda fig, pal: donut_chart(fig, pal, names, values, colors, center),
                      height=250).pack(fill="x")
        else:
            EmptyState(card.body, p, ctx.images, icon="pie", title="No expenses this month",
                       message="Your spending by category will show up here.").pack(fill="x", pady=22)

    def _trend_row(self) -> None:
        p, ctx, s = self.p, self.ctx, self.summary
        row = self._row((3, 2))

        card = Card(row, p)
        self._place(card, 0, 2)
        card_header(card.body, p, "Monthly Spending Trend", "Cumulative spending vs previous month")
        prev_month = shift_month(self.month, -1)
        if self.daily or self.prev_daily:
            total_days = days_in_month(self.month)
            shown = date.today().day if self.month == current_month() else total_days
            current = self._cumulative(self.daily, shown)
            prev = self._cumulative(self.prev_daily, days_in_month(prev_month)) if self.prev_daily else None
            ChartView(card.body, p,
                      lambda fig, pal: spending_trend_chart(fig, pal, total_days, current, prev,
                                                            month_short(self.month), month_short(prev_month)),
                      height=230).pack(fill="x")
        else:
            EmptyState(card.body, p, ctx.images, icon="analytics", title="No spending to chart",
                       message="Daily spending will be plotted once you record expenses.").pack(fill="x", pady=22)

        card = Card(row, p)
        self._place(card, 1, 2)
        card_header(card.body, p, "Current Month Summary", month_label(self.month))
        rows = [
            ("Income", ctx.money(s.income), p.secondary),
            ("Expenses", ctx.money(s.expense), p.danger),
            ("Net savings", ctx.money(s.savings, signed=True), p.secondary if s.savings >= 0 else p.danger),
            ("Savings rate", f"{s.savings_rate:.1f}%", p.text),
            ("Transactions", str(s.transaction_count), p.text),
            ("Avg. daily spend", ctx.money(s.avg_daily_spend), p.text),
            ("Top category", s.top_category or "\u2014", p.text),
        ]
        for i, (label, value, color) in enumerate(rows):
            line = tk.Frame(card.body, bg=p.card)
            line.pack(fill="x", pady=5)
            make_label(line, p, label, size=10, muted=True).pack(side="left")
            make_label(line, p, value, size=10, bold=True, color=color).pack(side="right")
            if i < len(rows) - 1:
                tk.Frame(card.body, bg=p.border, height=1).pack(fill="x")

    @staticmethod
    def _cumulative(daily: dict[int, int], upto: int) -> list[float]:
        total, out = 0, []
        for day in range(1, upto + 1):
            total += daily.get(day, 0)
            out.append(total / 100)
        return out

    # ------------------------------------------------------------------ #
    def _bottom_row(self) -> None:
        p = self.p
        row = self._row((1, 1, 1))
        for i, builder in enumerate((self._recent_card, self._budget_card, self._goals_card)):
            card = Card(row, p)
            self._place(card, i, 3)
            builder(card.body)

    def _recent_card(self, body: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        card_header(body, p, "Recent Transactions", "Latest activity",
                    action=("View all", lambda: ctx.navigate("transactions")))
        if not self.recent:
            EmptyState(body, p, ctx.images, icon="transactions", title="No transactions yet",
                       message="Your latest income and expenses will be listed here.").pack(fill="x")
            return
        for tx in self.recent:
            line = tk.Frame(body, bg=p.card)
            line.pack(fill="x", pady=6)
            line.columnconfigure(1, weight=1)
            dot = tk.Canvas(line, width=34, height=34, bg=p.card, highlightthickness=0, bd=0)
            dot.create_oval(1, 1, 33, 33, fill=p.mix(tx.color, 0.2), outline="")
            dot.create_oval(11, 11, 23, 23, fill=tx.color, outline="")
            dot.grid(row=0, column=0, rowspan=2, padx=(0, 10))
            title = tx.description or tx.category
            make_label(line, p, truncate(title, 24), size=10, bold=True).grid(row=0, column=1, sticky="w")
            make_label(line, p, f"{tx.category} \u00b7 {ctx.date(tx.date)}", size=8, muted=True).grid(
                row=1, column=1, sticky="w")
            sign = tx.amount if tx.type == "income" else -tx.amount
            make_label(line, p, ctx.money(sign, signed=True), size=10, bold=True,
                       color=p.secondary if tx.type == "income" else p.danger).grid(row=0, column=2, rowspan=2, sticky="e")

    def _budget_card(self, body: tk.Frame) -> None:
        p, ctx, ov = self.p, self.ctx, self.budget
        card_header(body, p, "Budget Progress", month_label(self.month),
                    action=("Manage", lambda: ctx.navigate("budgets")))
        if not ov.has_budgets:
            EmptyState(body, p, ctx.images, icon="budgets", title="No budget set",
                       message="Monthly limits and category budgets will be tracked here.").pack(fill="x")
            return
        lines = ([ov.overall] if ov.overall else []) + ov.categories[:4]
        for line in lines:
            block = tk.Frame(body, bg=p.card)
            block.pack(fill="x", pady=7)
            head = tk.Frame(block, bg=p.card)
            head.pack(fill="x")
            make_label(head, p, line.name, size=10, bold=True).pack(side="left")
            pct = round(line.ratio * 100)
            color = usage_color(p, line.ratio)
            make_label(head, p, f"{pct}%", size=10, bold=True, color=color).pack(side="right")
            ProgressBar(block, p, line.ratio, color).pack(fill="x", pady=(5, 3))
            detail = (f"{ctx.money(line.spent)} of {ctx.money(line.limit)}" if not line.over
                      else f"Over by {ctx.money(line.spent - line.limit)}")
            make_label(block, p, detail, size=8, muted=not line.over,
                       color=p.danger if line.over else None).pack(anchor="w")

    def _goals_card(self, body: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        card_header(body, p, "Savings Goals", "Progress toward your targets",
                    action=("View all", lambda: ctx.navigate("savings")))
        if not self.goals:
            EmptyState(body, p, ctx.images, icon="savings", title="No goals yet",
                       message="Create a savings goal to track your progress here.").pack(fill="x")
            return
        for goal in self.goals[:4]:
            block = tk.Frame(body, bg=p.card)
            block.pack(fill="x", pady=7)
            head = tk.Frame(block, bg=p.card)
            head.pack(fill="x")
            make_label(head, p, truncate(goal.name, 22), size=10, bold=True).pack(side="left")
            done = goal.completed
            make_label(head, p, "Completed" if done else f"{goal.percent}%", size=10, bold=True,
                       color=p.secondary).pack(side="right")
            ProgressBar(block, p, goal.ratio, p.secondary).pack(fill="x", pady=(5, 3))
            make_label(block, p, f"{ctx.money(goal.saved)} of {ctx.money(goal.target)}", size=8, muted=True).pack(anchor="w")
