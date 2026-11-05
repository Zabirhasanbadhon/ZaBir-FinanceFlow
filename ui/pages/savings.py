"""Savings goals: create/edit/delete, add or withdraw money, history and progress."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from config import GOAL_ICONS
from core.context import AppContext
from core.savings_manager import GoalProgress
from database.db_manager import DatabaseError
from ui.components import (Card, EmptyState, IconButton, PageHeader, ProgressBar, RoundedButton, StatCard,
                           make_label)
from ui.dialogs import Dialog, IconPicker
from ui.pages.base import ScrollPage
from utils.helpers import minor_to_text, today_iso
from utils.validators import ValidationError, parse_amount


class GoalDialog(Dialog):
    def __init__(self, parent: tk.Misc, ctx: AppContext, goal: GoalProgress | None = None) -> None:
        self.goal = goal
        super().__init__(parent, ctx, "Edit savings goal" if goal else "New savings goal",
                         subtitle="Set a target and an optional date to aim for.", width=520,
                         submit_text="Save changes" if goal else "Create goal")

    def build(self, body: tk.Frame) -> None:
        p, ctx, g = self.p, self.ctx, self.goal
        self.name = self.entry_field("Goal name", g.name if g else "")
        self.target = self.entry_field(f"Target amount ({ctx.currency.code})", minor_to_text(g.target) if g else "")
        if g is None:
            self.initial = self.entry_field(f"Already saved ({ctx.currency.code}, optional)", "")
        self.start = self.date_field("Start date", g.start_date if g else today_iso())
        self.end = self.date_field("Target date", g.target_date if g else None, optional=True)
        self.desc = self.entry_field("Description (optional)", g.description if g else "")
        self.icons = IconPicker(self.field("Icon"), ctx, GOAL_ICONS, g.icon if g else "savings", p.primary, per_row=12)
        self.icons.pack(anchor="w")

    def submit(self) -> None:
        mgr = self.ctx.savings
        target = parse_amount(self.target.get(), field="Target amount")
        start = self.read_date(self.start, "Start date")
        end = self.read_date(self.end, "Target date", optional=True)
        if self.goal:
            mgr.update_goal(self.goal.id, self.name.get(), target, start, end, self.desc.get(), self.icons.get())
        else:
            text = self.initial.get().strip()
            initial = parse_amount(text, field="Already saved") if text else 0
            mgr.add_goal(self.name.get(), target, initial, start, end, self.desc.get(), self.icons.get())


class ContributionDialog(Dialog):
    def __init__(self, parent: tk.Misc, ctx: AppContext, goal: GoalProgress, withdraw: bool) -> None:
        self.goal, self.is_withdrawal = goal, withdraw
        word = "Withdraw from" if withdraw else "Add money to"
        sub = (f"Saved so far: {ctx.money(goal.saved)}" if withdraw
               else f"Remaining to reach the target: {ctx.money(goal.remaining)}")
        super().__init__(parent, ctx, f"{word} {goal.name}", subtitle=sub, width=470,
                         submit_text="Withdraw" if withdraw else "Add money")

    def build(self, body: tk.Frame) -> None:
        self.amount = self.entry_field(f"Amount ({self.ctx.currency.code})", "")
        self.date_var = self.date_field("Date", today_iso())
        self.note = self.entry_field("Note (optional)", "")

    def submit(self) -> None:
        amount = parse_amount(self.amount.get())
        iso = self.read_date(self.date_var, "Date")
        self.ctx.savings.contribute(self.goal.id, amount, withdraw=self.is_withdrawal, on_date=iso, note=self.note.get())


class HistoryDialog(Dialog):
    def __init__(self, parent: tk.Misc, ctx: AppContext, goal: GoalProgress) -> None:
        self.goal = goal
        super().__init__(parent, ctx, f"{goal.name} \u2013 history", subtitle="Every deposit and withdrawal.",
                         width=560, submit_text=None, notify=False)

    def build(self, body: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        items = ctx.savings.list_contributions(self.goal.id)
        if not items:
            make_label(body, p, "No contributions yet.", size=10, muted=True).pack(pady=20)
            return
        tree = ttk.Treeview(body, columns=("date", "note", "amount"), show="headings", style="App.Treeview",
                            height=min(len(items), 9))
        for col, text, width, anchor in (("date", "Date", 120, "w"), ("note", "Note", 240, "w"), ("amount", "Amount", 140, "e")):
            tree.heading(col, text=text, anchor=anchor)
            tree.column(col, width=width, anchor=anchor)
        tree.tag_configure("in", foreground=p.secondary)
        tree.tag_configure("out", foreground=p.danger)
        for c in items:
            tree.insert("", "end", tags=("in" if c.amount > 0 else "out",),
                        values=(ctx.date(c.date), c.note or "\u2014", ctx.money(c.amount, signed=True)))
        tree.pack(fill="x")


class SavingsPage(ScrollPage):
    def build(self, content: tk.Frame) -> None:
        p, ctx = self.p, self.ctx
        head = PageHeader(content, p, "Savings Goals", "Set targets and watch your savings grow.")
        head.pack(fill="x")
        RoundedButton(head.actions, p, "New goal", lambda: GoalDialog(self, ctx),
                      icon=ctx.images.icon("plus", 16, p.on_primary), outer=p.bg).pack()
        try:
            goals = ctx.savings.list_goals()
            saved, target, count, done = ctx.savings.totals()
        except DatabaseError as exc:
            EmptyState(content, p, ctx.images, icon="bell", title="Could not load goals", message=str(exc), bg=p.bg).pack(pady=40)
            return

        row = self.grid_row((1, 1, 1))
        specs = [dict(title="Total saved", value=ctx.money(saved), subtitle=f"of {ctx.money(target)} targeted",
                      icon="coin", accent=p.secondary),
                 dict(title="Active goals", value=str(count - done), subtitle="In progress", icon="savings", accent=p.primary),
                 dict(title="Completed", value=str(done), subtitle="Goals reached", icon="check", accent=p.warning)]
        for i, spec in enumerate(specs):
            self.place(StatCard(row, p, ctx.images, **spec), i, 3)

        if not goals:
            card = Card(content, p)
            card.pack(fill="x", pady=(16, 0))
            EmptyState(card.body, p, ctx.images, icon="savings", title="No savings goals yet",
                       message="Create a goal such as an emergency fund or a new laptop.").pack(fill="x")
            RoundedButton(card.body, p, "Create your first goal", lambda: GoalDialog(self, ctx), outer=p.card).pack(pady=(0, 8))
            return
        active = [g for g in goals if not g.completed]
        finished = [g for g in goals if g.completed]
        if active:
            self._section("In progress", active)
        if finished:
            self._section("Completed goals", finished)

    def _section(self, title: str, goals: list[GoalProgress]) -> None:
        p = self.p
        make_label(self.content, p, title, size=13, bold=True, bg=p.bg).pack(anchor="w", pady=(22, 0))
        grid = self.grid_row((1, 1), top=10)
        for i, goal in enumerate(goals):
            card = Card(grid, p)
            self.place(card, i % 2, 2, row=i // 2)
            grid.rowconfigure(i // 2, weight=1)
            self._goal_card(card.body, goal)
            card.grid_configure(pady=(0 if i < 2 else 14, 0))

    def _goal_card(self, body: tk.Frame, g: GoalProgress) -> None:
        p, ctx = self.p, self.ctx
        top = tk.Frame(body, bg=p.card)
        top.pack(fill="x")
        accent = p.secondary if g.completed else p.primary
        self._keep = getattr(self, "_keep", [])
        bubble = ctx.images.circle_icon(g.icon, 46, p.mix(accent, 0.16), accent)
        self._keep.append(bubble)
        tk.Label(top, image=bubble, bg=p.card).pack(side="left")
        text = tk.Frame(top, bg=p.card)
        text.pack(side="left", padx=12, fill="x", expand=True)
        make_label(text, p, g.name, size=12, bold=True).pack(anchor="w")
        if g.description:
            make_label(text, p, g.description, size=9, muted=True, wraplength=230, justify="left").pack(anchor="w")
        make_label(top, p, "Done" if g.completed else f"{g.percent}%", size=16, bold=True, color=accent).pack(side="right")

        ProgressBar(body, p, g.ratio, accent, height=12).pack(fill="x", pady=(14, 6))
        make_label(body, p, f"{ctx.money(g.saved)} saved of {ctx.money(g.target)}", size=10, bold=True).pack(anchor="w")
        if g.completed:
            make_label(body, p, "Target reached \u2013 congratulations!", size=9, color=p.secondary).pack(anchor="w", pady=(2, 0))
        else:
            make_label(body, p, f"{ctx.money(g.remaining)} still to go", size=9, muted=True).pack(anchor="w", pady=(2, 0))
            days = g.days_left
            if days is not None:
                when = ctx.date(g.target_date)
                if days < 0:
                    make_label(body, p, f"Target date {when} passed {-days} day(s) ago", size=9, color=p.danger).pack(anchor="w")
                else:
                    needed = g.monthly_needed
                    extra = f" \u00b7 save about {ctx.money(needed)} / month" if needed else ""
                    make_label(body, p, f"Due {when} \u00b7 {days} day(s) left{extra}", size=9, muted=True,
                               wraplength=330, justify="left").pack(anchor="w")
        actions = tk.Frame(body, bg=p.card)
        actions.pack(fill="x", pady=(14, 0))
        RoundedButton(actions, p, "Add money", lambda: ContributionDialog(self, ctx, g, False), outer=p.card, height=32).pack(side="left")
        wd = RoundedButton(actions, p, "Withdraw", lambda: ContributionDialog(self, ctx, g, True), style="secondary",
                           outer=p.card, height=32)
        wd.pack(side="left", padx=8)
        wd.set_enabled(g.saved > 0)
        IconButton(actions, p, ctx.images, "trash", lambda: self._delete(g), size=32, icon_size=16, outer=p.card).pack(side="right")
        IconButton(actions, p, ctx.images, "edit", lambda: GoalDialog(self, ctx, g), size=32, icon_size=16, outer=p.card).pack(side="right")
        IconButton(actions, p, ctx.images, "table", lambda: HistoryDialog(self, ctx, g), size=32, icon_size=16, outer=p.card).pack(side="right")

    def _delete(self, g: GoalProgress) -> None:
        if not messagebox.askyesno("Delete goal", f"Delete \u201c{g.name}\u201d and its {self.ctx.money(g.saved)} contribution history?"
                                   "\n\nThis cannot be undone.", icon="warning", parent=self):
            return
        try:
            self.ctx.savings.delete_goal(g.id)
        except DatabaseError as exc:
            messagebox.showerror("Could not delete", str(exc), parent=self)
            return
        self.ctx.notify_data_changed()
