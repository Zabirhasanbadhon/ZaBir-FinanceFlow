"""Application context: wires services together and carries shared UI state."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable

from config import CURRENCIES, DEFAULT_CURRENCY, Currency, ensure_directories
from core.budget_manager import Alert, BudgetManager
from core.category_manager import CategoryManager
from core.finance_manager import FinanceManager
from core.report_manager import ReportManager
from core.savings_manager import SavingsManager
from database.db_manager import DatabaseManager
from ui.theme import ThemeManager
from utils.helpers import current_month, format_date, format_money, shift_month
from utils.image_manager import ImageManager

log = logging.getLogger(__name__)


class AppContext:
    """Single object passed to every page/component instead of globals."""

    def __init__(self, db_path=None) -> None:
        ensure_directories()
        self.db = DatabaseManager(db_path) if db_path else DatabaseManager()
        self.db.initialize()
        self.finance = FinanceManager(self.db)
        self.budgets = BudgetManager(self.db)
        self.savings = SavingsManager(self.db)
        self.categories = CategoryManager(self.db)
        self.reports = ReportManager(self.db, self.finance, self.budgets, self.savings, self.categories)
        self.theme = ThemeManager(self.db.get_setting("theme", "dark"))
        self.images = ImageManager()
        self.search_query = ""
        self.navigate: Callable[[str], None] = lambda key: None
        self._listeners: dict[str, list[Callable[[], None]]] = defaultdict(list)

    # ---- events ------------------------------------------------------- #
    def subscribe(self, event: str, callback: Callable[[], None]) -> None:
        """Events: 'data' (financial data changed), 'theme', 'settings'."""
        self._listeners[event].append(callback)

    def emit(self, event: str) -> None:
        for callback in list(self._listeners[event]):
            callback()

    def notify_data_changed(self) -> None:
        self.emit("data")

    # ---- settings ----------------------------------------------------- #
    @property
    def currency(self) -> Currency:
        return CURRENCIES.get(self.db.get_setting("currency", DEFAULT_CURRENCY), CURRENCIES[DEFAULT_CURRENCY])

    @property
    def date_format(self) -> str:
        return self.db.get_setting("date_format", "%d %b %Y")

    @property
    def user_name(self) -> str:
        return self.db.get_setting("user_name", "ZaBir")

    def set_theme(self, name: str) -> None:
        if name == self.theme.name:
            return
        self.theme.set(name)
        self.db.set_setting("theme", self.theme.name)
        self.emit("theme")

    def update_setting(self, key: str, value: str) -> None:
        self.db.set_setting(key, value)
        self.emit("settings")

    def default_dashboard_month(self) -> str:
        month = current_month()
        if self.db.get_setting("default_dashboard_month", "current") == "previous":
            return shift_month(month, -1)
        return month

    # ---- formatting --------------------------------------------------- #
    def money(self, minor: int, *, signed: bool = False) -> str:
        return format_money(minor, self.currency, signed=signed)

    def money_chart(self, minor: int) -> str:
        """Amount with the ISO code instead of the symbol, for Matplotlib text (fonts may lack e.g. \u09f3)."""
        from dataclasses import replace

        return format_money(minor, replace(self.currency, symbol=f"{self.currency.code} "))

    def date(self, iso_date: str) -> str:
        return format_date(iso_date, self.date_format)

    # ---- notifications ------------------------------------------------ #
    def alerts(self) -> list[Alert]:
        try:
            return self.budgets.alerts(current_month()) + self.savings.alerts()
        except Exception:  # notifications must never break the UI
            log.exception("Could not compute alerts")
            return []

    def reload_after_restore(self) -> None:
        """Re-read persisted state (theme etc.) after the database file was replaced."""
        self.theme.set(self.db.get_setting("theme", "dark"))
        self.emit("theme")

    def close(self) -> None:
        """Flush an automatic backup (if enabled) and close the database."""
        try:
            if self.db.get_setting("auto_backup", "1") == "1" and self.finance.has_transactions():
                self.db.backup(prefix="auto_backup")
                self.db.prune_backups()
        except Exception:
            log.warning("Automatic backup failed", exc_info=True)
        self.db.close()
