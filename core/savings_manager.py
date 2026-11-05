"""Savings goals: CRUD, deposits/withdrawals and progress calculations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from config import MAX_AMOUNT_MINOR
from core.budget_manager import Alert
from database.db_manager import DatabaseManager
from utils.helpers import today_iso
from utils.validators import ValidationError, parse_date, require_text


@dataclass(frozen=True)
class GoalProgress:
    id: int
    name: str
    target: int
    saved: int
    target_date: str | None
    icon: str
    start_date: str = ""
    description: str = ""

    @property
    def ratio(self) -> float:
        return min(self.saved / self.target, 1.0) if self.target > 0 else 0.0

    @property
    def percent(self) -> int:
        return int(self.ratio * 100)

    @property
    def remaining(self) -> int:
        return max(self.target - self.saved, 0)

    @property
    def completed(self) -> bool:
        return self.saved >= self.target

    @property
    def days_left(self) -> int | None:
        if not self.target_date:
            return None
        try:
            return (datetime.strptime(self.target_date, "%Y-%m-%d").date() - date.today()).days
        except ValueError:
            return None

    @property
    def monthly_needed(self) -> int | None:
        """Amount to save per month to hit the target date (None when not applicable)."""
        days = self.days_left
        if self.completed or days is None or days <= 0:
            return None
        months = max(days / 30.4, 1.0)
        return int(self.remaining / months)


@dataclass(frozen=True)
class Contribution:
    id: int
    amount: int  # signed: negative == withdrawal
    date: str
    note: str


class SavingsManager:
    DUE_SOON_DAYS = 30
    _COLS = "id, name, target_minor, current_minor, target_date, icon, start_date, description"

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    @staticmethod
    def _to_goal(r) -> GoalProgress:
        return GoalProgress(r["id"], r["name"], int(r["target_minor"]), int(r["current_minor"]),
                            r["target_date"], r["icon"], r["start_date"], r["description"])

    def list_goals(self) -> list[GoalProgress]:
        """Active goals first (closest to completion first), completed last."""
        goals = [self._to_goal(r) for r in self.db.query_all(f"SELECT {self._COLS} FROM savings_goals")]
        goals.sort(key=lambda g: (g.completed, -g.ratio, g.name.lower()))
        return goals

    def get_goal(self, goal_id: int) -> GoalProgress | None:
        r = self.db.query_one(f"SELECT {self._COLS} FROM savings_goals WHERE id = ?", (goal_id,))
        return self._to_goal(r) if r else None

    # ---- validation ---------------------------------------------------- #
    def _clean(self, name, target_minor, start_date, target_date, description):
        name = require_text(name, field="Goal name", max_length=60)
        if not isinstance(target_minor, int) or target_minor <= 0:
            raise ValidationError("Target amount must be greater than zero.")
        if target_minor > MAX_AMOUNT_MINOR:
            raise ValidationError("Target amount is too large.")
        start = parse_date(start_date, field="Start date")
        target = parse_date(target_date, field="Target date") if (target_date or "").strip() else None
        if target and target < start:
            raise ValidationError("Target date cannot be before the start date.")
        description = (description or "").strip()
        if len(description) > 300:
            raise ValidationError("Description must be at most 300 characters.")
        return name, start, target, description

    # ---- CRUD ----------------------------------------------------------- #
    def add_goal(self, name: str, target_minor: int, initial_minor: int, start_date: str,
                 target_date: str | None, description: str, icon: str) -> int:
        name, start, target, description = self._clean(name, target_minor, start_date, target_date, description)
        if initial_minor < 0 or initial_minor > MAX_AMOUNT_MINOR:
            raise ValidationError("Starting amount is invalid.")
        with self.db.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO savings_goals (name, target_minor, current_minor, start_date, target_date, "
                "description, icon) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, target_minor, initial_minor, start, target, description, icon or "savings"))
            if initial_minor:
                conn.execute("INSERT INTO savings_contributions (goal_id, amount_minor, contribution_date, note) "
                             "VALUES (?, ?, ?, 'Starting balance')", (cur.lastrowid, initial_minor, start))
            return cur.lastrowid

    def update_goal(self, goal_id: int, name: str, target_minor: int, start_date: str,
                    target_date: str | None, description: str, icon: str) -> None:
        name, start, target, description = self._clean(name, target_minor, start_date, target_date, description)
        if self.get_goal(goal_id) is None:
            raise ValidationError("This goal no longer exists.")
        self.db.execute("UPDATE savings_goals SET name=?, target_minor=?, start_date=?, target_date=?, "
                        "description=?, icon=? WHERE id=?",
                        (name, target_minor, start, target, description, icon or "savings", goal_id))

    def delete_goal(self, goal_id: int) -> None:
        self.db.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))  # contributions cascade

    def contribute(self, goal_id: int, amount_minor: int, *, withdraw: bool = False,
                   on_date: str | None = None, note: str = "") -> None:
        """Add money to (or withdraw from) a goal atomically."""
        if not isinstance(amount_minor, int) or amount_minor <= 0:
            raise ValidationError("Amount must be greater than zero.")
        iso = parse_date(on_date or today_iso())
        note = (note or "").strip()[:200]
        with self.db.transaction() as conn:
            row = conn.execute("SELECT current_minor FROM savings_goals WHERE id = ?", (goal_id,)).fetchone()
            if row is None:
                raise ValidationError("This goal no longer exists.")
            current = int(row["current_minor"])
            delta = -amount_minor if withdraw else amount_minor
            if current + delta < 0:
                raise ValidationError("You cannot withdraw more than the amount saved in this goal.")
            if current + delta > MAX_AMOUNT_MINOR:
                raise ValidationError("Resulting amount is too large.")
            conn.execute("UPDATE savings_goals SET current_minor = ? WHERE id = ?", (current + delta, goal_id))
            conn.execute("INSERT INTO savings_contributions (goal_id, amount_minor, contribution_date, note) "
                         "VALUES (?, ?, ?, ?)", (goal_id, delta, iso, note))

    def list_contributions(self, goal_id: int) -> list[Contribution]:
        rows = self.db.query_all(
            "SELECT id, amount_minor, contribution_date, note FROM savings_contributions "
            "WHERE goal_id = ? ORDER BY contribution_date DESC, id DESC", (goal_id,))
        return [Contribution(r["id"], int(r["amount_minor"]), r["contribution_date"], r["note"]) for r in rows]

    def totals(self) -> tuple[int, int, int, int]:
        """(total saved, total target, goals count, completed count)."""
        goals = self.list_goals()
        return (sum(g.saved for g in goals), sum(g.target for g in goals), len(goals),
                sum(1 for g in goals if g.completed))

    def alerts(self) -> list[Alert]:
        alerts: list[Alert] = []
        for goal in self.list_goals():
            days = goal.days_left
            if goal.completed or days is None:
                continue
            if days < 0:
                alerts.append(Alert("danger", f"{goal.name} is overdue",
                                    f"Target date passed; {goal.percent}% saved.", "savings"))
            elif days <= self.DUE_SOON_DAYS:
                alerts.append(Alert("warning", f"{goal.name} due soon",
                                    f"{days} day(s) left; {goal.percent}% saved.", "savings"))
        return alerts
