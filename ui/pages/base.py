"""Base classes shared by all pages."""
from __future__ import annotations

import tkinter as tk

from core.context import AppContext
from ui.components import ScrollableFrame


class BasePage(tk.Frame):
    """Every page receives the AppContext and exposes ``refresh()``."""

    def __init__(self, parent: tk.Misc, ctx: AppContext) -> None:
        self.ctx = ctx
        self.p = ctx.theme.palette
        super().__init__(parent, bg=self.p.bg)

    def refresh(self) -> None:
        """Re-read data and redraw. Called after financial data changes."""


class ScrollPage(BasePage):
    """A vertically scrolling page. Subclasses implement ``build(content)``; ``refresh()`` rebuilds
    while keeping the scroll position."""

    def __init__(self, parent: tk.Misc, ctx: AppContext) -> None:
        super().__init__(parent, ctx)
        self.scroll = ScrollableFrame(self, self.p)
        self.scroll.pack(fill="both", expand=True)
        self.content: tk.Frame = self.scroll.inner
        self._render()

    def _render(self) -> None:
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        self.content = tk.Frame(self.scroll.inner, bg=self.p.bg)
        self.content.pack(fill="x", padx=28, pady=(24, 30))
        self.build(self.content)

    def refresh(self) -> None:
        position = self.scroll.canvas.yview()[0]
        self._render()
        self.after_idle(lambda: self.scroll.canvas.yview_moveto(position))

    def build(self, content: tk.Frame) -> None:
        raise NotImplementedError

    def grid_row(self, weights: tuple[int, ...], top: int = 16) -> tk.Frame:
        row = tk.Frame(self.content, bg=self.p.bg)
        row.pack(fill="x", pady=(top, 0))
        for i, weight in enumerate(weights):
            row.columnconfigure(i, weight=weight, uniform="col")
        row.rowconfigure(0, weight=1)
        return row

    @staticmethod
    def place(widget: tk.Widget, col: int, count: int, row: int = 0) -> None:
        widget.grid(row=row, column=col, sticky="nsew",
                    padx=(0 if col == 0 else 8, 0 if col == count - 1 else 8))
