"""Headless tests for the data/business layer. Run:  python -m unittest discover -s tests -v"""
from __future__ import annotations

import csv
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import CURRENCIES  # noqa: E402
from core.budget_manager import BudgetManager  # noqa: E402
from core.category_manager import CategoryInUseError, CategoryManager  # noqa: E402
from core.finance_manager import FinanceManager, TransactionFilter  # noqa: E402
from core.report_manager import REPORT_TYPES, Money, ReportManager  # noqa: E402
from core.savings_manager import SavingsManager  # noqa: E402
from database.db_manager import DatabaseError, DatabaseManager  # noqa: E402
from utils import export_manager as export  # noqa: E402
from utils.helpers import (current_month, format_money, month_bounds, shift_month)  # noqa: E402
from utils.validators import ValidationError, parse_amount  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = DatabaseManager(self.dir / "t.db")
        self.db.initialize()
        self.fin = FinanceManager(self.db)
        self.cats = CategoryManager(self.db)
        self.bud = BudgetManager(self.db)
        self.sav = SavingsManager(self.db)
        self.rep = ReportManager(self.db, self.fin, self.bud, self.sav, self.cats)
        self.food = next(c.id for c in self.cats.list("expense") if c.name == "Food")
        self.travel = next(c.id for c in self.cats.list("expense") if c.name == "Travel")
        self.salary = next(c.id for c in self.cats.list("income") if c.name == "Salary")
        self.today = date.today().isoformat()

    def tearDown(self) -> None:
        self.db.close()
        self.tmp.cleanup()

    def add(self, kind, taka, cat, desc="x", day=None):
        return self.fin.add_transaction(kind, int(taka * 100), cat, desc, "Cash", day or self.today)


class TestFoundation(Base):
    def test_defaults_created_once(self):
        self.assertEqual(len(self.cats.list("income")), 6)
        self.assertEqual(len(self.cats.list("expense")), 11)
        self.db.initialize()
        self.assertEqual(len(self.cats.list()), 17)

    def test_amount_validation_and_money(self):
        self.assertEqual(parse_amount("1,250.50"), 125050)
        for bad in ("0", "-1", "abc", "1.234", "", "1e3", "NaN"):
            with self.assertRaises(ValidationError):
                parse_amount(bad)
        self.assertEqual(format_money(123456789, CURRENCIES["BDT"]), "\u09f312,34,567.89")

    def test_constraints(self):
        with self.assertRaises(DatabaseError):
            self.db.execute("INSERT INTO transactions(type,amount_minor,category_id,transaction_date) "
                            "VALUES('income',0,1,'2026-01-01')")
        with self.assertRaises(DatabaseError):
            self.db.execute("INSERT INTO transactions(type,amount_minor,category_id,transaction_date) "
                            "VALUES('income',5,9999,'2026-01-01')")


class TestTransactions(Base):
    def test_crud_and_validation(self):
        tid = self.add("expense", 250.75, self.food, "Lunch")
        tx = self.fin.get_transaction(tid)
        self.assertEqual((tx.amount, tx.category, tx.description), (25075, "Food", "Lunch"))
        self.fin.update_transaction(tid, "expense", 30000, self.travel, "Bus", "bKash", self.today)
        self.assertEqual(self.fin.get_transaction(tid).category, "Travel")
        self.fin.delete_transaction(tid)
        self.assertIsNone(self.fin.get_transaction(tid))
        with self.assertRaises(ValidationError):  # category type mismatch
            self.add("income", 5, self.food)
        with self.assertRaises(ValidationError):
            self.fin.add_transaction("expense", 0, self.food, "", "Cash", self.today)
        with self.assertRaises(ValidationError):
            self.fin.add_transaction("expense", 100, self.food, "", "Cash", "2026-13-45")

    def test_duplicate_guard(self):
        self.add("expense", 10, self.food, "Tea")
        with self.assertRaises(ValidationError):
            self.add("expense", 10, self.food, "Tea")

    def test_filters_sort_paging(self):
        self.add("income", 1000, self.salary, "Pay", "2026-03-01")
        for i in range(1, 8):
            self.add("expense", i * 10, self.food, f"Meal_{i}", f"2026-03-{i + 1:02d}")
        self.add("expense", 99, self.travel, "100% bus", "2026-04-02")
        f = TransactionFilter(search="meal_")
        self.assertEqual(self.fin.count_transactions(f)[0], 7)
        self.assertEqual(self.fin.count_transactions(TransactionFilter(search="100%"))[0], 1)  # LIKE escaped
        self.assertEqual(self.fin.count_transactions(TransactionFilter(search="travel"))[0], 1)  # category match
        self.assertEqual(self.fin.count_transactions(TransactionFilter(tx_type="income"))[0], 1)
        start, end = month_bounds("2026-03")
        n, inc, exp = self.fin.count_transactions(TransactionFilter(start=start, end="2026-03-31"))
        self.assertEqual((n, inc, exp), (8, 100000, 28000))
        rng = TransactionFilter(start="2026-03-03", end="2026-03-05")
        self.assertEqual(self.fin.count_transactions(rng)[0], 3)
        amt = TransactionFilter(min_minor=3000, max_minor=5000, tx_type="expense")
        self.assertEqual([t.amount for t in self.fin.list_transactions(amt)], [5000, 4000, 3000])
        asc = TransactionFilter(sort_by="amount", descending=False, tx_type="expense")
        page = self.fin.list_transactions(asc, limit=3, offset=3)
        self.assertEqual(len(page), 3)
        self.assertEqual(page[0].amount, 4000)


