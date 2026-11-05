"""Read-side financial queries used by the dashboard (CRUD arrives in Phase 2)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from config import MAX_AMOUNT_MINOR
from database.db_manager import DatabaseManager
from utils.helpers import current_month, days_in_month, month_bounds, shift_month
from utils.validators import ValidationError, parse_date


@dataclass(frozen=True)
class MonthPoint:
    month: str
    income: int
    expense: int


@dataclass(frozen=True)
class CategoryAmount:
    category_id: int
    name: str
    color: str
    amount: int


@dataclass(frozen=True)
class RecentTransaction:
    id: int
    type: str
    amount: int
    description: str
    date: str
    payment_method: str
    category: str
    color: str


@dataclass(frozen=True)
class MonthSummary:
    month: str
    income: int
    expense: int
    savings: int
    savings_rate: float  # 0-100, 0 when there is no income
    transaction_count: int
    avg_daily_spend: int
    top_category: str | None


@dataclass(frozen=True)
class Transaction:
    id: int
    type: str
    amount: int
    category_id: int
    category: str
    color: str
    description: str
    payment_method: str
    date: str
    created_at: str


@dataclass
class TransactionFilter:
    """Search/filter/sort criteria. ``start``/``end`` are inclusive ISO dates."""

    search: str = ""
    tx_type: str | None = None
    category_id: int | None = None
    start: str | None = None
    end: str | None = None
    min_minor: int | None = None
    max_minor: int | None = None
    sort_by: str = "date"  # "date" | "amount"
    descending: bool = True

    def is_active(self) -> bool:
        return any([self.search.strip(), self.tx_type, self.category_id, self.start, self.end,
                    self.min_minor is not None, self.max_minor is not None])


@dataclass(frozen=True)
class Insights:
    top_category: str | None
    top_category_amount: int
    avg_monthly_expense: int
    best_month: str | None
    best_month_savings: int
    biggest_expense: int
    biggest_expense_desc: str
    expense_change_pct: float | None  # vs the previous period of equal length


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class FinanceManager:
    """Aggregations over the ``transactions`` table (amounts in minor units)."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def totals(self) -> tuple[int, int]:
        """All-time (income, expense)."""
        row = self.db.query_one(
            "SELECT COALESCE(SUM(CASE WHEN type='income'  THEN amount_minor END), 0) AS inc, "
            "       COALESCE(SUM(CASE WHEN type='expense' THEN amount_minor END), 0) AS exp "
            "FROM transactions"
        )
        return int(row["inc"]), int(row["exp"])

    def month_totals(self, month: str) -> tuple[int, int]:
        start, end = month_bounds(month)
        row = self.db.query_one(
            "SELECT COALESCE(SUM(CASE WHEN type='income'  THEN amount_minor END), 0) AS inc, "
            "       COALESCE(SUM(CASE WHEN type='expense' THEN amount_minor END), 0) AS exp "
            "FROM transactions WHERE transaction_date >= ? AND transaction_date < ?",
            (start, end),
        )
        return int(row["inc"]), int(row["exp"])

    def has_transactions(self) -> bool:
        return bool(self.db.scalar("SELECT COUNT(*) FROM transactions"))

    def monthly_series(self, end_month: str, count: int = 6) -> list[MonthPoint]:
        """Income/expense per month for ``count`` months ending at ``end_month``."""
        months = [shift_month(end_month, -i) for i in range(count - 1, -1, -1)]
        start = f"{months[0]}-01"
        end = month_bounds(months[-1])[1]
        rows = self.db.query_all(
            "SELECT substr(transaction_date, 1, 7) AS m, type, SUM(amount_minor) AS total "
            "FROM transactions WHERE transaction_date >= ? AND transaction_date < ? "
            "GROUP BY m, type",
            (start, end),
        )
        lookup = {(r["m"], r["type"]): int(r["total"]) for r in rows}
        return [
            MonthPoint(m, lookup.get((m, "income"), 0), lookup.get((m, "expense"), 0))
            for m in months
        ]

    def category_breakdown(self, month: str, tx_type: str = "expense") -> list[CategoryAmount]:
        start, end = month_bounds(month)
        rows = self.db.query_all(
            "SELECT c.id, c.name, c.color, SUM(t.amount_minor) AS total "
            "FROM transactions t JOIN categories c ON c.id = t.category_id "
            "WHERE t.type = ? AND t.transaction_date >= ? AND t.transaction_date < ? "
            "GROUP BY c.id ORDER BY total DESC",
            (tx_type, start, end),
        )
        return [CategoryAmount(r["id"], r["name"], r["color"], int(r["total"])) for r in rows]

    def daily_totals(self, month: str, tx_type: str = "expense") -> dict[int, int]:
        """Mapping day-of-month -> total for the given transaction type."""
        start, end = month_bounds(month)
        rows = self.db.query_all(
            "SELECT CAST(substr(transaction_date, 9, 2) AS INTEGER) AS d, "
            "       SUM(amount_minor) AS total "
            "FROM transactions WHERE type = ? AND transaction_date >= ? AND transaction_date < ? "
            "GROUP BY d",
            (tx_type, start, end),
        )
        return {int(r["d"]): int(r["total"]) for r in rows}

    def recent_transactions(self, limit: int = 6) -> list[RecentTransaction]:
        rows = self.db.query_all(
            "SELECT t.id, t.type, t.amount_minor, t.description, t.transaction_date, "
            "       t.payment_method, c.name AS category, c.color "
            "FROM transactions t JOIN categories c ON c.id = t.category_id "
            "ORDER BY t.transaction_date DESC, t.id DESC LIMIT ?",
            (limit,),
        )
        return [
            RecentTransaction(
                r["id"], r["type"], int(r["amount_minor"]), r["description"],
                r["transaction_date"], r["payment_method"], r["category"], r["color"],
            )
            for r in rows
        ]

    def month_summary(self, month: str) -> MonthSummary:
        income, expense = self.month_totals(month)
        start, end = month_bounds(month)
        count = int(
            self.db.scalar(
                "SELECT COUNT(*) FROM transactions WHERE transaction_date >= ? AND transaction_date < ?",
                (start, end),
            )
        )
        elapsed = date.today().day if month == current_month() else days_in_month(month)
        breakdown = self.category_breakdown(month)
        savings = income - expense
        return MonthSummary(
            month=month,
            income=income,
            expense=expense,
            savings=savings,
            savings_rate=(savings / income * 100) if income > 0 else 0.0,
            transaction_count=count,
            avg_daily_spend=expense // max(elapsed, 1),
            top_category=breakdown[0].name if breakdown else None,
        )


    # ------------------------------------------------------------------ #
    # Transactions: query
    # ------------------------------------------------------------------ #
    @staticmethod
    def _where(f: TransactionFilter) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []
        if f.search.strip():
            like = f"%{_escape_like(f.search.strip())}%"
            clauses.append("(t.description LIKE ? ESCAPE '\\' OR c.name LIKE ? ESCAPE '\\')")
            params += [like, like]
        if f.tx_type in ("income", "expense"):
            clauses.append("t.type = ?")
            params.append(f.tx_type)
        if f.category_id:
            clauses.append("t.category_id = ?")
            params.append(f.category_id)
        if f.start:
            clauses.append("t.transaction_date >= ?")
            params.append(f.start)
        if f.end:
            clauses.append("t.transaction_date <= ?")
            params.append(f.end)
        if f.min_minor is not None:
            clauses.append("t.amount_minor >= ?")
            params.append(f.min_minor)
        if f.max_minor is not None:
            clauses.append("t.amount_minor <= ?")
            params.append(f.max_minor)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    _SELECT = ("SELECT t.id, t.type, t.amount_minor, t.category_id, c.name AS category, c.color, "
               "t.description, t.payment_method, t.transaction_date, t.created_at "
               "FROM transactions t JOIN categories c ON c.id = t.category_id")

    @staticmethod
    def _to_tx(r) -> Transaction:
        return Transaction(r["id"], r["type"], int(r["amount_minor"]), r["category_id"], r["category"],
                           r["color"], r["description"], r["payment_method"], r["transaction_date"],
                           r["created_at"])

    def list_transactions(self, f: TransactionFilter, limit: int | None = None,
                          offset: int = 0) -> list[Transaction]:
        where, params = self._where(f)
        direction = "DESC" if f.descending else "ASC"
        column = "t.amount_minor" if f.sort_by == "amount" else "t.transaction_date"
        sql = f"{self._SELECT}{where} ORDER BY {column} {direction}, t.id {direction}"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params = params + [limit, offset]
        return [self._to_tx(r) for r in self.db.query_all(sql, params)]

    def count_transactions(self, f: TransactionFilter) -> tuple[int, int, int]:
        """(row count, income total, expense total) for the filter."""
        where, params = self._where(f)
        row = self.db.query_one(
            "SELECT COUNT(*) AS n, "
            "COALESCE(SUM(CASE WHEN t.type='income'  THEN t.amount_minor END), 0) AS inc, "
            "COALESCE(SUM(CASE WHEN t.type='expense' THEN t.amount_minor END), 0) AS exp "
            f"FROM transactions t JOIN categories c ON c.id = t.category_id{where}", params)
        return int(row["n"]), int(row["inc"]), int(row["exp"])

    def get_transaction(self, tx_id: int) -> Transaction | None:
        row = self.db.query_one(f"{self._SELECT} WHERE t.id = ?", (tx_id,))
        return self._to_tx(row) if row else None

    # ------------------------------------------------------------------ #
    # Transactions: create / update / delete
    # ------------------------------------------------------------------ #
    def _validate(self, tx_type: str, amount_minor: int, category_id: int | None,
                  description: str, payment_method: str, tx_date: str) -> tuple[str, str, str]:
        if tx_type not in ("income", "expense"):
            raise ValidationError("Choose Income or Expense.")
        if not isinstance(amount_minor, int) or amount_minor <= 0:
            raise ValidationError("Amount must be greater than zero.")
        if amount_minor > MAX_AMOUNT_MINOR:
            raise ValidationError("Amount is too large.")
        if not category_id:
            raise ValidationError("Select a category.")
        cat = self.db.query_one("SELECT type FROM categories WHERE id = ?", (category_id,))
        if cat is None:
            raise ValidationError("The selected category no longer exists.")
        if cat["type"] != tx_type:
            raise ValidationError(f"The selected category is not an {tx_type} category.")
        iso = parse_date(tx_date)
        description = (description or "").strip()
        if len(description) > 200:
            raise ValidationError("Description must be at most 200 characters.")
        method = (payment_method or "").strip() or "Cash"
        if len(method) > 40:
            raise ValidationError("Payment method is too long.")
        return description, method, iso

    def add_transaction(self, tx_type: str, amount_minor: int, category_id: int | None,
                        description: str, payment_method: str, tx_date: str) -> int:
        description, method, iso = self._validate(tx_type, amount_minor, category_id, description,
                                                  payment_method, tx_date)
        duplicate = self.db.query_one(
            "SELECT id FROM transactions WHERE type=? AND amount_minor=? AND category_id=? AND "
            "description=? AND payment_method=? AND transaction_date=? "
            "AND created_at >= datetime('now', 'localtime', '-5 seconds')",
            (tx_type, amount_minor, category_id, description, method, iso))
        if duplicate:
            raise ValidationError("This exact transaction was just saved. Wait a moment to add it again.")
        return self.db.execute(
            "INSERT INTO transactions (type, amount_minor, category_id, description, payment_method, "
            "transaction_date) VALUES (?, ?, ?, ?, ?, ?)",
            (tx_type, amount_minor, category_id, description, method, iso))

    def update_transaction(self, tx_id: int, tx_type: str, amount_minor: int, category_id: int | None,
                           description: str, payment_method: str, tx_date: str) -> None:
        description, method, iso = self._validate(tx_type, amount_minor, category_id, description,
                                                  payment_method, tx_date)
        if self.get_transaction(tx_id) is None:
            raise ValidationError("This transaction no longer exists.")
        self.db.execute(
            "UPDATE transactions SET type=?, amount_minor=?, category_id=?, description=?, "
            "payment_method=?, transaction_date=? WHERE id=?",
            (tx_type, amount_minor, category_id, description, method, iso, tx_id))

    def delete_transaction(self, tx_id: int) -> None:
        self.db.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))

    # ------------------------------------------------------------------ #
    # Range aggregations (analytics & reports)
    # ------------------------------------------------------------------ #
    def range_totals(self, start: str, end_exclusive: str) -> tuple[int, int]:
        row = self.db.query_one(
            "SELECT COALESCE(SUM(CASE WHEN type='income'  THEN amount_minor END), 0) AS inc, "
            "       COALESCE(SUM(CASE WHEN type='expense' THEN amount_minor END), 0) AS exp "
            "FROM transactions WHERE transaction_date >= ? AND transaction_date < ?",
            (start, end_exclusive))
        return int(row["inc"]), int(row["exp"])

    def monthly_series_between(self, first_month: str, last_month: str) -> list[MonthPoint]:
        months: list[str] = []
        m = first_month
        while m <= last_month:
            months.append(m)
            m = shift_month(m, 1)
        if not months:
            return []
        rows = self.db.query_all(
            "SELECT substr(transaction_date, 1, 7) AS m, type, SUM(amount_minor) AS total "
            "FROM transactions WHERE transaction_date >= ? AND transaction_date < ? GROUP BY m, type",
            (f"{months[0]}-01", month_bounds(months[-1])[1]))
        lookup = {(r["m"], r["type"]): int(r["total"]) for r in rows}
        return [MonthPoint(m, lookup.get((m, "income"), 0), lookup.get((m, "expense"), 0)) for m in months]

    def category_breakdown_between(self, start: str, end_exclusive: str,
                                   tx_type: str = "expense") -> list[CategoryAmount]:
        rows = self.db.query_all(
            "SELECT c.id, c.name, c.color, SUM(t.amount_minor) AS total, COUNT(t.id) AS n "
            "FROM transactions t JOIN categories c ON c.id = t.category_id "
            "WHERE t.type = ? AND t.transaction_date >= ? AND t.transaction_date < ? "
            "GROUP BY c.id ORDER BY total DESC", (tx_type, start, end_exclusive))
        return [CategoryAmount(r["id"], r["name"], r["color"], int(r["total"])) for r in rows]

    def category_stats_between(self, start: str, end_exclusive: str, tx_type: str) -> list[tuple[str, int, int]]:
        """(category name, transaction count, total) ordered by total."""
        rows = self.db.query_all(
            "SELECT c.name, COUNT(t.id) AS n, SUM(t.amount_minor) AS total "
            "FROM transactions t JOIN categories c ON c.id = t.category_id "
            "WHERE t.type = ? AND t.transaction_date >= ? AND t.transaction_date < ? "
            "GROUP BY c.id ORDER BY total DESC", (tx_type, start, end_exclusive))
        return [(r["name"], int(r["n"]), int(r["total"])) for r in rows]

    def daily_series_between(self, start: str, end_exclusive: str, tx_type: str = "expense") -> dict[str, int]:
        rows = self.db.query_all(
            "SELECT transaction_date AS d, SUM(amount_minor) AS total FROM transactions "
            "WHERE type = ? AND transaction_date >= ? AND transaction_date < ? GROUP BY d",
            (tx_type, start, end_exclusive))
        return {r["d"]: int(r["total"]) for r in rows}

    def balance_before(self, iso_date: str) -> int:
        """Net balance (income - expenses) of everything dated before ``iso_date``."""
        row = self.db.query_one(
            "SELECT COALESCE(SUM(CASE WHEN type='income' THEN amount_minor ELSE -amount_minor END), 0) AS b "
            "FROM transactions WHERE transaction_date < ?", (iso_date,))
        return int(row["b"])

    def earliest_year(self) -> int:
        value = self.db.scalar("SELECT MIN(substr(transaction_date, 1, 4)) FROM transactions", default=None)
        return int(value) if value else date.today().year

    def insights(self, first_month: str, last_month: str) -> Insights:
        start, end = f"{first_month}-01", month_bounds(last_month)[1]
        points = self.monthly_series_between(first_month, last_month)
        cats = self.category_breakdown_between(start, end)
        total_expense = sum(p.expense for p in points)
        best = max(points, key=lambda p: p.income - p.expense, default=None)
        big = self.db.query_one(
            "SELECT amount_minor, description, (SELECT name FROM categories WHERE id = category_id) AS cat "
            "FROM transactions WHERE type='expense' AND transaction_date >= ? AND transaction_date < ? "
            "ORDER BY amount_minor DESC LIMIT 1", (start, end))
        length = len(points)
        prev_first, prev_last = shift_month(first_month, -length), shift_month(first_month, -1)
        prev_expense = sum(p.expense for p in self.monthly_series_between(prev_first, prev_last))
        change = ((total_expense - prev_expense) / prev_expense * 100) if prev_expense > 0 else None
        return Insights(
            top_category=cats[0].name if cats else None,
            top_category_amount=cats[0].amount if cats else 0,
            avg_monthly_expense=total_expense // max(length, 1),
            best_month=best.month if best and (best.income or best.expense) else None,
            best_month_savings=(best.income - best.expense) if best else 0,
            biggest_expense=int(big["amount_minor"]) if big else 0,
            biggest_expense_desc=(big["description"] or big["cat"]) if big else "",
            expense_change_pct=change,
        )
