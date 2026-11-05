"""Central configuration for ZaBir FinanceFlow.

All filesystem locations, currency definitions, navigation metadata and
default settings live here so that every other module imports from a single
source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APP_NAME = "ZaBir HaSan"
APP_TAGLINE = "Track. Budget. Grow."
APP_VERSION = "1.0.0"

# --------------------------------------------------------------------------- #
# Paths (all relative to the project root, Windows-safe via pathlib)
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "finance.db"
LOG_PATH = DATA_DIR / "app.log"
BACKUP_DIR = BASE_DIR / "backups"
EXPORT_DIR = BASE_DIR / "exports"
ASSETS_DIR = BASE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
IMAGES_DIR = ASSETS_DIR / "images"
FONTS_DIR = ASSETS_DIR / "fonts"


def ensure_directories() -> None:
    """Create every runtime directory the application relies on."""
    for folder in (DATA_DIR, BACKUP_DIR, EXPORT_DIR, ICONS_DIR, IMAGES_DIR, FONTS_DIR):
        folder.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #
MINOR_UNIT = 100  # 1 major unit (e.g. 1 taka) == 100 minor units (poisha)
MAX_AMOUNT_MINOR = 999_999_999_999  # 9,999,999,999.99 – upper sanity bound


@dataclass(frozen=True)
class Currency:
    """A display currency. No conversion between currencies is ever performed."""

    code: str
    symbol: str
    name: str
    indian_grouping: bool = False  # lakh/crore digit grouping (12,34,567)


CURRENCIES: dict[str, Currency] = {
    "BDT": Currency("BDT", "\u09f3", "Bangladeshi Taka", True),
    "USD": Currency("USD", "$", "US Dollar"),
    "EUR": Currency("EUR", "\u20ac", "Euro"),
    "GBP": Currency("GBP", "\u00a3", "British Pound"),
    "INR": Currency("INR", "\u20b9", "Indian Rupee", True),
}
DEFAULT_CURRENCY = "BDT"

# --------------------------------------------------------------------------- #
# Settings & formats
# --------------------------------------------------------------------------- #
DATE_FORMATS: list[tuple[str, str]] = [
    ("04 Nov 2026", "%d %b %Y"),
    ("04/11/2026", "%d/%m/%Y"),
    ("11/04/2026", "%m/%d/%Y"),
    ("2026-11-04", "%Y-%m-%d"),
]

DEFAULT_SETTINGS: dict[str, str] = {
    "theme": "dark",
    "currency": DEFAULT_CURRENCY,
    "date_format": "%d %b %Y",
    "default_dashboard_month": "current",  # "current" or "previous"
    "user_name": "ZaBir",
    "auto_backup": "1",  # snapshot on exit, newest 10 kept
}

PAYMENT_METHODS = ["Cash", "Bank Transfer", "Debit/Credit Card", "bKash", "Nagad", "Other"]

# --------------------------------------------------------------------------- #
# UI metrics
# --------------------------------------------------------------------------- #
FONT_FAMILY = "Segoe UI"
SIDEBAR_WIDTH = 244
TOPBAR_HEIGHT = 68
MIN_WINDOW_SIZE = (1180, 720)
DEFAULT_WINDOW_SIZE = (1366, 820)

# (key, label, icon-name)
NAV_ITEMS: list[tuple[str, str, str]] = [
    ("dashboard", "Dashboard", "dashboard"),
    ("transactions", "Transactions", "transactions"),
    ("budgets", "Budgets", "budgets"),
    ("categories", "Categories", "categories"),
    ("savings", "Savings Goals", "savings"),
    ("analytics", "Analytics", "analytics"),
    ("reports", "Reports", "reports"),
    ("settings", "Settings", "settings"),
]

# --------------------------------------------------------------------------- #
# Pickers used by category / goal dialogs
# --------------------------------------------------------------------------- #
COLOR_PRESETS = ["#6366F1", "#8B5CF6", "#EC4899", "#EF4444", "#F97316", "#EAB308",
                 "#84CC16", "#22C55E", "#14B8A6", "#06B6D4", "#3B82F6", "#64748B"]
CATEGORY_ICONS = ["briefcase", "laptop", "store", "trending-up", "gift", "plus-circle", "utensils",
                  "bus", "shopping-bag", "home", "book", "heart", "film", "zap", "plane", "repeat",
                  "coin", "wallet", "tag", "more-horizontal"]
GOAL_ICONS = ["savings", "coin", "wallet", "plane", "home", "laptop", "gift", "heart", "book",
              "bus", "briefcase", "store"]
BACKUP_KEEP = 10
