"""Matplotlib chart builders (theme-aware) and the Tk host widget."""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable, Sequence

import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from ui.theme import Palette
from utils.helpers import compact_number

matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = ["Segoe UI", "Nirmala UI", "Arial", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)


class ChartView(tk.Frame):
    """Embeds a Matplotlib figure; ``builder(fig, palette)`` draws into it."""

    def __init__(self, parent: tk.Misc, p: Palette, builder: Callable[[Figure, Palette], None], *,
                 height: int = 250) -> None:
        super().__init__(parent, bg=p.card)
        self.figure = Figure(figsize=(5, height / 100), dpi=100, facecolor=p.card)
        builder(self.figure, p)
        self._canvas = FigureCanvasTkAgg(self.figure, master=self)
        widget = self._canvas.get_tk_widget()
        widget.configure(width=10, height=height, bg=p.card, highlightthickness=0, bd=0)
        widget.pack(fill="both", expand=True)


def _style_axes(ax, p: Palette) -> None:
    ax.set_facecolor(p.card)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(p.border)
    ax.tick_params(colors=p.text_muted, labelsize=8, length=0)
    ax.grid(axis="y", color=p.border, linewidth=0.7, alpha=0.9)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: compact_number(v)))


def income_expense_chart(fig: Figure, p: Palette, labels: Sequence[str],
                         income: Sequence[float], expense: Sequence[float], annotate: bool = False) -> None:
    """Grouped bars of income vs. expense per month (values in major units)."""
    ax = fig.add_subplot(111)
    _style_axes(ax, p)
    width = 0.36
    xs = list(range(len(labels)))
    ax.bar([x - width / 2 for x in xs], income, width, color=p.secondary, label="Income", zorder=3)
    ax.bar([x + width / 2 for x in xs], expense, width, color=p.danger, label="Expenses", zorder=3)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    if annotate:
        for x, v in zip(xs, income):
            if v:
                ax.text(x - width / 2, v, compact_number(v), ha="center", va="bottom", fontsize=7, color=p.text_muted)
        for x, v in zip(xs, expense):
            if v:
                ax.text(x + width / 2, v, compact_number(v), ha="center", va="bottom", fontsize=7, color=p.text_muted)
    ax.legend(frameon=False, fontsize=8, labelcolor=p.text_muted, loc="upper left", ncol=2,
              bbox_to_anchor=(0, 1.14))
    fig.subplots_adjust(left=0.1, right=0.98, top=0.86, bottom=0.12)


def donut_chart(fig: Figure, p: Palette, labels: Sequence[str], values: Sequence[float],
                colors: Sequence[str], center_text: str) -> None:
    """Donut with the total in the middle and a legend showing each share."""
    ax = fig.add_subplot(111)
    total = sum(values) or 1
    wedges, _ = ax.pie(values, colors=colors, startangle=90, counterclock=False,
                       wedgeprops={"width": 0.38, "edgecolor": p.card, "linewidth": 2})
    ax.text(0, 0.07, center_text, ha="center", va="center", fontsize=11, fontweight="bold", color=p.text)
    ax.text(0, -0.17, "spent", ha="center", va="center", fontsize=8, color=p.text_muted)
    legend_labels = [f"{name}  {v / total * 100:.0f}%" for name, v in zip(labels, values)]
    ax.legend(wedges, legend_labels, loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False,
              fontsize=8, labelcolor=p.text, handlelength=1, handleheight=1)
    fig.subplots_adjust(left=0.01, right=0.60, top=0.97, bottom=0.03)


def spending_trend_chart(fig: Figure, p: Palette, days: int, current: Sequence[float],
                         previous: Sequence[float] | None, current_label: str,
                         previous_label: str) -> None:
    """Cumulative spending through the month, optionally against the previous month."""
    ax = fig.add_subplot(111)
    _style_axes(ax, p)
    if previous:
        ax.plot(range(1, len(previous) + 1), previous, color=p.text_muted, linewidth=1.4,
                linestyle="--", label=previous_label, zorder=2)
    xs = list(range(1, len(current) + 1))
    ax.plot(xs, current, color=p.primary, linewidth=2.4, label=current_label, zorder=4)
    ax.fill_between(xs, current, color=p.primary, alpha=0.16, zorder=3)
    ax.set_xlim(1, max(days, 2))
    ax.set_ylim(bottom=0)
    ax.set_xticks([d for d in range(1, days + 1) if d == 1 or d % 5 == 0])
    ax.legend(frameon=False, fontsize=8, labelcolor=p.text_muted, loc="upper left", ncol=2,
              bbox_to_anchor=(0, 1.14))
    fig.subplots_adjust(left=0.1, right=0.98, top=0.86, bottom=0.12)


