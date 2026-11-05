"""Date, month and money helpers shared across the application."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from config import MINOR_UNIT, Currency


# ------------------------------------------------------------------ #
# Dates and months ("YYYY-MM" strings are used for month identifiers)
# ------------------------------------------------------------------ #
def today_iso() -> str:
    return date.today().isoformat()


def current_month() -> str:
    return date.today().strftime("%Y-%m")


def parse_month(month: str) -> tuple[int, int]:
    year, mon = month.split("-")
    return int(year), int(mon)


def shift_month(month: str, delta: int) -> str:
    """Return ``month`` moved by ``delta`` months (negative = earlier)."""
    year, mon = parse_month(month)
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def month_bounds(month: str) -> tuple[str, str]:
    """Return (inclusive start, exclusive end) ISO dates for a month."""
    return f"{month}-01", f"{shift_month(month, 1)}-01"


def days_in_month(month: str) -> int:
    year, mon = parse_month(month)
    return calendar.monthrange(year, mon)[1]


def month_label(month: str) -> str:
    year, mon = parse_month(month)
    return f"{calendar.month_name[mon]} {year}"


def month_short(month: str) -> str:
    return calendar.month_abbr[parse_month(month)[1]]


def format_date(iso_date: str, fmt: str) -> str:
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime(fmt)
    except (TypeError, ValueError):
        return str(iso_date or "")


# ------------------------------------------------------------------ #
# Money (integer minor units everywhere; no floats for storage/maths)
# ------------------------------------------------------------------ #
def _group_digits(digits: str, indian: bool) -> str:
    if len(digits) <= 3:
        return digits
    if not indian:
        return f"{int(digits):,}"
    head, tail = digits[:-3], digits[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def format_money(minor: int, currency: Currency, *, signed: bool = False) -> str:
    """Format minor units, e.g. 123456 -> '\u09f31,234.56' for BDT."""
    sign = "-" if minor < 0 else ("+" if signed and minor > 0 else "")
    major, fraction = divmod(abs(int(minor)), MINOR_UNIT)
    body = _group_digits(str(major), currency.indian_grouping)
    return f"{sign}{currency.symbol}{body}.{fraction:02d}"


def compact_number(value: float) -> str:
    """Short axis-label style number (1.5K, 2.3M) without a currency symbol."""
    sign = "-" if value < 0 else ""
    v = abs(value)
    for threshold, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= threshold:
            text = f"{v / threshold:.1f}".rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"
    return f"{sign}{v:.0f}"


# ------------------------------------------------------------------ #
# Misc text / math helpers
# ------------------------------------------------------------------ #
def truncate(text: str, length: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= length else text[: max(length - 1, 1)].rstrip() + "\u2026"


def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "U"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def ratio(part: int, whole: int) -> float:
    return (part / whole) if whole > 0 else 0.0


def minor_to_text(minor: int) -> str:
    """Plain decimal text for editing/CSV, e.g. 125050 -> '1250.50' (no symbol, no grouping)."""
    major, fraction = divmod(abs(int(minor)), MINOR_UNIT)
    return f"{'-' if minor < 0 else ''}{major}.{fraction:02d}"


def recent_months(count: int, end: str | None = None) -> list[str]:
    """Newest-first list of ``count`` months ending at ``end`` (default: this month)."""
    last = end or current_month()
    return [shift_month(last, -i) for i in range(count)]


def year_bounds(year: int) -> tuple[str, str]:
    return f"{year:04d}-01-01", f"{year + 1:04d}-01-01"


def last_day(end_exclusive: str) -> str:
    """Inclusive last ISO date for an exclusive end date."""
    return (date.fromisoformat(end_exclusive) - timedelta(days=1)).isoformat()


def open_path(path) -> None:
    """Open a file or folder with the operating system's default application."""
    import os
    import subprocess
    import sys

    target = str(path)
    if sys.platform == "win32":
        os.startfile(target)  # noqa: S606 - user-initiated, local path
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])
