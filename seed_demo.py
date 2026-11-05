"""Development helper: fill the database with realistic DEMO records.

The records are inserted into SQLite exactly like real data, so the dashboard
reads them from the database (nothing is hard-coded in the UI).

    python seed_demo.py           # add demo data (only if no transactions exist)
    python seed_demo.py --reset   # delete ALL transactions, budgets and goals, then add demo data
"""
from __future__ import annotations

import random
import sys
from datetime import date, timedelta

from config import ensure_directories
from database.db_manager import DatabaseManager
from utils.helpers import current_month, shift_month

EXPENSE_PLAN = {  # category: (descriptions, min_taka, max_taka, entries_per_month)
    "Food": (["Groceries", "Restaurant dinner", "Lunch", "Street food", "Tea & snacks"], 120, 1800, 16),
    "Transportation": (["Rickshaw", "Uber ride", "Bus fare", "Fuel"], 40, 900, 9),
    "Shopping": (["Clothing", "Gadget accessory", "Household items"], 500, 6500, 3),
    "Entertainment": (["Cinema", "Games", "Outing with friends"], 300, 2500, 3),
    "Healthcare": (["Pharmacy", "Doctor visit"], 200, 3500, 2),
    "Education": (["Online course", "Books"], 500, 4000, 1),
}
FIXED = [("Housing", "House rent", 20000, 5), ("Utilities", "Electricity & internet", 3600, 12),
         ("Subscriptions", "Streaming & cloud", 1200, 15)]
METHODS = ["Cash", "bKash", "Nagad", "Bank Transfer", "Debit/Credit Card"]


def main() -> None:
    ensure_directories()
    db = DatabaseManager()
    db.initialize()
    reset = "--reset" in sys.argv
    if db.scalar("SELECT COUNT(*) FROM transactions") and not reset:
        print("Transactions already exist. Use --reset to replace them with demo data.")
        return
    cats = {r["name"]: r["id"] for r in db.query_all("SELECT id, name FROM categories")}
    rng = random.Random(7)
    today = date.today()
    rows: list[tuple] = []

    def add(kind: str, taka: int, cat: str, desc: str, day: date) -> None:
        if day <= today:
            rows.append((kind, int(taka) * 100, cats[cat], desc, rng.choice(METHODS), day.isoformat()))

    for back in range(6, -1, -1):
        month = shift_month(current_month(), -back)
        start = date.fromisoformat(f"{month}-01")
        span = 28 if back else max(today.day, 1)
        add("income", 85000, "Salary", "Monthly salary", start)
        add("income", rng.randint(6, 22) * 1000, "Freelancing", "Freelance project", start + timedelta(days=rng.randint(4, 24)))
        if rng.random() < 0.4:
            add("income", rng.randint(2, 6) * 1000, "Investments", "Dividend payout", start + timedelta(days=rng.randint(8, 25)))
        for cat, desc, taka, dom in FIXED:
            add("expense", taka + rng.randint(-200, 300) if cat == "Utilities" else taka, cat, desc, start + timedelta(days=dom - 1))
        for cat, (descs, lo, hi, per_month) in EXPENSE_PLAN.items():
            count = per_month if back else max(1, round(per_month * span / 28))
            for _ in range(count):
                add("expense", rng.randint(lo, hi), cat, rng.choice(descs), start + timedelta(days=rng.randint(0, span - 1)))

    with db.transaction() as conn:
        if reset:
            for table in ("transactions", "budgets", "savings_contributions", "savings_goals"):
                conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            "INSERT INTO transactions (type, amount_minor, category_id, description, payment_method, transaction_date) "
            "VALUES (?, ?, ?, ?, ?, ?)", rows)
        month = current_month()
        conn.execute("INSERT OR REPLACE INTO budgets (month, category_id, limit_minor) VALUES (?, NULL, ?)", (month, 60000 * 100))
        for cat, taka in (("Food", 14000), ("Transportation", 5000), ("Shopping", 8000), ("Entertainment", 4000)):
            conn.execute("INSERT OR REPLACE INTO budgets (month, category_id, limit_minor) VALUES (?, ?, ?)",
                         (month, cats[cat], taka * 100))
        goals = [("Emergency Fund", 300000, 125000, 270, "Six months of essentials"),
                 ("New Laptop", 120000, 96000, 90, "Upgrade for freelance work"),
                 ("Cox's Bazar Trip", 50000, 50000, -10, "Family holiday fund"),
                 ("Online Degree", 200000, 38000, 400, "Tuition savings")]
        for name, target, saved, days, desc in goals:
            cur = conn.execute(
                "INSERT INTO savings_goals (name, target_minor, current_minor, start_date, target_date, description, icon) "
                "VALUES (?, ?, ?, ?, ?, ?, 'savings')",
                (name, target * 100, saved * 100, (today - timedelta(days=120)).isoformat(),
                 (today + timedelta(days=days)).isoformat(), desc))
            conn.execute("INSERT INTO savings_contributions (goal_id, amount_minor, contribution_date, note) VALUES (?, ?, ?, 'Initial demo deposit')",
                         (cur.lastrowid, saved * 100, (today - timedelta(days=60)).isoformat()))
    print(f"Inserted {len(rows)} demo transactions, 5 budgets and 4 savings goals.")
    db.close()


if __name__ == "__main__":
    main()