class TestCategories(Base):
    def test_custom_and_duplicates(self):
        cid = self.cats.add("Pets", "expense", "#ff00aa", "heart")
        with self.assertRaises(ValidationError):
            self.cats.add("pets", "expense", "#ff00aa", "heart")
        with self.assertRaises(ValidationError):
            self.cats.add("Bad", "expense", "red", "tag")
        self.cats.update(cid, "Pet care", "#00ff00", "tag")
        self.assertEqual(self.cats.get(cid).name, "Pet care")

    def test_safe_delete_with_reassign(self):
        self.add("expense", 40, self.food, "Pizza")
        with self.assertRaises(CategoryInUseError):
            self.cats.delete(self.food)
        with self.assertRaises(ValidationError):
            self.cats.delete(self.food, reassign_to=self.salary)  # wrong type
        self.cats.delete(self.food, reassign_to=self.travel)
        self.assertIsNone(self.cats.get(self.food))
        self.assertEqual(self.fin.count_transactions(TransactionFilter(category_id=self.travel))[0], 1)
        unused = self.cats.add("Temp", "income", "#123456", "tag")
        self.cats.delete(unused)
        self.assertIsNone(self.cats.get(unused))


class TestBudgetsAndSavings(Base):
    def test_budget_progress(self):
        m = current_month()
        self.add("expense", 300, self.food)
        self.add("expense", 200, self.travel)
        self.bud.set_budget(m, None, 100000)
        self.bud.set_budget(m, self.food, 25000)
        self.bud.set_budget(m, self.food, 20000)  # upsert, not duplicate
        ov = self.bud.overview(m)
        self.assertEqual(len(ov.categories), 1)
        self.assertEqual((ov.overall.spent, ov.remaining), (50000, 50000))
        self.assertTrue(ov.categories[0].over)
        self.assertEqual(self.bud.alerts(m)[0].level, "danger")
        with self.assertRaises(ValidationError):
            self.bud.set_budget(m, self.salary, 100)  # income category
        self.assertEqual(self.bud.copy_from_previous(shift_month(m, 1)), 2)
        self.bud.delete_budget(m, self.food)
        self.assertEqual(len(self.bud.overview(m).categories), 0)

    def test_goals_and_contributions(self):
        gid = self.sav.add_goal("Laptop", 100000, 20000, self.today, None, "", "laptop")
        self.sav.contribute(gid, 30000)
        self.sav.contribute(gid, 10000, withdraw=True)
        g = self.sav.get_goal(gid)
        self.assertEqual((g.saved, g.percent, g.remaining), (40000, 40, 60000))
        with self.assertRaises(ValidationError):
            self.sav.contribute(gid, 99999999, withdraw=True)
        self.assertEqual([c.amount for c in self.sav.list_contributions(gid)], [-10000, 30000, 20000])
        self.sav.contribute(gid, 60000)
        self.assertTrue(self.sav.get_goal(gid).completed)
        with self.assertRaises(ValidationError):
            self.sav.add_goal("X", 100, 0, "2026-05-01", "2026-04-01", "", "savings")
        self.sav.delete_goal(gid)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM savings_contributions"), 0)  # cascade


