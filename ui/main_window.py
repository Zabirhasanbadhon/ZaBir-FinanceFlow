"""Main application window: assembles topbar, sidebar and the active page."""
from __future__ import annotations

import logging
import sys
import tkinter as tk
from tkinter import messagebox

from config import APP_NAME, DEFAULT_WINDOW_SIZE, MIN_WINDOW_SIZE
from core.context import AppContext
from database.db_manager import DatabaseError
from ui.components import EmptyState
from ui.pages.analytics import AnalyticsPage
from ui.pages.base import BasePage
from ui.pages.budgets import BudgetsPage
from ui.pages.categories import CategoriesPage
from ui.pages.dashboard import DashboardPage
from ui.pages.reports import ReportsPage
from ui.pages.savings import SavingsPage
from ui.pages.settings import SettingsPage
from ui.pages.transactions import TransactionsPage
from ui.sidebar import Sidebar
from ui.theme import apply_ttk_styles
from ui.topbar import Topbar

log = logging.getLogger(__name__)

PAGES: dict[str, type[BasePage]] = {
    "dashboard": DashboardPage,
    "transactions": TransactionsPage,
    "budgets": BudgetsPage,
    "categories": CategoriesPage,
    "savings": SavingsPage,
    "analytics": AnalyticsPage,
    "reports": ReportsPage,
    "settings": SettingsPage,
}


class MainWindow(tk.Tk):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.current_key = "dashboard"
        self.page: BasePage | None = None
        self.sidebar: Sidebar | None = None
        self.topbar: Topbar | None = None
        self._rebuild_pending = False

        ctx.navigate = self.navigate
        ctx.subscribe("theme", self._schedule_rebuild)
        ctx.subscribe("settings", self._schedule_rebuild)
        ctx.subscribe("data", self._on_data_changed)

        self.title(APP_NAME)
        self.minsize(*MIN_WINDOW_SIZE)
        self._center(*DEFAULT_WINDOW_SIZE)
        ctx.images.save_brand_assets()
        self._app_icon = ctx.images.logo(64)
        try:
            self.iconphoto(True, self._app_icon)
        except tk.TclError:
            log.warning("Could not set window icon")

        self.report_callback_exception = self._handle_exception
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()

    # ------------------------------------------------------------------ #
    def _center(self, width: int, height: int) -> None:
        width = min(width, self.winfo_screenwidth() - 60)
        height = min(height, self.winfo_screenheight() - 100)
        x = (self.winfo_screenwidth() - width) // 2
        y = max((self.winfo_screenheight() - height) // 2 - 20, 0)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build(self) -> None:
        """(Re)create the whole shell with the current theme and settings."""
        self._rebuild_pending = False
        p = self.ctx.theme.palette
        apply_ttk_styles(self, p)
        self.configure(bg=p.bg)
        for child in self.winfo_children():
            child.destroy()
        self.page = None

        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)
        self.topbar = Topbar(self, self.ctx, self._on_search, self._toggle_theme)
        self.topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Frame(self, bg=p.border, height=1).grid(row=1, column=0, columnspan=2, sticky="ew")
        self.sidebar = Sidebar(self, self.ctx, self.current_key, self.navigate)
        self.sidebar.grid(row=2, column=0, sticky="ns")
        self.content = tk.Frame(self, bg=p.bg)
        self.content.grid(row=2, column=1, sticky="nsew")
        self._show_page(self.current_key)
        self._apply_titlebar(p.is_dark)

    def _schedule_rebuild(self) -> None:
        if not self._rebuild_pending:
            self._rebuild_pending = True
            self.after(20, self._build)

    # ------------------------------------------------------------------ #
    def navigate(self, key: str) -> None:
        if key not in PAGES:
            return
        self.current_key = key
        if self.sidebar:
            self.sidebar.set_active(key)
        self._show_page(key)

    def _show_page(self, key: str) -> None:
        if self.page is not None:
            self.page.destroy()
            self.page = None
        for child in self.content.winfo_children():
            child.destroy()
        try:
            self.page = PAGES[key](self.content, self.ctx)
            self.page.pack(fill="both", expand=True)
        except DatabaseError as exc:
            log.exception("Page %s failed to load", key)
            self._show_error_state(str(exc))

    def _show_error_state(self, message: str) -> None:
        p = self.ctx.theme.palette
        EmptyState(self.content, p, self.ctx.images, icon="bell", title="Something went wrong",
                   message=message, bg=p.bg).pack(expand=True)

    def _on_data_changed(self) -> None:
        if self.page is not None:
            self.page.refresh()
        if self.topbar is not None:
            self.topbar.refresh_notifications()

    def _on_search(self, query: str) -> None:
        self.ctx.search_query = query
        self.navigate("transactions")

    def _toggle_theme(self) -> None:
        self.ctx.set_theme("light" if self.ctx.theme.name == "dark" else "dark")

    # ------------------------------------------------------------------ #
    def _apply_titlebar(self, dark: bool) -> None:
        """Use the dark immersive title bar on Windows 10/11 (best effort)."""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1 if dark else 0)
            for attribute in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                           ctypes.sizeof(value))
        except Exception:
            log.debug("Title bar theming unavailable", exc_info=True)

    def _handle_exception(self, exc_type, exc, tb) -> None:
        """Centralised handler for errors raised inside Tk callbacks."""
        log.error("Unhandled UI error", exc_info=(exc_type, exc, tb))
        if isinstance(exc, DatabaseError):
            messagebox.showerror("Database error", str(exc), parent=self)
        else:
            messagebox.showerror(
                "Unexpected error",
                f"Something went wrong:\n\n{exc}\n\nDetails were written to data/app.log.",
                parent=self,
            )

    def _on_close(self) -> None:
        self.ctx.close()
        self.destroy()
