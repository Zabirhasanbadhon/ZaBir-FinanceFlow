"""UI smoke test using a fake ``tkinter`` (only runs when real Tk is not installed).

It builds every page and dialog against a real temporary database so wrong arguments, typos and logic
errors surface without a display. It cannot check visual layout - run the app for that.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HAS_TK = importlib.util.find_spec("_tkinter") is not None

_PREFIXES = ("create_", "winfo_", "tag_", "pack", "grid", "place", "after", "bind", "unbind", "focus", "grab",
             "item", "add_", "yview", "xview", "wm_", "option_", "update", "tk_", "iconphoto", "selection_",
             "event_", "wait_", "lift", "lower")
_NAMES = {"destroy", "configure", "config", "columnconfigure", "rowconfigure", "protocol", "title", "geometry",
          "minsize", "resizable", "transient", "withdraw", "deiconify", "mainloop", "heading", "column", "delete",
          "insert", "start", "stop", "coords", "move", "scale", "see", "set", "invoke", "post", "unpost", "icursor",
          "select_range", "tkraise", "propagate", "state", "clipboard_clear", "clipboard_append", "image_names"}


def _install_fake_tk() -> None:
    class Misc:
        def __init__(self, master=None, *args, **kw):
            self.master = master if not isinstance(master, str) else None
            self._opts = dict(kw)
            self._val = ""

        def __getattr__(self, name):
            if name.startswith("__") or not (name in _NAMES or name.startswith(_PREFIXES)):
                raise AttributeError(name)
            return lambda *a, **k: None

        def cget(self, key):
            return self._opts.get(key, "1")

        def configure(self, cnf=None, **kw):
            self._opts.update(cnf or {})
            self._opts.update(kw)

        config = configure

        def __getitem__(self, key):
            return self._opts.get(key, "")

        def winfo_children(self):
            return []

        def winfo_exists(self):
            return 1

        def winfo_toplevel(self):
            return self

        def winfo_width(self):
            return 900

        winfo_height = winfo_reqwidth = winfo_reqheight = winfo_rootx = winfo_rooty = winfo_width

        def winfo_screenwidth(self):
            return 1920

        def winfo_screenheight(self):
            return 1080

        def winfo_ismapped(self):
            return True

        def after(self, ms, func=None, *a):
            return "after#1"

        def after_idle(self, func, *a):
            return "idle#1"

        def yview(self, *a):
            return (0.0, 1.0)

        def get(self, *a):
            return self._val

        def selection(self):
            return getattr(self, "_sel", ())

        def get_children(self, *a):
            return list(getattr(self, "_items", []))

        def find_closest(self, *a):
            return (1,)

        def gettags(self, *a):
            return ()

    class Variable:
        def __init__(self, master=None, value="", name=None):
            self._v = value

        def get(self):
            return self._v

        def set(self, v):
            self._v = v

        def trace_add(self, *a):
            pass

    class Combobox(Misc):
        def __init__(self, master=None, textvariable=None, values=(), **kw):
            super().__init__(master, **kw)
            self._var, self._opts["values"] = textvariable, values

        def get(self):
            return self._var.get() if self._var else self._val

        def set(self, v):
            (self._var.set(v) if self._var else setattr(self, "_val", v))

    class Treeview(Misc):
        def insert(self, parent, index, iid=None, values=(), tags=(), **kw):
            self._items = getattr(self, "_items", []) + [iid or str(len(getattr(self, "_items", [])))]

        def delete(self, *items):
            self._items = []

    class Entry(Misc):
        def __init__(self, master=None, textvariable=None, **kw):
            super().__init__(master, **kw)
            self._var = textvariable

        def get(self):
            return self._var.get() if self._var else self._val

        def insert(self, i, text):
            self._val = text

    class Font:
        def __init__(self, **kw):
            pass

        def measure(self, text):
            return 7 * len(text)

    tk = types.ModuleType("tkinter")
    for name in ("Frame", "Canvas", "Label", "Toplevel", "Tk", "Menu", "Scrollbar", "Text", "Misc", "Widget"):
        setattr(tk, name, type(name, (Misc,), {}))
    tk.Entry, tk.StringVar, tk.TclError, tk.Event = Entry, Variable, type("TclError", (Exception,), {}), Misc
    tk.PhotoImage = lambda *a, **k: object()
    ttk = types.ModuleType("tkinter.ttk")
    ttk.Combobox, ttk.Treeview = Combobox, Treeview
    ttk.Scrollbar = ttk.Progressbar = type("W", (Misc,), {})
    ttk.Style = type("Style", (), {"__init__": lambda s, *a: None, "__getattr__": lambda s, n: (lambda *a, **k: None)})
    font = types.ModuleType("tkinter.font")
    font.Font = Font
    dialogs = {"messagebox": ["showinfo", "showerror", "showwarning", "askyesno"],
               "filedialog": ["asksaveasfilename", "askopenfilename"], "colorchooser": ["askcolor"]}
    for mod, fns in dialogs.items():
        m = types.ModuleType(f"tkinter.{mod}")
        for fn in fns:
            setattr(m, fn, lambda *a, **k: False if fn.startswith("ask") else None)
        sys.modules[f"tkinter.{mod}"] = m
        setattr(tk, mod, m)
    tk.ttk, tk.font = ttk, font
    sys.modules.update({"tkinter": tk, "tkinter.ttk": ttk, "tkinter.font": font})
    sys.modules["PIL.ImageTk"] = types.SimpleNamespace(PhotoImage=lambda *a, **k: object())
    import PIL
    PIL.ImageTk = sys.modules["PIL.ImageTk"]
    sys.modules["matplotlib.backends.backend_tkagg"] = MagicMock()


@unittest.skipIf(HAS_TK, "real tkinter available - run the app to test the UI")
class TestUiSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_fake_tk()
        cls.tmp = tempfile.TemporaryDirectory()
        from core.context import AppContext
        cls.ctx = AppContext(Path(cls.tmp.name) / "ui.db")
        ctx, today = cls.ctx, date.today().isoformat()
        cats = {c.name: c.id for c in ctx.categories.list()}
        from utils.helpers import current_month, shift_month
        for back in range(4):
            mo = shift_month(current_month(), -back)
            ctx.finance.add_transaction("income", 8500000, cats["Salary"], "Pay", "Bank Transfer", f"{mo}-01")
            for i, name in enumerate(("Food", "Housing", "Travel", "Shopping")):
                ctx.finance.add_transaction("expense", 100000 + i * 50000 + back, cats[name], f"{name} {back}", "Cash", f"{mo}-{i + 2:02d}")
        ctx.budgets.set_budget(current_month(), None, 900000)
        ctx.budgets.set_budget(current_month(), cats["Food"], 90000)
        ctx.savings.add_goal("Trip", 5000000, 1000000, today, f"{date.today().year + 1}-01-01", "Fun", "plane")
        cls.parent = sys.modules["tkinter"].Frame(None)

    @classmethod
    def tearDownClass(cls):
        cls.ctx.db.close()
        cls.tmp.cleanup()

    def test_all_pages_build_and_refresh(self):
        from ui.main_window import PAGES
        for key, cls in PAGES.items():
            for theme in ("dark", "light"):
                self.ctx.theme.set(theme)
                page = cls(self.parent, self.ctx)
                page.refresh()
        self.ctx.theme.set("dark")

    def test_reports_every_type(self):
        from ui.pages.reports import ReportsPage
        from core.report_manager import REPORT_TYPES
        page = ReportsPage(self.parent, self.ctx)
        for key, label, modes in REPORT_TYPES:
            page.type_box.set(label)
            page._on_type()
            for mode in modes:
                page.mode_box.set({"month": "Month", "year": "Year", "all": "All time"}[mode])
                page._on_mode()
                self.assertIsNotNone(getattr(page, "data", None))

    def test_analytics_presets(self):
        from ui.pages.analytics import PRESETS, AnalyticsPage
        for preset in PRESETS:
            AnalyticsPage.preset = preset
            AnalyticsPage(self.parent, self.ctx)
        AnalyticsPage.preset = "Last 6 months"

    def test_transaction_dialog_roundtrip(self):
        from ui.pages.transactions import TransactionDialog
        ctx = self.ctx
        dlg = TransactionDialog(self.parent, ctx)
        dlg.amount.set("1,234.50")
        dlg.desc.set("Smoke test")
        dlg.category_box.set("Food")
        dlg._submit()
        self.assertEqual(dlg.error.cget("text"), "")
        from core.finance_manager import TransactionFilter
        tx = ctx.finance.list_transactions(TransactionFilter(search="Smoke test"))[0]
        self.assertEqual(tx.amount, 123450)
        edit = TransactionDialog(self.parent, ctx, tx)
        edit.amount.set("0")
        edit._submit()
        self.assertIn("greater than zero", edit.error.cget("text"))  # validation shown inline, nothing saved
        edit.amount.set("99")
        edit._submit()
        self.assertEqual(ctx.finance.get_transaction(tx.id).amount, 9900)

    def test_other_dialogs(self):
        from ui.pages.budgets import BudgetDialog
        from ui.pages.categories import CategoryDialog, ReassignDialog
        from ui.pages.savings import ContributionDialog, GoalDialog, HistoryDialog
        ctx = self.ctx
        d = CategoryDialog(self.parent, ctx)
        d.name.set("Pets")
        d._submit()
        self.assertTrue(any(c.name == "Pets" for c in ctx.categories.list()))
        food = next(c for c in ctx.categories.list("expense") if c.name == "Food")
        ReassignDialog(self.parent, ctx, food, 3)
        CategoryDialog(self.parent, ctx, food)
        from utils.helpers import current_month
        b = BudgetDialog(self.parent, ctx, current_month())
        b.scope.set("Travel")
        b.amount.set("5000")
        b._submit()
        self.assertEqual(ctx.budgets.get_limit(current_month(), next(c.id for c in ctx.categories.list("expense") if c.name == "Travel")), 500000)
        BudgetDialog(self.parent, ctx, current_month(), overall=True)
        g = GoalDialog(self.parent, ctx)
        g.name.set("Bike")
        g.target.set("20000")
        g.initial.set("500")
        g.end.set("")
        g._submit()
        goal = next(x for x in ctx.savings.list_goals() if x.name == "Bike")
        self.assertEqual(goal.saved, 50000)
        c = ContributionDialog(self.parent, ctx, goal, withdraw=True)
        c.amount.set("1000000")
        c._submit()
        self.assertIn("cannot withdraw", c.error.cget("text"))
        HistoryDialog(self.parent, ctx, goal)
        GoalDialog(self.parent, ctx, goal)

    def test_main_window_navigation_and_events(self):
        from ui.main_window import PAGES, MainWindow
        win = MainWindow(self.ctx)
        for key in PAGES:
            win.navigate(key)
        self.ctx.notify_data_changed()
        self.ctx.set_theme("light")
        win._build()
        self.ctx.set_theme("dark")
        win._build()
        win._on_search("food")


if __name__ == "__main__":
    unittest.main()