def savings_trend_chart(fig: Figure, p: Palette, labels: Sequence[str], net: Sequence[float]) -> None:
    """Net savings (income - expenses) per month as a line with markers."""
    ax = fig.add_subplot(111)
    _style_axes(ax, p)
    xs = list(range(len(labels)))
    ax.axhline(0, color=p.text_muted, linewidth=0.8)
    ax.plot(xs, net, color=p.secondary, linewidth=2.4, marker="o", markersize=5, zorder=4)
    ax.fill_between(xs, net, 0, where=[v >= 0 for v in net], color=p.secondary, alpha=0.15, zorder=3, interpolate=True)
    ax.fill_between(xs, net, 0, where=[v < 0 for v in net], color=p.danger, alpha=0.18, zorder=3, interpolate=True)
    if len(xs) <= 12:
        for x, v in zip(xs, net):
            ax.annotate(compact_number(v), (x, v), textcoords="offset points", xytext=(0, 8), ha="center",
                        fontsize=7, color=p.text_muted)
    step = max(1, len(xs) // 12)
    ax.set_xticks(xs[::step])
    ax.set_xticklabels(list(labels)[::step])
    ax.margins(x=0.04, y=0.18)
    fig.subplots_adjust(left=0.1, right=0.98, top=0.92, bottom=0.12)


def hbar_chart(fig: Figure, p: Palette, labels: Sequence[str], values: Sequence[float],
               colors: Sequence[str], value_labels: Sequence[str]) -> None:
    """Horizontal bars (largest on top) with a text label at the end of each bar."""
    ax = fig.add_subplot(111)
    ax.set_facecolor(p.card)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ys = list(range(len(labels)))
    ax.barh(ys, values, color=colors, height=0.62, zorder=3)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=8, color=p.text)
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.tick_params(length=0)
    top = max(values) if values else 1
    for y, v, text in zip(ys, values, value_labels):
        ax.text(v + top * 0.02, y, text, va="center", fontsize=8, color=p.text_muted)
    ax.set_xlim(0, top * 1.28)
    fig.subplots_adjust(left=0.24, right=0.98, top=0.97, bottom=0.03)


def daily_bars_chart(fig: Figure, p: Palette, labels: Sequence[str], values: Sequence[float]) -> None:
    """Spending per day (or per week for long ranges)."""
    ax = fig.add_subplot(111)
    _style_axes(ax, p)
    xs = list(range(len(values)))
    peak = max(values) if values else 0
    ax.bar(xs, values, color=[p.danger if v == peak and v > 0 else p.primary for v in values], width=0.72, zorder=3)
    step = max(1, len(xs) // 10)
    ax.set_xticks(xs[::step])
    ax.set_xticklabels(list(labels)[::step], fontsize=7)
    fig.subplots_adjust(left=0.1, right=0.98, top=0.95, bottom=0.14)


def budget_utilization_chart(fig: Figure, p: Palette, labels: Sequence[str], ratios: Sequence[float]) -> None:
    """Percent of each budget used; bars past 100% turn red and the limit is marked."""
    ax = fig.add_subplot(111)
    ax.set_facecolor(p.card)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(p.border)
    pct = [r * 100 for r in ratios]
    colors = [p.danger if v > 100 else (p.warning if v >= 80 else p.primary) for v in pct]
    ys = list(range(len(labels)))
    ax.barh(ys, pct, color=colors, height=0.55, zorder=3)
    ax.axvline(100, color=p.text_muted, linewidth=1, linestyle="--", zorder=4)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=8, color=p.text)
    ax.invert_yaxis()
    ax.tick_params(axis="x", colors=p.text_muted, labelsize=8, length=0)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v:.0f}%"))
    ax.grid(axis="x", color=p.border, linewidth=0.6)
    ax.set_axisbelow(True)
    for y, v in zip(ys, pct):
        ax.text(v + 2, y, f"{v:.0f}%", va="center", fontsize=8, color=p.text_muted)
    ax.set_xlim(0, max(120, max(pct, default=0) + 25))
    fig.subplots_adjust(left=0.2, right=0.97, top=0.96, bottom=0.14)
