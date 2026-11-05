"""Builds report datasets (pure data, no file or UI code)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from core.budget_manager import BudgetManager, BudgetOverview
from core.category_manager import CategoryManager
from core.finance_manager import (CategoryAmount, FinanceManager, MonthPoint, Transaction,
                                  TransactionFilter)
from core.savings_manager import GoalProgress, SavingsManager
from database.db_manager import DatabaseManager
from utils.helpers import (last_day, month_bounds, month_label, shift_month, year_bounds)
from utils.validators import ValidationError


@dataclass(frozen=True)
class Money:
    """A monetary report cell (integer minor units); formatted by the consumer."""

    minor: int


@dataclass
class ReportData:
    key: str
    title: str
    subtitle: str
    summary: list[tuple[str, object]]
    headers: list[str]
    rows: list[list[object]]
    numeric_cols: set[int] = field(default_factory=set)
    total_row: list[object] | None = None


@dataclass
class MonthlyStatement:
    month: str
    income: int
    expense: int
    net: int
    savings_rate: float
    opening_balance: int
    closing_balance: int
    transaction_count: int
    series: list[MonthPoint]
    expense_categories: list[CategoryAmount]
    category_counts: dict[int, int]
    budget: BudgetOverview
    recent: list[Transaction]
    goals: list[GoalProgress]


# key, label, allowed period modes
REPORT_TYPES: list[tuple[str, str, list[str]]] = [
    ("monthly_summary", "Monthly financial summary", ["month"]),
    ("yearly_summary", "Yearly financial summary", ["year"]),
    ("income_report", "Income report", ["month", "year"]),
    ("expense_report", "Expense report", ["month", "year"]),
    ("category_spending", "Category-wise spending", ["month", "year"]),
    ("budget_performance", "Budget performance", ["month", "year"]),
    ("savings_progress", "Savings progress", ["all"]),
]


class ReportManager:
    def __init__(self, db: DatabaseManager, finance: FinanceManager, budgets: BudgetManager,
                 savings: SavingsManager, categories: CategoryManager) -> None:
        self.db, self.finance, self.budgets = db, finance, budgets
        self.savings, self.categories = savings, categories

    # ------------------------------------------------------------------ #
    @staticmethod
    def _period(mode: str, value: str) -> tuple[str, str, str]:
        """(start inclusive, end exclusive, label)."""
        if mode == "month":
            start, end = month_bounds(value)
            return start, end, month_label(value)
        if mode == "year":
            start, end = year_bounds(int(value))
            return start, end, str(int(value))
        raise ValidationError("Choose a valid reporting period.")

    @staticmethod
    def _pct(part: int, whole: int) -> str:
        return f"{(part / whole * 100):.1f}%" if whole > 0 else "0.0%"

    def build(self, key: str, mode: str, value: str) -> ReportData:
        builders = {
            "monthly_summary": lambda: self._monthly_summary(value),
            "yearly_summary": lambda: self._yearly_summary(value),
            "income_report": lambda: self._transactions_report("income", mode, value),
            "expense_report": lambda: self._transactions_report("expense", mode, value),
            "category_spending": lambda: self._category_spending(mode, value),
            "budget_performance": lambda: self._budget_performance(mode, value),
            "savings_progress": self._savings_progress,
        }
        if key not in builders:
            raise ValidationError("Unknown report type.")
        return builders[key]()

    # ------------------------------------------------------------------ #
    def _monthly_summary(self, month: str) -> ReportData:
        start, end = month_bounds(month)
        inc, exp = self.finance.range_totals(start, end)
        opening = self.finance.balance_before(start)
        count = self.finance.count_transactions(TransactionFilter(start=start, end=last_day(end)))[0]
        rows: list[list[object]] = []
        for kind in ("income", "expense"):
            total = inc if kind == "income" else exp
            for name, n, amount in self.finance.category_stats_between(start, end, kind):
                rows.append([name, kind.capitalize(), n, Money(amount), self._pct(amount, total)])
        summary = [("Total income", Money(inc)), ("Total expenses", Money(exp)), ("Net savings", Money(inc - exp)),
                   ("Savings rate", self._pct(inc - exp, inc) if inc > 0 else "0.0%"),
                   ("Opening balance", Money(opening)), ("Closing balance", Money(opening + inc - exp)),
                   ("Transactions", str(count))]
        return ReportData("monthly_summary", "Monthly Financial Summary", month_label(month), summary,
                          ["Category", "Type", "Transactions", "Amount", "% of type"], rows, {2, 3, 4})

    def _yearly_summary(self, year: str) -> ReportData:
        y = int(year)
        points = self.finance.monthly_series_between(f"{y}-01", f"{y}-12")
        rows = [[month_label(p.month).split()[0], Money(p.income), Money(p.expense),
                 Money(p.income - p.expense), self._pct(p.income - p.expense, p.income) if p.income else "0.0%"]
                for p in points]
        inc, exp = sum(p.income for p in points), sum(p.expense for p in points)
        best = max(points, key=lambda p: p.income - p.expense)
        summary = [("Total income", Money(inc)), ("Total expenses", Money(exp)), ("Net savings", Money(inc - exp)),
                   ("Average monthly expense", Money(exp // 12)),
                   ("Best savings month", month_label(best.month).split()[0] if (best.income or best.expense) else "\u2014")]
        total = ["Total", Money(inc), Money(exp), Money(inc - exp), self._pct(inc - exp, inc) if inc else "0.0%"]
        return ReportData("yearly_summary", "Yearly Financial Summary", str(y), summary,
                          ["Month", "Income", "Expenses", "Net savings", "Savings rate"], rows, {1, 2, 3, 4}, total)

    def _transactions_report(self, kind: str, mode: str, value: str) -> ReportData:
        start, end, label = self._period(mode, value)
        flt = TransactionFilter(tx_type=kind, start=start, end=last_day(end), sort_by="date", descending=False)
        txs = self.finance.list_transactions(flt)
        total = sum(t.amount for t in txs)
        rows = [[t.date, t.category, t.description or "\u2014", t.payment_method, Money(t.amount)] for t in txs]
        biggest = max(txs, key=lambda t: t.amount, default=None)
        word = "Income" if kind == "income" else "Expense"
        summary = [(f"Total {kind}", Money(total)), ("Transactions", str(len(txs))),
                   ("Average per transaction", Money(total // len(txs) if txs else 0)),
                   ("Largest", Money(biggest.amount) if biggest else "\u2014")]
        return ReportData(f"{kind}_report", f"{word} Report", label, summary,
                          ["Date", "Category", "Description", "Payment method", "Amount"], rows, {4},
                          ["Total", "", "", "", Money(total)] if txs else None)

    def _category_spending(self, mode: str, value: str) -> ReportData:
        start, end, label = self._period(mode, value)
        stats = self.finance.category_stats_between(start, end, "expense")
        total = sum(a for _, _, a in stats)
        rows = [[name, n, Money(a), self._pct(a, total), Money(a // n if n else 0)] for name, n, a in stats]
        summary = [("Total spending", Money(total)), ("Categories used", str(len(stats))),
                   ("Top category", stats[0][0] if stats else "\u2014")]
        return ReportData("category_spending", "Category-wise Spending", label, summary,
                          ["Category", "Transactions", "Amount", "% of total", "Average"], rows, {1, 2, 3, 4},
                          ["Total", sum(n for _, n, _ in stats), Money(total), "100.0%", ""] if stats else None)

    def _budget_performance(self, mode: str, value: str) -> ReportData:
        start, end, label = self._period(mode, value)
        months = [value] if mode == "month" else [f"{int(value)}-{m:02d}" for m in range(1, 13)]
        rows: list[list[object]] = []
        over = within = 0
        for month in months:
            ov = self.budgets.overview(month)
            for line in ([ov.overall] if ov.overall else []) + ov.categories:
                pct = round(line.ratio * 100)
                status = "Over budget" if line.over else ("Near limit" if line.ratio >= 0.8 else "On track")
                over += line.over
                within += not line.over
                rows.append([month_label(month), line.name, Money(line.limit), Money(line.spent),
                             Money(line.remaining), f"{pct}%", status])
        summary = [("Budgets tracked", str(len(rows))), ("Within budget", str(within)), ("Over budget", str(over))]
        return ReportData("budget_performance", "Budget Performance", label, summary,
                          ["Month", "Budget", "Limit", "Spent", "Remaining", "Used", "Status"], rows, {2, 3, 4, 5})

    def _savings_progress(self) -> ReportData:
        goals = self.savings.list_goals()
        rows = [[g.name, Money(g.target), Money(g.saved), Money(g.remaining), f"{g.percent}%",
                 g.target_date or "\u2014", "Completed" if g.completed else "In progress"] for g in goals]
        saved, target, count, done = self.savings.totals()
        summary = [("Total saved", Money(saved)), ("Total target", Money(target)),
                   ("Goals", str(count)), ("Completed", str(done))]
        return ReportData("savings_progress", "Savings Progress", f"As of {date.today().isoformat()}", summary,
                          ["Goal", "Target", "Saved", "Remaining", "Progress", "Target date", "Status"], rows, {1, 2, 3, 4})

    # ------------------------------------------------------------------ #
    def monthly_statement(self, month: str) -> MonthlyStatement:
        start, end = month_bounds(month)
        inc, exp = self.finance.range_totals(start, end)
        opening = self.finance.balance_before(start)
        flt = TransactionFilter(start=start, end=last_day(end))
        count = self.finance.count_transactions(flt)[0]
        counts = {name: n for name, n, _ in self.finance.category_stats_between(start, end, "expense")}
        cats = self.finance.category_breakdown_between(start, end)
        return MonthlyStatement(
            month=month, income=inc, expense=exp, net=inc - exp,
            savings_rate=((inc - exp) / inc * 100) if inc > 0 else 0.0,
            opening_balance=opening, closing_balance=opening + inc - exp, transaction_count=count,
            series=self.finance.monthly_series(month, 6), expense_categories=cats,
            category_counts={c.category_id: counts.get(c.name, 0) for c in cats},
            budget=self.budgets.overview(month),
            recent=self.finance.list_transactions(flt, limit=15), goals=self.savings.list_goals())
