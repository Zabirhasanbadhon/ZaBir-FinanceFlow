"""Budget progress calculations (create/edit/delete arrives in Phase 3)."""
from __future__ import annotations

from dataclasses import dataclass, field

from database.db_manager import DatabaseManager
from config import MAX_AMOUNT_MINOR
from utils.helpers import month_bounds, shift_month
from utils.validators import ValidationError


@dataclass(frozen=True)
class Alert:
    level: str  # "danger" | "warning" | "info"
    title: str
    message: str
    target: str = "budgets"  # page key opened when the notification is clicked


@dataclass(frozen=True)
class BudgetLine:
    name: str
    color: str
    limit: int
    spent: int
    category_id: int | None = None

    @property
    def remaining(self) -> int:
        return self.limit - self.spent

    @property
    def ratio(self) -> float:
        return self.spent / self.limit if self.limit > 0 else 0.0

    @property
    def over(self) -> bool:
        return self.spent > self.limit


@dataclass(frozen=True)
class BudgetOverview:
    month: str
    total_spent: int
    overall: BudgetLine | None
    categories: list[BudgetLine] = field(default_factory=list)

    @property
    def has_budgets(self) -> bool:
        return self.overall is not None or bool(self.categories)

    @property
    def remaining(self) -> int | None:
        """Remaining monthly budget, or None when no budget exists."""
        if self.overall is not None:
            return self.overall.remaining
        if self.categories:
            return sum(line.remaining for line in self.categories)
        return None

    @property
    def limit(self) -> int | None:
        if self.overall is not None:
            return self.overall.limit
        if self.categories:
            return sum(line.limit for line in self.categories)
        return None


class BudgetManager:
    WARNING_RATIO = 0.8

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def overview(self, month: str) -> BudgetOverview:
        start, end = month_bounds(month)
        total_spent = int(
            self.db.scalar(
                "SELECT SUM(amount_minor) FROM transactions "
                "WHERE type='expense' AND transaction_date >= ? AND transaction_date < ?",
                (start, end),
            )
        )
        overall_limit = self.db.scalar(
            "SELECT limit_minor FROM budgets WHERE month = ? AND category_id IS NULL",
            (month,),
            default=None,
        )
        rows = self.db.query_all(
            "SELECT b.category_id, c.name, c.color, b.limit_minor, "
            "  COALESCE((SELECT SUM(t.amount_minor) FROM transactions t "
            "            WHERE t.type = 'expense' AND t.category_id = b.category_id "
            "              AND t.transaction_date >= ? AND t.transaction_date < ?), 0) AS spent "
            "FROM budgets b JOIN categories c ON c.id = b.category_id "
            "WHERE b.month = ? ORDER BY (spent * 1.0 / b.limit_minor) DESC",
            (start, end, month),
        )
        lines = [BudgetLine(r["name"], r["color"], int(r["limit_minor"]), int(r["spent"]), r["category_id"]) for r in rows]
        overall = (
            BudgetLine("Overall budget", "#6366F1", int(overall_limit), total_spent, None)
            if overall_limit is not None
            else None
        )
        return BudgetOverview(month, total_spent, overall, lines)

    def alerts(self, month: str) -> list[Alert]:
        ov = self.overview(month)
        alerts: list[Alert] = []
        lines = ([ov.overall] if ov.overall else []) + ov.categories
        for line in lines:
            pct = round(line.ratio * 100)
            if line.over:
                alerts.append(Alert("danger", f"{line.name} exceeded", f"Spent {pct}% of the monthly limit."))
            elif line.ratio >= self.WARNING_RATIO:
                alerts.append(Alert("warning", f"{line.name} nearly used", f"{pct}% of the monthly limit is used."))
        return alerts

    # ------------------------------------------------------------------ #
    # CRUD (category_id None == overall monthly limit)
    # ------------------------------------------------------------------ #
    def get_limit(self, month: str, category_id: int | None) -> int | None:
        return self.db.scalar("SELECT limit_minor FROM budgets WHERE month = ? AND IFNULL(category_id, 0) = ?",
                              (month, category_id or 0), default=None)

    def set_budget(self, month: str, category_id: int | None, limit_minor: int) -> None:
        """Create or update a budget; one per (month, scope)."""
        if not isinstance(limit_minor, int) or limit_minor <= 0:
            raise ValidationError("Budget limit must be greater than zero.")
        if limit_minor > MAX_AMOUNT_MINOR:
            raise ValidationError("Budget limit is too large.")
        if category_id is not None:
            cat = self.db.query_one("SELECT type FROM categories WHERE id = ?", (category_id,))
            if cat is None or cat["type"] != "expense":
                raise ValidationError("Budgets can only be set for expense categories.")
        with self.db.transaction() as conn:
            row = conn.execute("SELECT id FROM budgets WHERE month = ? AND IFNULL(category_id, 0) = ?",
                               (month, category_id or 0)).fetchone()
            if row:
                conn.execute("UPDATE budgets SET limit_minor = ? WHERE id = ?", (limit_minor, row["id"]))
            else:
                conn.execute("INSERT INTO budgets (month, category_id, limit_minor) VALUES (?, ?, ?)",
                             (month, category_id, limit_minor))

    def delete_budget(self, month: str, category_id: int | None) -> None:
        self.db.execute("DELETE FROM budgets WHERE month = ? AND IFNULL(category_id, 0) = ?",
                        (month, category_id or 0))

    def copy_from_previous(self, month: str) -> int:
        """Copy budgets from the previous month that do not exist yet; returns rows copied."""
        prev = shift_month(month, -1)
        with self.db.transaction() as conn:
            rows = conn.execute("SELECT category_id, limit_minor FROM budgets WHERE month = ?", (prev,)).fetchall()
            copied = 0
            for r in rows:
                exists = conn.execute("SELECT 1 FROM budgets WHERE month = ? AND IFNULL(category_id, 0) = ?",
                                      (month, r["category_id"] or 0)).fetchone()
                if not exists:
                    conn.execute("INSERT INTO budgets (month, category_id, limit_minor) VALUES (?, ?, ?)",
                                 (month, r["category_id"], r["limit_minor"]))
                    copied += 1
        return copied
