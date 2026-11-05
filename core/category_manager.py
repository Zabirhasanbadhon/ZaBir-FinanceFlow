"""Category CRUD with safe deletion (reassignment of linked transactions)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from database.db_manager import DatabaseManager
from utils.helpers import current_month, month_bounds
from utils.validators import ValidationError, require_text

COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class CategoryInUseError(Exception):
    """Raised when deleting a category that still has transactions."""

    def __init__(self, count: int) -> None:
        super().__init__(f"{count} transaction(s) use this category.")
        self.count = count


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    type: str
    color: str
    icon: str
    is_default: bool
    tx_count: int = 0
    total: int = 0
    month_total: int = 0


class CategoryManager:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    def list(self, tx_type: str | None = None, month: str | None = None) -> list[Category]:
        start, end = month_bounds(month or current_month())
        sql = ("SELECT c.id, c.name, c.type, c.color, c.icon, c.is_default, COUNT(t.id) AS n, "
               "COALESCE(SUM(t.amount_minor), 0) AS total, "
               "COALESCE(SUM(CASE WHEN t.transaction_date >= ? AND t.transaction_date < ? "
               "THEN t.amount_minor END), 0) AS month_total "
               "FROM categories c LEFT JOIN transactions t ON t.category_id = c.id ")
        params: list = [start, end]
        if tx_type:
            sql += "WHERE c.type = ? "
            params.append(tx_type)
        sql += "GROUP BY c.id ORDER BY c.id"
        return [Category(r["id"], r["name"], r["type"], r["color"], r["icon"], bool(r["is_default"]),
                         int(r["n"]), int(r["total"]), int(r["month_total"]))
                for r in self.db.query_all(sql, params)]

    def get(self, category_id: int) -> Category | None:
        for cat in self.list():
            if cat.id == category_id:
                return cat
        return None

    def _clean(self, name: str, color: str, icon: str) -> tuple[str, str, str]:
        name = require_text(name, field="Category name", max_length=30)
        if not COLOR_RE.match(color or ""):
            raise ValidationError("Choose a valid colour.")
        return name, color.upper(), (icon or "tag")

    def _name_taken(self, name: str, tx_type: str, exclude_id: int | None = None) -> bool:
        row = self.db.query_one("SELECT id FROM categories WHERE name = ? AND type = ? AND id <> ?",
                                (name, tx_type, exclude_id or 0))
        return row is not None

    def add(self, name: str, tx_type: str, color: str, icon: str) -> int:
        if tx_type not in ("income", "expense"):
            raise ValidationError("Choose income or expense.")
        name, color, icon = self._clean(name, color, icon)
        if self._name_taken(name, tx_type):
            raise ValidationError(f"An {tx_type} category named \u201c{name}\u201d already exists.")
        return self.db.execute("INSERT INTO categories (name, type, color, icon, is_default) VALUES (?, ?, ?, ?, 0)",
                               (name, tx_type, color, icon))

    def update(self, category_id: int, name: str, color: str, icon: str) -> None:
        cat = self.get(category_id)
        if cat is None:
            raise ValidationError("This category no longer exists.")
        name, color, icon = self._clean(name, color, icon)
        if self._name_taken(name, cat.type, category_id):
            raise ValidationError(f"An {cat.type} category named \u201c{name}\u201d already exists.")
        self.db.execute("UPDATE categories SET name = ?, color = ?, icon = ? WHERE id = ?",
                        (name, color, icon, category_id))

    def usage_count(self, category_id: int) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM transactions WHERE category_id = ?", (category_id,)))

    def delete(self, category_id: int, reassign_to: int | None = None) -> None:
        """Delete a category. If it has transactions, ``reassign_to`` must be given."""
        cat = self.get(category_id)
        if cat is None:
            return
        count = self.usage_count(category_id)
        if count and reassign_to is None:
            raise CategoryInUseError(count)
        with self.db.transaction() as conn:
            if count:
                target = conn.execute("SELECT type FROM categories WHERE id = ?", (reassign_to,)).fetchone()
                if target is None or target["type"] != cat.type or reassign_to == category_id:
                    raise ValidationError(f"Choose a different {cat.type} category to move the transactions to.")
                conn.execute("UPDATE transactions SET category_id = ? WHERE category_id = ?",
                             (reassign_to, category_id))
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
