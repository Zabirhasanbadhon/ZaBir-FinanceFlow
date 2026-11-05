"""Categories: create/edit/delete with colours and icons; safe reassignment on delete."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from config import CATEGORY_ICONS, COLOR_PRESETS
from core.category_manager import Category, CategoryInUseError
from core.context import AppContext
from database.db_manager import DatabaseError
from ui.components import Card, EmptyState, IconButton, PageHeader, RoundedButton, card_header, make_label
from ui.components import Segmented
from ui.dialogs import ColorPicker, Dialog, IconPicker
from ui.pages.base import ScrollPage
from utils.helpers import current_month, month_label
from utils.validators import ValidationError


class CategoryDialog(Dialog):
    def __init__(self, parent: tk.Misc, ctx: AppContext, category: Category | None = None,
                 default_type: str = "expense") -> None:
        self.category, self.kind = category, (category.type if category else default_type)
        super().__init__(parent, ctx, "Edit category" if category else "New category",
                         subtitle="Choose a name, colour and icon.", width=500,
                         submit_text="Save changes" if category else "Create category")

    def build(self, body: tk.Frame) -> None:
        p, cat = self.p, self.category
        if cat is None:
            Segmented(body, p, [("Expense", "expense"), ("Income", "income")], self.kind,
                      lambda k: setattr(self, "kind", k)).pack(anchor="w", pady=(0, 14))
        self.name = self.entry_field("Name", cat.name if cat else "")
        color = cat.color if cat else COLOR_PRESETS[0]
        self.color_picker = ColorPicker(self.field("Colour"), p, color)
        self.color_picker.pack(fill="x")
        icon_row = self.field("Icon")
        self.icon_picker = IconPicker(icon_row, self.ctx, CATEGORY_ICONS, cat.icon if cat else "tag", color)
        self.icon_picker.pack(anchor="w")
        # keep icon accent in sync with the chosen colour
        self.after(200, self._sync)

    def _sync(self) -> None:
        try:
            self.icon_picker.set_accent(self.color_picker.get())
            self.after(250, self._sync)
        except tk.TclError:
            pass

    def submit(self) -> None:
        mgr = self.ctx.categories
        if self.category:
            mgr.update(self.category.id, self.name.get(), self.color_picker.get(), self.icon_picker.get())
        else:
            mgr.add(self.name.get(), self.kind, self.color_picker.get(), self.icon_picker.get())


class ReassignDialog(Dialog):
    """Move a category's transactions to another category, then delete it."""

    def __init__(self, parent: tk.Misc, ctx: AppContext, category: Category, count: int) -> None:
        self.category, self.count = category, count
        super().__init__(parent, ctx, "Delete category",
                         subtitle=f"\u201c{category.name}\u201d has {count} transaction(s). Choose where they should go "
                                  "before it is deleted.", width=480, submit_text="Move & delete")

    def build(self, body: tk.Frame) -> None:
        options = [c for c in self.ctx.categories.list(self.category.type) if c.id != self.category.id]
        self._map = {c.name: c.id for c in options}
        self.target = self.combo_field(f"Move transactions to ({self.category.type})", list(self._map))

    def submit(self) -> None:
        target = self._map.get(self.target.get())
        if target is None:
            raise ValidationError("Select a category to move the transactions to.")
        self.ctx.categories.delete(self.category.id, reassign_to=target)


class CategoriesPage(ScrollPage):
    def build(self, content: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        head = PageHeader(content, p, "Categories", f"Organise income and expenses. Totals shown for {month_label(current_month())}.")
        head.pack(fill="x")
        RoundedButton(head.actions, p, "New category", lambda: CategoryDialog(self, ctx),
                      icon=ctx.images.icon("plus", 16, p.on_primary), outer=p.bg).pack()
        try:
            cats = ctx.categories.list()
        except DatabaseError as exc:
            EmptyState(content, p, ctx.images, icon="bell", title="Could not load categories", message=str(exc), bg=p.bg).pack(pady=40)
            return
        row = self.grid_row((1, 1))
        for i, (kind, title, color) in enumerate((("income", "Income categories", p.secondary),
                                                   ("expense", "Expense categories", p.danger))):
            card = Card(row, p)
            self.place(card, i, 2)
            items = [c for c in cats if c.type == kind]
            card_header(card.body, p, title, f"{len(items)} categories")
            if not items:
                EmptyState(card.body, p, ctx.images, icon="categories", title="No categories",
                           message="Create a category to start organising.").pack(fill="x")
            for cat in items:
                self._row(card.body, cat, color)

    def _row(self, body: tk.Frame, cat: Category, accent: str) -> None:
        p, ctx = self.p, self.ctx
        line = tk.Frame(body, bg=p.card)
        line.pack(fill="x", pady=5)
        line.columnconfigure(1, weight=1)
        bubble = ctx.images.circle_icon(cat.icon, 38, p.mix(cat.color, 0.2), cat.color)
        tk.Label(line, image=bubble, bg=p.card).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        line._bubble = bubble
        make_label(line, p, cat.name, size=10, bold=True).grid(row=0, column=1, sticky="w")
        uses = f"{cat.tx_count} transaction{'s' if cat.tx_count != 1 else ''} \u00b7 {ctx.money(cat.total)} all time"
        make_label(line, p, uses, size=8, muted=True).grid(row=1, column=1, sticky="w")
        make_label(line, p, ctx.money(cat.month_total), size=10, bold=True, color=accent if cat.month_total else p.text_muted).grid(
            row=0, column=2, rowspan=2, padx=8)
        IconButton(line, p, ctx.images, "edit", lambda c=cat: CategoryDialog(self, ctx, c), size=32, icon_size=16,
                   outer=p.card).grid(row=0, column=3, rowspan=2)
        IconButton(line, p, ctx.images, "trash", lambda c=cat: self._delete(c), size=32, icon_size=16,
                   outer=p.card).grid(row=0, column=4, rowspan=2)
        tk.Frame(body, bg=p.border, height=1).pack(fill="x")

    def _delete(self, cat: Category) -> None:
        ctx = self.ctx
        try:
            count = ctx.categories.usage_count(cat.id)
            if count:
                others = [c for c in ctx.categories.list(cat.type) if c.id != cat.id]
                if not others:
                    messagebox.showinfo("Cannot delete", f"\u201c{cat.name}\u201d is in use and there is no other {cat.type} "
                                        "category to move its transactions to. Create another one first.", parent=self)
                    return
                ReassignDialog(self, ctx, cat, count)
                return
            if messagebox.askyesno("Delete category", f"Delete \u201c{cat.name}\u201d? Any budgets for it are removed too.",
                                   icon="warning", parent=self):
                ctx.categories.delete(cat.id)
                ctx.notify_data_changed()
        except (CategoryInUseError, DatabaseError) as exc:
            messagebox.showerror("Could not delete", str(exc), parent=self)
