"""Input validation helpers. All failures raise :class:`ValidationError`."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from config import MAX_AMOUNT_MINOR, MINOR_UNIT


class ValidationError(ValueError):
    """A user-correctable input problem; the message is safe to display."""


def parse_amount(text: str, *, field: str = "Amount") -> int:
    """Convert user text such as '1,250.50' to integer minor units (125050)."""
    raw = (text or "").strip().replace(",", "").replace(" ", "")
    if not raw:
        raise ValidationError(f"{field} is required.")
    if not all(ch.isdigit() or ch in ".-+" for ch in raw):
        raise ValidationError(f"{field} must be a valid number.")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise ValidationError(f"{field} must be a valid number.") from None
    if not value.is_finite():
        raise ValidationError(f"{field} must be a valid number.")
    if value <= 0:
        raise ValidationError(f"{field} must be greater than zero.")
    if value != value.quantize(Decimal("0.01")):
        raise ValidationError(f"{field} cannot have more than 2 decimal places.")
    minor = int((value * MINOR_UNIT).to_integral_value())
    if minor > MAX_AMOUNT_MINOR:
        raise ValidationError(f"{field} is too large.")
    return minor


def parse_date(text: str, fmt: str = "%Y-%m-%d", *, field: str = "Date") -> str:
    """Parse ``text`` with ``fmt`` and return an ISO ``YYYY-MM-DD`` string."""
    try:
        return datetime.strptime((text or "").strip(), fmt).strftime("%Y-%m-%d")
    except ValueError:
        raise ValidationError(f"{field} is not a valid date.") from None


def require_text(value: str, *, field: str, max_length: int = 120) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValidationError(f"{field} is required.")
    if len(cleaned) > max_length:
        raise ValidationError(f"{field} must be at most {max_length} characters.")
    return cleaned