class TestReportsAndExports(Base):
    def seed(self):
        m = current_month()
        self.add("income", 85000, self.salary, "Salary", f"{m}-01")
        self.add("expense", 1200.5, self.food, "Groceries", f"{m}-02")
        self.add("expense", 800, self.travel, "Bus", f"{m}-03")
        self.add("expense", 500, self.food, "Last month", f"{shift_month(m, -1)}-10")
        self.bud.set_budget(m, None, 500000)
        self.bud.set_budget(m, self.food, 100000)
        self.sav.add_goal("Trip", 50000, 10000, self.today, None, "", "plane")
        return m

    def test_all_report_types_and_csv(self):
        m = self.seed()
        for key, _label, modes in REPORT_TYPES:
            mode = modes[0]
            value = {"month": m, "year": m[:4], "all": ""}[mode]
            data = self.rep.build(key, mode, value)
            self.assertTrue(data.headers)
            out = export.export_report_csv(data, self.dir / f"{key}.csv", CURRENCIES["BDT"])
            with open(out, encoding="utf-8-sig") as fh:
                rows = list(csv.reader(fh))
            self.assertEqual(len(rows[0]), len(data.headers))
        monthly = self.rep.build("monthly_summary", "month", m)
        self.assertEqual(dict(monthly.summary)["Closing balance"], Money(8500000 - 120050 - 80000 - 50000))
        self.assertEqual(dict(monthly.summary)["Opening balance"], Money(-50000))

    def test_pdfs(self):
        m = self.seed()
        st = self.rep.monthly_statement(m)
        self.assertEqual(st.closing_balance, st.opening_balance + st.net)
        for code in ("BDT", "USD"):
            path = export.export_monthly_pdf(st, self.dir / f"m_{code}.pdf", CURRENCIES[code])
            self.assertTrue(path.read_bytes().startswith(b"%PDF"))
            self.assertGreater(path.stat().st_size, 20000)
        gen = export.export_report_pdf(self.rep.build("expense_report", "year", m[:4]), self.dir / "g.pdf",
                                       CURRENCIES["BDT"])
        self.assertTrue(gen.read_bytes().startswith(b"%PDF"))
        empty = DatabaseManager(self.dir / "e.db")
        empty.initialize()
        efin = FinanceManager(empty)
        erep = ReportManager(empty, efin, BudgetManager(empty), SavingsManager(empty), CategoryManager(empty))
        export.export_monthly_pdf(erep.monthly_statement(m), self.dir / "empty.pdf", CURRENCIES["BDT"])
        empty.close()

    def test_insights(self):
        m = self.seed()
        ins = self.fin.insights(shift_month(m, -1), m)
        self.assertEqual(ins.top_category, "Food")
        self.assertEqual(ins.biggest_expense, 120050)


class TestBackupRestore(Base):
    def test_backup_restore_roundtrip(self):
        self.add("expense", 10, self.food, "Before")
        path = self.db.backup(self.dir / "bk")
        self.add("expense", 20, self.food, "After")
        self.assertEqual(self.fin.count_transactions(TransactionFilter())[0], 2)
        self.db.restore_from(path)
        self.assertEqual(self.fin.count_transactions(TransactionFilter())[0], 1)
        self.add("expense", 5, self.food, "Works after restore")

    def test_rejects_bad_files(self):
        junk = self.dir / "junk.db"
        junk.write_bytes(b"not a database")
        with self.assertRaises(DatabaseError):
            self.db.restore_from(junk)
        other = self.dir / "other.db"
        sqlite3.connect(other).execute("CREATE TABLE x(a)").connection.close()
        with self.assertRaises(DatabaseError):
            self.db.restore_from(other)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM categories"), 17)  # live DB untouched

    def test_prune_and_optimize(self):
        for i in range(4):
            (self.dir / f"auto_backup_{i}.db").write_text("x")
        self.db.prune_backups(keep=2, directory=self.dir)
        self.assertEqual(len(list(self.dir.glob("auto_backup_*.db"))), 2)
        self.db.optimize()


if __name__ == "__main__":
    unittest.main()
