"""CSV and PDF export. Safe to call from a background thread (no Tk, no pyplot)."""
from __future__ import annotations

import csv
import io
import logging
import os
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence
from xml.sax.saxutils import escape

import matplotlib
import matplotlib.ticker
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, Frame, Image, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from config import APP_NAME, Currency
from core.finance_manager import Transaction
from core.report_manager import Money, MonthlyStatement, ReportData
from utils.helpers import compact_number, format_money, minor_to_text, month_label, month_short

log = logging.getLogger(__name__)

INDIGO = colors.HexColor("#4F46E5")
GREEN = colors.HexColor("#16A34A")
RED = colors.HexColor("#DC2626")
SLATE = colors.HexColor("#64748B")
INK = colors.HexColor("#172033")
LIGHT = colors.HexColor("#F1F5F9")
LINE = colors.HexColor("#E2E8F0")


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def _csv_cell(cell: object) -> str:
    return minor_to_text(cell.minor) if isinstance(cell, Money) else str(cell)


def _write_csv(path: Path, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:  # BOM keeps Excel happy
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    return path


def export_report_csv(report: ReportData, path: Path, currency: Currency) -> Path:
    """Monetary columns are plain decimals; the currency code is added to the headers."""
    money_cols = {i for row in report.rows for i, c in enumerate(row) if isinstance(c, Money)}
    headers = [f"{h} ({currency.code})" if i in money_cols else h for i, h in enumerate(report.headers)]
    rows = [[_csv_cell(c) for c in row] for row in report.rows]
    if report.total_row:
        rows.append([_csv_cell(c) for c in report.total_row])
    return _write_csv(path, headers, rows)


def export_transactions_csv(transactions: Sequence[Transaction], path: Path, currency: Currency) -> Path:
    headers = ["ID", "Date", "Type", "Category", "Description", "Payment method",
               f"Amount ({currency.code})", "Created at"]
    rows = [[t.id, t.date, t.type.capitalize(), t.category, t.description, t.payment_method,
             minor_to_text(t.amount), t.created_at] for t in transactions]
    return _write_csv(path, headers, rows)


# --------------------------------------------------------------------------- #
# Fonts / currency symbol handling for the PDF
# --------------------------------------------------------------------------- #
@dataclass
class PdfStyle:
    regular: str
    bold: str
    currency: Currency  # symbol possibly replaced by "BDT " when no font has the glyph

    def money(self, minor: int, signed: bool = False) -> str:
        return format_money(minor, self.currency, signed=signed)

    def cell(self, cell: object) -> str:
        return self.money(cell.minor) if isinstance(cell, Money) else str(cell)


_FONT_CANDIDATES = [
    ("FFNirmala", "nirmala.ttf", "nirmalab.ttf"),
    ("FFVrinda", "vrinda.ttf", "vrindab.ttf"),
    ("FFSegoe", "segoeui.ttf", "segoeuib.ttf"),
    ("FFArial", "arial.ttf", "arialbd.ttf"),
]


def _font_dirs() -> list[Path]:
    dirs = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", Path("/usr/share/fonts/truetype/dejavu"),
            Path(matplotlib.get_data_path()) / "fonts" / "ttf"]
    return [d for d in dirs if d.is_dir()]


