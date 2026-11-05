"""Transactions: add/edit/delete, search, filters, sorting, pagination and CSV export."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from config import EXPORT_DIR, PAYMENT_METHODS
from core.context import AppContext
from core.finance_manager import Transaction, TransactionFilter
from database.db_manager import DatabaseError
from ui.components import (Card, EmptyState, IconButton, PageHeader, RoundedButton, ScrollableFrame,
                           make_label, run_in_background, styled_entry)
from ui.components import Segmented
from ui.dialogs import Dialog
from ui.pages.base import BasePage
from ui.theme import font
from utils.export_manager import export_transactions_csv
from utils.helpers import (last_day, minor_to_text, month_bounds, month_label, open_path, recent_months,
                           today_iso)
from utils.validators import ValidationError, parse_amount, parse_date

SORTS = [("Date (newest first)", "date", True), ("Date (oldest first)", "date", False),
         ("Amount (high to low)", "amount", True), ("Amount (low to high)", "amount", False)]
PAGE_SIZES = [15, 25, 50, 100]


class TransactionDialog(Dialog):
    """Add or edit an income/expense transaction."""

    def __init__(self, parent: tk.Misc, ctx: AppContext, tx: Transaction | None = None,
                 default_type: str = "expense") -> None:
        self.tx = tx
        self.kind = tx.type if tx else default_type
        super().__init__(parent, ctx, "Edit transaction" if tx else "Add transaction",
                         subtitle="Update the details below." if tx else "Record money coming in or going out.",
                         width=500, submit_text="Save changes" if tx else "Add transaction")

    def build(self, body: tk.Frame) -> None:
        p, ctx, tx = self.p, self.ctx, self.tx
        seg = Segmented(body, p, [("Expense", "expense"), ("Income", "income")], self.kind, self._on_type)
        seg.pack(anchor="w", pady=(0, 14))
        self.amount = self.entry_field(f"Amount ({ctx.currency.code})", minor_to_text(tx.amount) if tx else "")
        self.category_box = self.combo_field("Category", [], "")
        self.date_var = self.date_field("Date", tx.date if tx else today_iso())
        methods = list(PAYMENT_METHODS)
        if tx and tx.payment_method not in methods:
            methods.append(tx.payment_method)
        self.method = self.combo_field("Payment method", methods, tx.payment_method if tx else "Cash", readonly=False)
        self.desc = self.entry_field("Description (optional)", tx.description if tx else "")
        self._fill_categories(tx.category_id if tx else None)

    def _on_type(self, kind: str) -> None:
        self.kind = kind
        self._fill_categories(None)

    def _fill_categories(self, select_id: int | None) -> None:
        cats = self.ctx.categories.list(self.kind)
        self._cat_map = {c.name: c.id for c in cats}
        self.category_box.configure(values=list(self._cat_map))
        chosen = next((c.name for c in cats if c.id == select_id), None) or (cats[0].name if cats else "")
        self.category_box.set(chosen)

    def submit(self) -> None:
        amount = parse_amount(self.amount.get())
        category_id = self._cat_map.get(self.category_box.get())
        iso = self.read_date(self.date_var, "Date")
        args = (self.kind, amount, category_id, self.desc.get(), self.method.get(), iso)
        if self.tx:
            self.ctx.finance.update_transaction(self.tx.id, *args)
        else:
            self.ctx.finance.add_transaction(*args)


class TransactionDetailDialog(Dialog):
    def __init__(self, parent: tk.Misc, ctx: AppContext, tx: Transaction, on_edit, on_delete) -> None:
        self.tx, self._on_edit, self._on_delete = tx, on_edit, on_delete
        super().__init__(parent, ctx, "Transaction details", width=460, submit_text=None, notify=False)

    def build(self, body: tk.Frame) -> None:
        p, ctx, tx = self.p, self.ctx, self.tx
        sign = tx.amount if tx.type == "income" else -tx.amount
        make_label(body, p, ctx.money(sign, signed=True), size=24, bold=True,
                   color=p.secondary if tx.type == "income" else p.danger).pack(anchor="w", pady=(0, 10))
        rows = [("Type", tx.type.capitalize()), ("Category", tx.category), ("Date", ctx.date(tx.date)),
                ("Payment method", tx.payment_method), ("Description", tx.description or "\u2014"),
                ("Transaction ID", f"#{tx.id}"), ("Created", tx.created_at)]
        for label, value in rows:
            line = tk.Frame(body, bg=p.card)
            line.pack(fill="x", pady=4)
            make_label(line, p, label, size=10, muted=True).pack(side="left")
            make_label(line, p, value, size=10, bold=True, wraplength=280, justify="right").pack(side="right")
            tk.Frame(body, bg=p.border, height=1).pack(fill="x")

    def buttons(self):
        return [("Edit", lambda: (self.destroy(), self._on_edit(self.tx)), "primary"),
                ("Delete", lambda: (self.destroy(), self._on_delete(self.tx)), "danger"),
                ("Close", self.destroy, "secondary")]


class TransactionsPage(BasePage):
    def __init__(self, parent: tk.Misc, ctx: AppContext) -> None:
        super().__init__(parent, ctx)
        self.page_index, self.page_size = 0, PAGE_SIZES[0]
        self._rows: dict[str, Transaction] = {}
        self._search_job: str | None = None
        self._cat_labels: dict[str, int | None] = {}
        self._month_labels: dict[str, str | None] = {}

        scroll = ScrollableFrame(self, self.p)
        scroll.pack(fill="both", expand=True)
        self.content = tk.Frame(scroll.inner, bg=self.p.bg)
        self.content.pack(fill="x", padx=28, pady=(24, 30))
        self._header()
        self._filters()
        self._stats()
        self._table()
        self._load()

    # ------------------------------------------------------------------ #
    def _header(self) -> None:
        p, ctx = self.p, self.ctx
        head = PageHeader(self.content, p, "Transactions", "Every income and expense, searchable and filterable.")
        head.pack(fill="x")
        RoundedButton(head.actions, p, "Add transaction", self._add, icon=ctx.images.icon("plus", 16, p.on_primary),
                      outer=p.bg).pack(side="right")
        RoundedButton(head.actions, p, "Export CSV", self._export, style="secondary",
                      icon=ctx.images.icon("download", 16, p.text), outer=p.bg).pack(side="right", padx=(0, 10))

    def _filters(self) -> None:
        p, ctx = self.p, self.ctx
        card = Card(self.content, p, padding=16)
        card.pack(fill="x", pady=(16, 0))
        body = card.body
        self.search_var = tk.StringVar(value=ctx.search_query)
        self.type_var = tk.StringVar(value="All types")
        self.cat_var = tk.StringVar(value="All categories")
        self.month_var = tk.StringVar(value="Any month")
        self.from_var, self.to_var = tk.StringVar(), tk.StringVar()
        self.min_var, self.max_var = tk.StringVar(), tk.StringVar()
        self.sort_var = tk.StringVar(value=SORTS[0][0])

        cats = ctx.categories.list()
        names = [c.name for c in cats]
        self._cat_labels = {"All categories": None}
        for c in cats:
            label = c.name if names.count(c.name) == 1 else f"{c.name} ({c.type})"
            self._cat_labels[label] = c.id
        self._month_labels = {"Any month": None}
        for m in recent_months(36):
            self._month_labels[month_label(m)] = m

        row1 = tk.Frame(body, bg=p.card)
        row1.pack(fill="x")
        row2 = tk.Frame(body, bg=p.card)
        row2.pack(fill="x", pady=(10, 0))

        def labeled(parent, text, widget_factory, expand=False, padx=(0, 12)):
            box = tk.Frame(parent, bg=p.card)
            box.pack(side="left", fill="x", expand=expand, padx=padx)
            make_label(box, p, text, size=8, bold=True, muted=True).pack(anchor="w", pady=(0, 3))
            widget = widget_factory(box)
            widget.pack(fill="x", ipady=5)
            return widget

        search = labeled(row1, "SEARCH", lambda b: styled_entry(b, p, self.search_var, width=20), expand=True)
        self.search_var.trace_add("write", lambda *_: self._on_search_typed())
        search.bind("<Return>", lambda _e: self._apply())

        def combo(var, values, width):
            return lambda b: ttk.Combobox(b, textvariable=var, values=values, state="readonly", width=width, font=font(10))

        c1 = labeled(row1, "TYPE", combo(self.type_var, ["All types", "Income", "Expense"], 12))
        c2 = labeled(row1, "CATEGORY", combo(self.cat_var, list(self._cat_labels), 20))
        c3 = labeled(row1, "MONTH", combo(self.month_var, list(self._month_labels), 18), padx=(0, 0))
        for c in (c1, c2, c3):
            c.bind("<<ComboboxSelected>>", lambda _e: self._apply())

        def entry(var, width):
            def make(b):
                e = styled_entry(b, p, var, width=width)
                e.bind("<Return>", lambda _e: self._apply())
                e.bind("<FocusOut>", lambda _e: self._apply())
                return e
            return make

        fmt_hint = ctx.date(today_iso())
        labeled(row2, f"FROM  ({fmt_hint})", entry(self.from_var, 14))
        labeled(row2, "TO", entry(self.to_var, 14))
        labeled(row2, f"MIN AMOUNT", entry(self.min_var, 11))
        labeled(row2, "MAX AMOUNT", entry(self.max_var, 11))
        s = labeled(row2, "SORT BY", combo(self.sort_var, [x[0] for x in SORTS], 20))
        s.bind("<<ComboboxSelected>>", lambda _e: self._apply())
        RoundedButton(row2, p, "Clear filters", self._clear, style="secondary", outer=p.card,
                      icon=ctx.images.icon("x", 14, p.text)).pack(side="right", pady=(18, 0))
        self.filter_error = tk.Label(body, text="", fg=p.danger, bg=p.card, font=font(9), anchor="w")
        self.filter_error.pack(fill="x")

    def _stats(self) -> None:
        p = self.p
        row = tk.Frame(self.content, bg=p.bg)
        row.pack(fill="x", pady=(14, 0))
        self.stat_labels: dict[str, tk.Label] = {}
        for key, title, color in (("count", "Matching transactions", p.text), ("income", "Income", p.secondary),
                                  ("expense", "Expenses", p.danger), ("net", "Net", p.primary)):
            chip = Card(row, p, padding=12, radius=12)
            chip.pack(side="left", fill="x", expand=True, padx=(0, 10))
            make_label(chip.body, p, title, size=8, muted=True).pack(anchor="w")
            lbl = make_label(chip.body, p, "\u2014", size=13, bold=True, color=color)
            lbl.pack(anchor="w")
            self.stat_labels[key] = lbl

    def _table(self) -> None:
        p, ctx = self.p, self.ctx
        self.table_card = Card(self.content, p, padding=0)
        self.table_card.pack(fill="x", pady=(14, 0))
        body = self.table_card.body
        bar = tk.Frame(body, bg=p.card)
        bar.pack(fill="x", padx=16, pady=(14, 8))
        self.range_label = make_label(bar, p, "", size=10, muted=True)
        self.range_label.pack(side="left")
        self.delete_btn = RoundedButton(bar, p, "Delete", self._delete_selected, style="danger", outer=p.card, height=32)
        self.delete_btn.pack(side="right")
        self.edit_btn = RoundedButton(bar, p, "Edit", self._edit_selected, style="secondary", outer=p.card, height=32)
        self.edit_btn.pack(side="right", padx=8)
        self.view_btn = RoundedButton(bar, p, "View", self._view_selected, style="secondary", outer=p.card, height=32)
        self.view_btn.pack(side="right")
        for b in (self.delete_btn, self.edit_btn, self.view_btn):
            b.set_enabled(False)

        self.tree_holder = tk.Frame(body, bg=p.card)
        self.tree_holder.pack(fill="x", padx=8)
        cols = ("date", "description", "category", "method", "type", "amount")
        self.tree = ttk.Treeview(self.tree_holder, columns=cols, show="headings", style="App.Treeview",
                                 selectmode="browse")
        for col, text, width, anchor, stretch in (("date", "Date", 110, "w", False), ("description", "Description", 260, "w", True),
                                                   ("category", "Category", 150, "w", False), ("method", "Method", 130, "w", False),
                                                   ("type", "Type", 90, "w", False), ("amount", "Amount", 140, "e", False)):
            self.tree.heading(col, text=text, anchor=anchor)
            self.tree.column(col, width=width, anchor=anchor, stretch=stretch, minwidth=60)
        self.tree.tag_configure("income", foreground=p.secondary)
        self.tree.tag_configure("expense", foreground=p.danger)
        self.tree.tag_configure("odd", background=p.mix(p.text, 0.035))
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())
        self.tree.bind("<Double-1>", lambda _e: self._view_selected())
        self.tree.bind("<Delete>", lambda _e: self._delete_selected())
        self.tree.bind("<Return>", lambda _e: self._view_selected())
        self.tree.bind("<Button-3>", self._context_menu)
        self.empty_holder = tk.Frame(body, bg=p.card)

        foot = self.foot = tk.Frame(body, bg=p.card)
        foot.pack(fill="x", padx=16, pady=(10, 14))
        make_label(foot, p, "Rows per page", size=9, muted=True).pack(side="left")
        self.size_box = ttk.Combobox(foot, values=[str(n) for n in PAGE_SIZES], width=5, state="readonly", font=font(9))
        self.size_box.set(str(self.page_size))
        self.size_box.pack(side="left", padx=8)
        self.size_box.bind("<<ComboboxSelected>>", lambda _e: self._change_size())
        self.next_btn = IconButton(foot, p, ctx.images, "chevron-right", lambda: self._go(1), size=34, outer=p.card)
        self.next_btn.pack(side="right")
        self.page_label = make_label(foot, p, "", size=9, muted=True)
        self.page_label.pack(side="right", padx=8)
        self.prev_btn = IconButton(foot, p, ctx.images, "chevron-left", lambda: self._go(-1), size=34, outer=p.card)
        self.prev_btn.pack(side="right")

    # ------------------------------------------------------------------ #
    # Filtering / loading
    # ------------------------------------------------------------------ #
    def _build_filter(self) -> TransactionFilter:
        ctx = self.ctx
        kind = {"Income": "income", "Expense": "expense"}.get(self.type_var.get())
        start = end = None
        month = self._month_labels.get(self.month_var.get())
        if month:
            start, exclusive_end = month_bounds(month)
            end = last_day(exclusive_end)
        frm = parse_date(self.from_var.get(), ctx.date_format, field="From date") if self.from_var.get().strip() else None
        to = parse_date(self.to_var.get(), ctx.date_format, field="To date") if self.to_var.get().strip() else None
        if frm:
            start = max(start, frm) if start else frm
        if to:
            end = min(end, to) if end else to
        if start and end and start > end:
            raise ValidationError("The date range is empty: 'From' must be on or before 'To' (and inside the chosen month).")
        mn = parse_amount(self.min_var.get(), field="Minimum amount") if self.min_var.get().strip() else None
        mx = parse_amount(self.max_var.get(), field="Maximum amount") if self.max_var.get().strip() else None
        if mn is not None and mx is not None and mn > mx:
            raise ValidationError("Minimum amount cannot be greater than the maximum amount.")
        _label, sort_by, desc = next(x for x in SORTS if x[0] == self.sort_var.get())
        return TransactionFilter(self.search_var.get(), kind, self._cat_labels.get(self.cat_var.get()), start, end,
                                 mn, mx, sort_by, desc)

    def _on_search_typed(self) -> None:
        self.ctx.search_query = self.search_var.get()
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(300, self._apply)

    def _apply(self) -> None:
        self._search_job = None
        self.page_index = 0
        self._load()

    def _clear(self) -> None:
        for var, value in ((self.search_var, ""), (self.type_var, "All types"), (self.cat_var, "All categories"),
                           (self.month_var, "Any month"), (self.from_var, ""), (self.to_var, ""),
                           (self.min_var, ""), (self.max_var, ""), (self.sort_var, SORTS[0][0])):
            var.set(value)
        self.ctx.search_query = ""
        self._apply()

    def refresh(self) -> None:
        self._load()

    def _load(self) -> None:
        try:
            flt = self._build_filter()
        except ValidationError as exc:
            self.filter_error.configure(text=str(exc))
            return
        self.filter_error.configure(text="")
        try:
            count, income, expense = self.ctx.finance.count_transactions(flt)
            last_page = max((count - 1) // self.page_size, 0)
            self.page_index = min(self.page_index, last_page)
            rows = self.ctx.finance.list_transactions(flt, self.page_size, self.page_index * self.page_size)
        except DatabaseError as exc:
            self.filter_error.configure(text=str(exc))
            return
        self._flt = flt
        self._render(rows, count, income, expense, flt.is_active())

    def _render(self, rows: list[Transaction], count: int, income: int, expense: int, filtered: bool) -> None:
        ctx, p = self.ctx, self.p
        self.stat_labels["count"].configure(text=f"{count:,}")
        self.stat_labels["income"].configure(text=ctx.money(income))
        self.stat_labels["expense"].configure(text=ctx.money(expense))
        self.stat_labels["net"].configure(text=ctx.money(income - expense, signed=True))
        self.tree.delete(*self.tree.get_children())
        self._rows = {}
        for i, tx in enumerate(rows):
            sign = tx.amount if tx.type == "income" else -tx.amount
            tags = (tx.type, "odd") if i % 2 else (tx.type,)
            self.tree.insert("", "end", iid=str(tx.id), tags=tags,
                             values=(ctx.date(tx.date), tx.description or "\u2014", tx.category, tx.payment_method,
                                     tx.type.capitalize(), ctx.money(sign, signed=True)))
            self._rows[str(tx.id)] = tx
        self.tree.configure(height=max(len(rows), 1))
        for child in self.empty_holder.winfo_children():
            child.destroy()
        if rows:
            self.empty_holder.pack_forget()
            self.tree_holder.pack(fill="x", padx=8, before=self.foot)
        else:
            self.tree_holder.pack_forget()
            if filtered:
                state = EmptyState(self.empty_holder, p, ctx.images, icon="filter", title="No matching transactions",
                                   message="Try changing or clearing the filters.")
                state.pack()
                RoundedButton(self.empty_holder, p, "Clear filters", self._clear, style="secondary", outer=p.card).pack(pady=(0, 18))
            else:
                state = EmptyState(self.empty_holder, p, ctx.images, icon="transactions", title="No transactions yet",
                                   message="Add your first income or expense to get started.")
                state.pack()
                RoundedButton(self.empty_holder, p, "Add transaction", self._add, outer=p.card).pack(pady=(0, 18))
            self.empty_holder.pack(fill="x", before=self.foot)
        first = self.page_index * self.page_size + 1 if rows else 0
        self.range_label.configure(text=f"Showing {first}\u2013{first + len(rows) - 1 if rows else 0} of {count:,}")
        pages = max((count - 1) // self.page_size + 1, 1)
        self.page_label.configure(text=f"Page {self.page_index + 1} of {pages}")
        self._on_select()

    def _go(self, delta: int) -> None:
        new = self.page_index + delta
        count = self.ctx.finance.count_transactions(self._flt)[0]
        if 0 <= new <= max((count - 1) // self.page_size, 0):
            self.page_index = new
            self._load()

    def _change_size(self) -> None:
        self.page_size = int(self.size_box.get())
        self._apply()

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _selected(self) -> Transaction | None:
        sel = self.tree.selection()
        return self._rows.get(sel[0]) if sel else None

    def _on_select(self) -> None:
        on = self._selected() is not None
        for b in (self.view_btn, self.edit_btn, self.delete_btn):
            b.set_enabled(on)

    def _context_menu(self, event: tk.Event) -> None:
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        p = self.p
        menu = tk.Menu(self, tearoff=0, bg=p.card, fg=p.text, activebackground=p.primary,
                       activeforeground=p.on_primary, bd=0, font=font(10))
        menu.add_command(label="View details", command=self._view_selected)
        menu.add_command(label="Edit", command=self._edit_selected)
        menu.add_separator()
        menu.add_command(label="Delete", command=self._delete_selected)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _add(self) -> None:
        kind = {"Income": "income"}.get(self.type_var.get(), "expense")
        TransactionDialog(self, self.ctx, default_type=kind)

    def _view_selected(self) -> None:
        tx = self._selected()
        if tx:
            TransactionDetailDialog(self, self.ctx, tx, self._edit, self._delete)

    def _edit_selected(self) -> None:
        tx = self._selected()
        if tx:
            self._edit(tx)

    def _edit(self, tx: Transaction) -> None:
        TransactionDialog(self, self.ctx, tx)

    def _delete_selected(self) -> None:
        tx = self._selected()
        if tx:
            self._delete(tx)

    def _delete(self, tx: Transaction) -> None:
        ctx = self.ctx
        label = f"{tx.description or tx.category} \u2013 {ctx.money(tx.amount)} on {ctx.date(tx.date)}"
        if not messagebox.askyesno("Delete transaction", f"Delete this transaction?\n\n{label}\n\nThis cannot be undone.",
                                   icon="warning", parent=self):
            return
        try:
            ctx.finance.delete_transaction(tx.id)
        except DatabaseError as exc:
            messagebox.showerror("Could not delete", str(exc), parent=self)
            return
        ctx.notify_data_changed()

    def _export(self) -> None:
        try:
            flt = self._build_filter()
        except ValidationError as exc:
            messagebox.showwarning("Check your filters", str(exc), parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, title="Export transactions", defaultextension=".csv",
                                            filetypes=[("CSV file", "*.csv")], initialdir=str(EXPORT_DIR),
                                            initialfile=f"transactions_{today_iso()}.csv")
        if not path:
            return
        ctx = self.ctx

        def work():
            return export_transactions_csv(ctx.finance.list_transactions(flt), path, ctx.currency)

        def done(result, error):
            if error:
                messagebox.showerror("Export failed", str(error), parent=self)
            elif messagebox.askyesno("Export complete", f"Saved to:\n{result}\n\nOpen the file now?", parent=self):
                open_path(result)

        run_in_background(self, work, done)