def _find(name: str) -> Path | None:
    for folder in _font_dirs():
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def pdf_style(currency: Currency) -> PdfStyle:
    """Pick fonts that can actually draw the currency symbol, else fall back to the ISO code."""
    if currency.symbol in ("$", "\u00a3", "\u20ac"):  # covered by built-in Helvetica
        return PdfStyle("Helvetica", "Helvetica-Bold", currency)
    candidates = list(_FONT_CANDIDATES) + [("FFDejaVu", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf")]
    for family, regular_file, bold_file in candidates:
        reg = _find(regular_file)
        if reg is None:
            continue
        try:
            reg_name = f"{family}-R"
            if reg_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(reg_name, str(reg)))
            if ord(currency.symbol[0]) not in pdfmetrics.getFont(reg_name).face.charToGlyph:
                continue
            bold_path, bold_name = _find(bold_file), f"{family}-B"
            if bold_path and bold_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
            return PdfStyle(reg_name, bold_name if bold_path else reg_name, currency)
        except Exception:
            log.debug("Font candidate %s unusable", family, exc_info=True)
    return PdfStyle("Helvetica", "Helvetica-Bold", replace(currency, symbol=f"{currency.code} "))


# --------------------------------------------------------------------------- #
# Shared PDF plumbing
# --------------------------------------------------------------------------- #
def _numbered_canvas(style: PdfStyle, title: str):
    """Canvas class drawing header, footer and 'Page X of Y' on every page."""

    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved: list[dict] = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _decorate(self, total: int):
            w, h = self._pagesize
            self.setFillColor(INDIGO)
            self.rect(0, h - 1.15 * cm, w, 1.15 * cm, stroke=0, fill=1)
            self.setFillColor(colors.white)
            self.setFont(style.bold, 10)
            self.drawString(1.6 * cm, h - 0.75 * cm, APP_NAME)
            self.setFont(style.regular, 9)
            self.drawRightString(w - 1.6 * cm, h - 0.75 * cm, title)
            self.setStrokeColor(LINE)
            self.line(1.6 * cm, 1.3 * cm, w - 1.6 * cm, 1.3 * cm)
            self.setFillColor(SLATE)
            self.setFont(style.regular, 8)
            self.drawString(1.6 * cm, 0.8 * cm, f"Generated {datetime.now():%d %b %Y, %H:%M} \u2022 {APP_NAME}")
            self.drawRightString(w - 1.6 * cm, 0.8 * cm, f"Page {self._pageNumber} of {total}")

    return NumberedCanvas


def _doc(path: Path, pagesize, title: str, style: PdfStyle):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(path), pagesize=pagesize, title=f"{APP_NAME} \u2013 {title}", author=APP_NAME,
                          leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=2.0 * cm, bottomMargin=1.8 * cm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body", leftPadding=0,
                  rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
    return doc


def _styles(style: PdfStyle) -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle("t", fontName=style.bold, fontSize=22, leading=26, textColor=INK),
        "sub": ParagraphStyle("s", fontName=style.regular, fontSize=11, leading=14, textColor=SLATE),
        "h2": ParagraphStyle("h2", fontName=style.bold, fontSize=12.5, leading=16, textColor=INDIGO,
                             spaceBefore=14, spaceAfter=6, keepWithNext=1),
        "cell": ParagraphStyle("c", fontName=style.regular, fontSize=8.6, leading=11, textColor=INK),
        "cell_r": ParagraphStyle("cr", fontName=style.regular, fontSize=8.6, leading=11, textColor=INK, alignment=2),
        "head": ParagraphStyle("hd", fontName=style.bold, fontSize=8.6, leading=11, textColor=colors.white),
        "head_r": ParagraphStyle("hr", fontName=style.bold, fontSize=8.6, leading=11, textColor=colors.white, alignment=2),
        "note": ParagraphStyle("n", fontName=style.regular, fontSize=9, leading=12, textColor=SLATE),
        "kpi_l": ParagraphStyle("kl", fontName=style.regular, fontSize=8.5, leading=11, textColor=SLATE),
        "kpi_v": ParagraphStyle("kv", fontName=style.bold, fontSize=14, leading=18, textColor=INK),
    }


def _p(text: str, st: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)), st)


def _data_table(headers: Sequence[str], rows: Sequence[Sequence[str]], numeric: set[int], total_width: float,
                st: dict, style: PdfStyle, weights: Sequence[float] | None = None,
                total_row: Sequence[str] | None = None) -> Table:
    data = [[_p(h, st["head_r"] if i in numeric else st["head"]) for i, h in enumerate(headers)]]
    for row in rows:
        data.append([_p(c, st["cell_r"] if i in numeric else st["cell"]) for i, c in enumerate(row)])
    if total_row:
        bold = ParagraphStyle("b", parent=st["cell"], fontName=style.bold)
        bold_r = ParagraphStyle("br", parent=bold, alignment=2)
        data.append([_p(c, bold_r if i in numeric else bold) for i, c in enumerate(total_row)])
    if weights is None:
        weights = [max(6, min(26, max([len(str(headers[i]))] + [len(str(r[i])) for r in rows[:60]])))
                   for i in range(len(headers))]
    scale = total_width / sum(weights)
    table = Table(data, colWidths=[w * scale for w in weights], repeatRows=1)
    cmds = [("BACKGROUND", (0, 0), (-1, 0), INDIGO), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE)]
    last = len(data) - (2 if total_row else 1)
    for r in range(1, last + 1):
        if r % 2 == 0:
            cmds.append(("BACKGROUND", (0, r), (-1, r), LIGHT))
    if total_row:
        cmds += [("BACKGROUND", (0, -1), (-1, -1), LIGHT), ("LINEABOVE", (0, -1), (-1, -1), 1, INDIGO)]
    table.setStyle(TableStyle(cmds))
    return table


def _kpi_table(items: Sequence[tuple[str, str, colors.Color]], width: float, st: dict, per_row: int = 3) -> Table:
    rows, cmds = [], [("VALIGN", (0, 0), (-1, -1), "TOP")]
    cell_w = width / per_row
    for i in range(0, len(items), per_row):
        chunk = list(items[i:i + per_row])
        cells = []
        for label, value, color in chunk:
            val_style = ParagraphStyle("kv2", parent=st["kpi_v"], textColor=color)
            inner = Table([[_p(label, st["kpi_l"])], [_p(value, val_style)]], colWidths=[cell_w - 10])
            inner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), LIGHT), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 6),
                                       ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
            cells.append(inner)
        cells += [""] * (per_row - len(cells))
        rows.append(cells)
    table = Table(rows, colWidths=[cell_w] * per_row)
    table.setStyle(TableStyle(cmds + [("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return table


def _summary_table(summary, width: float, st: dict, style: PdfStyle) -> Table:
    data = [[_p(k, st["kpi_l"]), _p(style.cell(v), ParagraphStyle("sv", parent=st["cell"], fontName=style.bold, alignment=2))]
            for k, v in summary]
    table = Table(data, colWidths=[width * 0.6, width * 0.4])
    table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return table


def _png(fig: Figure, width_cm: float) -> Image:
    buffer = io.BytesIO()
    FigureCanvasAgg(fig)
    fig.savefig(buffer, format="png", dpi=200, facecolor="white")
    buffer.seek(0)
    ratio = fig.get_figheight() / fig.get_figwidth()
    return Image(buffer, width=width_cm * cm, height=width_cm * ratio * cm)


# --------------------------------------------------------------------------- #
# Generic report PDF
# --------------------------------------------------------------------------- #
def export_report_pdf(report: ReportData, path: Path, currency: Currency) -> Path:
    style = pdf_style(currency)
    st = _styles(style)
    size = landscape(A4) if len(report.headers) >= 6 else A4
    doc = _doc(path, size, report.title, style)
    story = [_p(report.title, st["title"]), _p(report.subtitle, st["sub"]), Spacer(1, 10)]
    if report.summary:
        story += [_summary_table(report.summary, min(doc.width, 9 * cm), st, style), Spacer(1, 10)]
    if report.rows:
        rows = [[style.cell(c) for c in r] for r in report.rows]
        total = [style.cell(c) for c in report.total_row] if report.total_row else None
        story.append(_data_table(report.headers, rows, report.numeric_cols, doc.width, st, style, total_row=total))
    else:
        story.append(_p("No data for this period.", st["note"]))
    doc.build(story, canvasmaker=_numbered_canvas(style, report.title))
    return Path(path)


# --------------------------------------------------------------------------- #
# Premium monthly statement
# --------------------------------------------------------------------------- #
def _income_expense_fig(series) -> Figure:
    fig = Figure(figsize=(5.2, 2.7))
    ax = fig.add_subplot(111)
    xs = list(range(len(series)))
    ax.bar([x - 0.2 for x in xs], [p.income / 100 for p in series], 0.4, color="#16A34A", label="Income")
    ax.bar([x + 0.2 for x in xs], [p.expense / 100 for p in series], 0.4, color="#DC2626", label="Expenses")
    ax.set_xticks(xs)
    ax.set_xticklabels([month_short(p.month) for p in series], fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _p: compact_number(v)))
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", color="#E2E8F0")
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8, loc="lower left", ncol=2, bbox_to_anchor=(0, 1.0))
    fig.tight_layout()
    return fig


def _distribution_fig(cats) -> Figure:
    fig = Figure(figsize=(5.2, 2.7))
    ax = fig.add_subplot(111)
    top, rest = cats[:6], cats[6:]
    labels = [c.name for c in top] + (["Others"] if rest else [])
    values = [c.amount / 100 for c in top] + ([sum(c.amount for c in rest) / 100] if rest else [])
    cols = [c.color for c in top] + (["#64748B"] if rest else [])
    total = sum(values) or 1
    wedges, _ = ax.pie(values, colors=cols, startangle=90, counterclock=False,
                       wedgeprops={"width": 0.4, "edgecolor": "white", "linewidth": 1.5})
    ax.legend(wedges, [f"{n}  {v / total * 100:.0f}%" for n, v in zip(labels, values)], loc="center left",
              bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=8)
    fig.subplots_adjust(left=0.0, right=0.55, top=0.98, bottom=0.02)
    return fig


def export_monthly_pdf(statement: MonthlyStatement, path: Path, currency: Currency) -> Path:
    style = pdf_style(currency)
    st = _styles(style)
    title = f"Monthly Financial Report \u2013 {month_label(statement.month)}"
    doc = _doc(path, A4, title, style)
    w = doc.width
    m = style.money
    story = [_p("Monthly Financial Report", st["title"]), _p(month_label(statement.month), st["sub"]),
             Spacer(1, 12)]

    net_color = GREEN if statement.net >= 0 else RED
    story.append(_kpi_table([
        ("Total income", m(statement.income), GREEN), ("Total expenses", m(statement.expense), RED),
        ("Net savings", m(statement.net, signed=True), net_color),
        ("Opening balance", m(statement.opening_balance), INK), ("Closing balance", m(statement.closing_balance), INK),
        ("Savings rate", f"{statement.savings_rate:.1f}%", INDIGO)], w, st))

    story.append(_p("Income vs Expenses and Spending Distribution", st["h2"]))
    if any(p.income or p.expense for p in statement.series):
        left = _png(_income_expense_fig(statement.series), 8.6)
    else:
        left = _p("No income or expense activity in the last 6 months.", st["note"])
    right = _png(_distribution_fig(statement.expense_categories), 8.6) if statement.expense_categories \
        else _p("No expenses recorded this month.", st["note"])
    charts = Table([[left, right]], colWidths=[w / 2, w / 2])
    charts.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(charts)

    story.append(_p("Category-wise Expense Breakdown", st["h2"]))
    if statement.expense_categories:
        rows = [[c.name, str(statement.category_counts.get(c.category_id, 0)), m(c.amount),
                 f"{c.amount / statement.expense * 100:.1f}%"] for c in statement.expense_categories]
        story.append(_data_table(["Category", "Transactions", "Amount", "% of expenses"], rows, {1, 2, 3}, w, st, style,
                                 weights=[10, 5, 7, 6], total_row=["Total", "", m(statement.expense), "100.0%"]))
    else:
        story.append(_p("No expenses recorded for this month.", st["note"]))

    story.append(_p("Budget Performance", st["h2"]))
    ov = statement.budget
    lines = ([ov.overall] if ov.overall else []) + ov.categories
    if lines:
        rows = [[ln.name, m(ln.limit), m(ln.spent), m(ln.remaining), f"{round(ln.ratio * 100)}%",
                 "Over budget" if ln.over else ("Near limit" if ln.ratio >= 0.8 else "On track")] for ln in lines]
        story.append(_data_table(["Budget", "Limit", "Spent", "Remaining", "Used", "Status"], rows, {1, 2, 3, 4}, w, st,
                                 style, weights=[9, 6, 6, 6, 3.5, 5]))
    else:
        story.append(_p("No budgets were set for this month.", st["note"]))

    story.append(_p("Recent Transactions", st["h2"]))
    if statement.recent:
        rows = [[t.date, t.category, (t.description or "\u2014"), m(t.amount if t.type == "income" else -t.amount, True)]
                for t in statement.recent]
        story.append(_data_table(["Date", "Category", "Description", "Amount"], rows, {3}, w, st, style,
                                 weights=[4, 5, 10, 5]))
    else:
        story.append(_p("No transactions were recorded this month.", st["note"]))

    story.append(_p("Savings Goal Summary", st["h2"]))
    if statement.goals:
        rows = [[g.name, m(g.saved), m(g.target), f"{g.percent}%", "Completed" if g.completed else "In progress"]
                for g in statement.goals]
        story.append(_data_table(["Goal", "Saved", "Target", "Progress", "Status"], rows, {1, 2, 3}, w, st, style,
                                 weights=[9, 6, 6, 4, 5]))
    else:
        story.append(_p("No savings goals have been created yet.", st["note"]))

    doc.build(story, canvasmaker=_numbered_canvas(style, title))
    return Path(path)
