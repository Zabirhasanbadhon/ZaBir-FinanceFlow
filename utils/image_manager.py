"""Pillow-powered asset generation: logo, icons, avatars and banners.

Every asset is drawn locally (supersampled for smooth edges), so the app never
depends on external image files. If an icon name is unknown the manager falls
back to a neutral placeholder instead of raising.
"""
from __future__ import annotations

import logging
import math
from typing import Callable

from PIL import Image, ImageDraw, ImageFont, ImageTk

from config import ICONS_DIR, IMAGES_DIR

log = logging.getLogger(__name__)

SS = 8  # supersampling factor for icons
RESAMPLE = Image.Resampling.LANCZOS

Color = tuple[int, int, int, int]


def _rgba(color: str, alpha: int = 255) -> Color:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha


# --------------------------------------------------------------------------- #
# Icon drawing primitives (24x24 design grid, scaled by ``u``)
# --------------------------------------------------------------------------- #
def _line(d: ImageDraw.ImageDraw, pts: list[tuple[float, float]], w: float, c: Color, u: float) -> None:
    pp = [(x * u, y * u) for x, y in pts]
    d.line(pp, fill=c, width=max(1, round(w * u)), joint="curve")
    r = w * u / 2
    for x, y in (pp[0], pp[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=c)


def _box(vals: tuple[float, float, float, float], u: float) -> list[float]:
    return [v * u for v in vals]


def _ic_dashboard(d, u, c):
    for b in ((3, 3, 10.5, 12), (13.5, 3, 21, 8.5), (13.5, 11.5, 21, 21), (3, 15, 10.5, 21)):
        d.rounded_rectangle(_box(b, u), radius=2 * u, fill=c)


def _ic_transactions(d, u, c):
    _line(d, [(4, 8), (19, 8)], 2, c, u)
    _line(d, [(15, 4), (19.5, 8), (15, 12)], 2, c, u)
    _line(d, [(20, 16), (5, 16)], 2, c, u)
    _line(d, [(9, 12), (4.5, 16), (9, 20)], 2, c, u)


def _ic_wallet(d, u, c):
    d.rounded_rectangle(_box((3, 6, 21, 20), u), radius=3 * u, outline=c, width=round(2 * u))
    _line(d, [(5, 6), (16, 3.5)], 2, c, u)
    d.ellipse(_box((14.4, 12.4, 17.6, 15.6), u), fill=c)


def _ic_categories(d, u, c):
    for y in (6, 12, 18):
        d.ellipse(_box((3.5, y - 1.6, 6.7, y + 1.6), u), fill=c)
        _line(d, [(10, y), (20.5, y)], 2, c, u)


def _ic_target(d, u, c):
    d.ellipse(_box((3, 3, 21, 21), u), outline=c, width=round(2 * u))
    d.ellipse(_box((7.3, 7.3, 16.7, 16.7), u), outline=c, width=round(2 * u))
    d.ellipse(_box((10.4, 10.4, 13.6, 13.6), u), fill=c)


def _ic_analytics(d, u, c):
    for b in ((4, 12, 8, 20), (10, 4, 14, 20), (16, 9, 20, 20)):
        d.rounded_rectangle(_box(b, u), radius=1.3 * u, fill=c)


def _ic_reports(d, u, c):
    d.rounded_rectangle(_box((5, 3, 19, 21), u), radius=2.5 * u, outline=c, width=round(2 * u))
    _line(d, [(8.6, 9), (15.4, 9)], 1.8, c, u)
    _line(d, [(8.6, 13), (15.4, 13)], 1.8, c, u)
    _line(d, [(8.6, 17), (12.4, 17)], 1.8, c, u)


def _ic_settings(d, u, c):
    cx = cy = 12 * u
    for i in range(8):
        a = math.pi / 4 * i
        d.line([(cx + math.cos(a) * 7 * u, cy + math.sin(a) * 7 * u),
                (cx + math.cos(a) * 10.2 * u, cy + math.sin(a) * 10.2 * u)],
               fill=c, width=round(3.4 * u))
    d.ellipse((cx - 8 * u, cy - 8 * u, cx + 8 * u, cy + 8 * u), fill=c)
    d.ellipse((cx - 3.3 * u, cy - 3.3 * u, cx + 3.3 * u, cy + 3.3 * u), fill=(0, 0, 0, 0))


def _ic_search(d, u, c):
    d.ellipse(_box((4, 4, 16.5, 16.5), u), outline=c, width=round(2.2 * u))
    _line(d, [(15, 15), (20, 20)], 2.4, c, u)


def _ic_bell(d, u, c):
    d.pieslice(_box((6, 3, 18, 15), u), 180, 360, fill=c)
    d.polygon([(6 * u, 9 * u), (18 * u, 9 * u), (20 * u, 17 * u), (4 * u, 17 * u)], fill=c)
    d.ellipse(_box((10.2, 17.6, 13.8, 21.2), u), fill=c)


def _ic_sun(d, u, c):
    d.ellipse(_box((7.6, 7.6, 16.4, 16.4), u), fill=c)
    for i in range(8):
        a = math.pi / 4 * i
        _line(d, [(12 + math.cos(a) * 7.4, 12 + math.sin(a) * 7.4),
                  (12 + math.cos(a) * 9.8, 12 + math.sin(a) * 9.8)], 2, c, u)


def _ic_moon(d, u, c):
    d.ellipse(_box((4, 4, 20, 20), u), fill=c)
    d.ellipse(_box((9.5, 1.5, 24, 16), u), fill=(0, 0, 0, 0))


def _ic_user(d, u, c):
    d.ellipse(_box((8, 3.5, 16, 11.5), u), fill=c)
    d.pieslice(_box((4, 13, 20, 29), u), 180, 360, fill=c)


def _ic_arrow_up(d, u, c):
    _line(d, [(12, 19), (12, 5)], 2.4, c, u)
    _line(d, [(6, 11), (12, 5), (18, 11)], 2.4, c, u)


def _ic_arrow_down(d, u, c):
    _line(d, [(12, 5), (12, 19)], 2.4, c, u)
    _line(d, [(6, 13), (12, 19), (18, 13)], 2.4, c, u)


def _ic_coin(d, u, c):
    for y in (3.5, 8.5, 13.5):
        d.ellipse(_box((5, y, 19, y + 7), u), outline=c, width=round(2 * u))


def _ic_pie(d, u, c):
    d.pieslice(_box((3, 3, 21, 21), u), 0, 270, fill=c)
    d.pieslice(_box((5.5, 0.5, 23.5, 18.5), u), 270, 360, fill=c)


def _ic_plus(d, u, c):
    _line(d, [(12, 5), (12, 19)], 2.4, c, u)
    _line(d, [(5, 12), (19, 12)], 2.4, c, u)


def _ic_check(d, u, c):
    _line(d, [(5, 12.5), (10, 17.5), (19, 7)], 2.6, c, u)


def _ic_calendar(d, u, c):
    d.rounded_rectangle(_box((3, 5, 21, 21), u), radius=3 * u, outline=c, width=round(2 * u))
    _line(d, [(3.5, 10.5), (20.5, 10.5)], 2, c, u)
    _line(d, [(8, 3), (8, 7)], 2, c, u)
    _line(d, [(16, 3), (16, 7)], 2, c, u)


def _ic_tag(d, u, c):
    d.polygon([(3 * u, 4 * u), (12 * u, 4 * u), (21 * u, 13 * u), (13 * u, 21 * u), (3 * u, 12 * u)], fill=c)
    d.ellipse(_box((6, 7, 9, 10), u), fill=(0, 0, 0, 0))


_ICONS: dict[str, Callable] = {
    "dashboard": _ic_dashboard, "transactions": _ic_transactions, "budgets": _ic_wallet,
    "wallet": _ic_wallet, "categories": _ic_categories, "savings": _ic_target,
    "target": _ic_target, "analytics": _ic_analytics, "reports": _ic_reports,
    "settings": _ic_settings, "search": _ic_search, "bell": _ic_bell, "sun": _ic_sun,
    "moon": _ic_moon, "user": _ic_user, "arrow_up": _ic_arrow_up, "arrow_down": _ic_arrow_down,
    "coin": _ic_coin, "pie": _ic_pie, "plus": _ic_plus, "check": _ic_check,
    "calendar": _ic_calendar, "tag": _ic_tag,
}


def _outline_box(d, u, c, box, r=2.5, w=2):
    d.rounded_rectangle(_box(box, u), radius=r * u, outline=c, width=round(w * u))


def _ic_briefcase(d, u, c):
    _outline_box(d, u, c, (3, 8, 21, 20))
    _line(d, [(9, 8), (9, 5.5), (15, 5.5), (15, 8)], 2, c, u)
    _line(d, [(3.5, 13.5), (20.5, 13.5)], 2, c, u)


def _ic_laptop(d, u, c):
    _outline_box(d, u, c, (5, 5, 19, 16), 2)
    _line(d, [(2.5, 19), (21.5, 19)], 2.6, c, u)


def _ic_store(d, u, c):
    d.polygon([(3 * u, 9 * u), (5.5 * u, 3.5 * u), (18.5 * u, 3.5 * u), (21 * u, 9 * u)], fill=c)
    _outline_box(d, u, c, (4.5, 10, 19.5, 20.5), 1.5)
    d.rectangle(_box((10, 14, 14, 20.5), u), fill=c)


def _ic_trending(d, u, c):
    _line(d, [(3, 17), (9, 11), (13, 15), (20.5, 7)], 2.4, c, u)
    _line(d, [(15, 6.5), (21, 6.5), (21, 12.5)], 2.4, c, u)


def _ic_gift(d, u, c):
    _outline_box(d, u, c, (4.5, 11, 19.5, 21), 1.5)
    d.rounded_rectangle(_box((3, 7, 21, 11.5), u), radius=1.2 * u, fill=c)
    _line(d, [(12, 7), (12, 21)], 2, c, u)
    d.arc(_box((6.5, 2.5, 12, 8), u), 130, 360, fill=c, width=round(1.8 * u))
    d.arc(_box((12, 2.5, 17.5, 8), u), 180, 50, fill=c, width=round(1.8 * u))


def _ic_plus_circle(d, u, c):
    d.ellipse(_box((3, 3, 21, 21), u), outline=c, width=round(2 * u))
    _line(d, [(12, 8), (12, 16)], 2, c, u)
    _line(d, [(8, 12), (16, 12)], 2, c, u)


def _ic_utensils(d, u, c):
    for x in (5, 8, 11):
        _line(d, [(x, 3), (x, 9)], 1.6, c, u)
    _line(d, [(5, 9), (11, 9)], 1.6, c, u)
    _line(d, [(8, 9), (8, 21)], 2, c, u)
    d.rounded_rectangle(_box((15, 3, 19, 13), u), radius=2 * u, fill=c)
    _line(d, [(17, 12), (17, 21)], 2, c, u)


def _ic_bus(d, u, c):
    _outline_box(d, u, c, (4, 3.5, 20, 18), 3)
    _line(d, [(4.5, 11), (19.5, 11)], 2, c, u)
    for x in (8, 16):
        d.ellipse(_box((x - 1.6, 18.4, x + 1.6, 21.6), u), fill=c)


def _ic_bag(d, u, c):
    _outline_box(d, u, c, (4.5, 8, 19.5, 21), 2.5)
    d.arc(_box((8.5, 2.5, 15.5, 13), u), 180, 360, fill=c, width=round(2 * u))


def _ic_home(d, u, c):
    _line(d, [(3, 12), (12, 3.5), (21, 12)], 2.2, c, u)
    _line(d, [(6, 10.5), (6, 20.5), (18, 20.5), (18, 10.5)], 2, c, u)


def _ic_book(d, u, c):
    _outline_box(d, u, c, (5, 3, 19, 21), 2.5)
    _line(d, [(9.5, 3.5), (9.5, 20.5)], 2, c, u)


def _ic_heart(d, u, c):
    d.ellipse(_box((3.2, 4, 12.6, 13.4), u), fill=c)
    d.ellipse(_box((11.4, 4, 20.8, 13.4), u), fill=c)
    d.polygon([(3.6 * u, 10.6 * u), (20.4 * u, 10.6 * u), (12 * u, 21 * u)], fill=c)


def _ic_film(d, u, c):
    _outline_box(d, u, c, (3, 5, 21, 19), 2.5)
    for x in (7.5, 16.5):
        _line(d, [(x, 5.5), (x, 18.5)], 1.8, c, u)
    for y in (9, 15):
        _line(d, [(3.5, y), (6, y)], 1.6, c, u)
        _line(d, [(18, y), (20.5, y)], 1.6, c, u)


def _ic_zap(d, u, c):
    d.polygon([(13.5 * u, 2 * u), (4.5 * u, 13.5 * u), (11 * u, 13.5 * u), (10 * u, 22 * u),
               (19.5 * u, 10 * u), (13 * u, 10 * u)], fill=c)


def _ic_plane(d, u, c):
    d.polygon([(21.5 * u, 2.5 * u), (2.5 * u, 10.5 * u), (9.5 * u, 13 * u), (12 * u, 20.5 * u)], fill=c)
    _line(d, [(9.5, 13), (21.5, 2.5)], 1.4, (0, 0, 0, 0), u)


def _ic_repeat(d, u, c):
    _line(d, [(5, 12), (5, 8), (19, 8)], 2, c, u)
    _line(d, [(16, 5), (19.5, 8), (16, 11)], 2, c, u)
    _line(d, [(19, 12), (19, 16), (5, 16)], 2, c, u)
    _line(d, [(8, 13), (4.5, 16), (8, 19)], 2, c, u)


def _ic_more(d, u, c):
    for x in (5.5, 12, 18.5):
        d.ellipse(_box((x - 1.8, 10.2, x + 1.8, 13.8), u), fill=c)


def _ic_edit(d, u, c):
    _line(d, [(8, 16), (17.5, 6.5)], 3.8, c, u)
    d.polygon([(4 * u, 20.5 * u), (5 * u, 15.5 * u), (9 * u, 19.5 * u)], fill=c)


def _ic_trash(d, u, c):
    _line(d, [(4, 7), (20, 7)], 2, c, u)
    _line(d, [(9, 7), (9, 4), (15, 4), (15, 7)], 2, c, u)
    _outline_box(d, u, c, (6, 8, 18, 21), 2.5)
    _line(d, [(10, 11.5), (10, 17.5)], 1.6, c, u)
    _line(d, [(14, 11.5), (14, 17.5)], 1.6, c, u)


def _ic_eye(d, u, c):
    d.ellipse(_box((2, 6, 22, 18), u), outline=c, width=round(2 * u))
    d.ellipse(_box((9, 9, 15, 15), u), fill=c)


def _ic_download(d, u, c):
    _line(d, [(12, 4), (12, 15)], 2.2, c, u)
    _line(d, [(7, 10.5), (12, 15.5), (17, 10.5)], 2.2, c, u)
    _line(d, [(5, 20), (19, 20)], 2.2, c, u)


def _ic_table(d, u, c):
    _outline_box(d, u, c, (3, 4, 21, 20), 2.5)
    _line(d, [(3.5, 10), (20.5, 10)], 1.8, c, u)
    _line(d, [(3.5, 15), (20.5, 15)], 1.8, c, u)
    _line(d, [(9.5, 4.5), (9.5, 19.5)], 1.8, c, u)


def _ic_folder(d, u, c):
    _line(d, [(3, 6.5), (9, 6.5), (11, 8.5), (21, 8.5), (21, 19), (3, 19), (3, 6.5)], 2, c, u)


def _ic_refresh(d, u, c):
    d.arc(_box((4, 4, 20, 20), u), 30, 320, fill=c, width=round(2.2 * u))
    _line(d, [(15.5, 3.5), (19.5, 6.5), (15.5, 9.5)], 2.2, c, u)


def _ic_x(d, u, c):
    _line(d, [(6, 6), (18, 18)], 2.4, c, u)
    _line(d, [(18, 6), (6, 18)], 2.4, c, u)


def _ic_chev_l(d, u, c):
    _line(d, [(15, 5), (8, 12), (15, 19)], 2.6, c, u)


def _ic_chev_r(d, u, c):
    _line(d, [(9, 5), (16, 12), (9, 19)], 2.6, c, u)


def _ic_filter(d, u, c):
    d.polygon([(3 * u, 5 * u), (21 * u, 5 * u), (14 * u, 13 * u), (14 * u, 20 * u), (10 * u, 18 * u),
               (10 * u, 13 * u)], fill=c)


def _ic_info(d, u, c):
    d.ellipse(_box((3, 3, 21, 21), u), outline=c, width=round(2 * u))
    _line(d, [(12, 11), (12, 17)], 2, c, u)
    d.ellipse(_box((10.8, 6.6, 13.2, 9), u), fill=c)


def _ic_minus(d, u, c):
    _line(d, [(5, 12), (19, 12)], 2.4, c, u)


_ICONS.update({
    "briefcase": _ic_briefcase, "laptop": _ic_laptop, "store": _ic_store, "trending-up": _ic_trending,
    "gift": _ic_gift, "plus-circle": _ic_plus_circle, "utensils": _ic_utensils, "bus": _ic_bus,
    "shopping-bag": _ic_bag, "home": _ic_home, "book": _ic_book, "heart": _ic_heart, "film": _ic_film,
    "zap": _ic_zap, "plane": _ic_plane, "repeat": _ic_repeat, "more-horizontal": _ic_more,
    "edit": _ic_edit, "trash": _ic_trash, "eye": _ic_eye, "download": _ic_download, "table": _ic_table,
    "folder": _ic_folder, "refresh": _ic_refresh, "x": _ic_x, "chevron-left": _ic_chev_l,
    "chevron-right": _ic_chev_r, "filter": _ic_filter, "info": _ic_info, "minus": _ic_minus,
})


def _load_font(size: int, bold: bool = True) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    names = (["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold
             else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def _gradient(size: tuple[int, int], c1: str, c2: str, horizontal: bool = False) -> Image.Image:
    mask = Image.linear_gradient("L")
    if horizontal:
        mask = mask.transpose(Image.Transpose.ROTATE_90)
    mask = mask.resize(size, RESAMPLE)
    return Image.composite(Image.new("RGBA", size, _rgba(c2)), Image.new("RGBA", size, _rgba(c1)), mask)


class ImageManager:
    """Generates and caches every bitmap used by the UI."""

    def __init__(self) -> None:
        self._photos: dict[tuple, ImageTk.PhotoImage] = {}
        self._pil_cache: dict[tuple, Image.Image] = {}

    # ---- icons --------------------------------------------------------- #
    def icon_image(self, name: str, size: int = 20, color: str = "#FFFFFF") -> Image.Image:
        key = ("icon", name, size, color)
        if key in self._pil_cache:
            return self._pil_cache[key]
        drawer = _ICONS.get(name)
        if drawer is None:
            log.warning("Unknown icon %r – using fallback", name)
            drawer = _ic_tag
        big = size * SS
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        drawer(ImageDraw.Draw(img), big / 24, _rgba(color))
        out = img.resize((size, size), RESAMPLE)
        self._pil_cache[key] = out
        return out

    def icon(self, name: str, size: int = 20, color: str = "#FFFFFF") -> ImageTk.PhotoImage:
        key = ("icon", name, size, color)
        if key not in self._photos:
            self._photos[key] = ImageTk.PhotoImage(self.icon_image(name, size, color))
        return self._photos[key]

    def circle_icon(self, name: str, size: int, bg: str, fg: str, outer: str | None = None) -> ImageTk.PhotoImage:
        """Icon centred on a filled circle (used for stat cards)."""
        key = ("circle", name, size, bg, fg)
        if key not in self._photos:
            big = size * 4
            base = Image.new("RGBA", (big, big), (0, 0, 0, 0))
            ImageDraw.Draw(base).ellipse((0, 0, big - 1, big - 1), fill=_rgba(bg))
            base = base.resize((size, size), RESAMPLE)
            glyph = self.icon_image(name, round(size * 0.5), fg)
            offset = (size - glyph.width) // 2
            base.alpha_composite(glyph, (offset, offset))
            self._photos[key] = ImageTk.PhotoImage(base)
        return self._photos[key]

    # ---- logo & avatar -------------------------------------------------- #
    def logo_image(self, size: int = 64) -> Image.Image:
        """Rounded gradient tile with three rising bars (last one in green)."""
        key = ("logo", size)
        if key in self._pil_cache:
            return self._pil_cache[key]
        big = size * 4
        tile = _gradient((big, big), "#6366F1", "#8B5CF6")
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.26, fill=255)
        tile.putalpha(mask)
        d = ImageDraw.Draw(tile)
        base_y, bar_w = big * 0.76, big * 0.15
        for i, (h, col) in enumerate(((0.28, (255, 255, 255, 235)), (0.42, (255, 255, 255, 235)),
                                      (0.58, (34, 197, 94, 255)))):
            x = big * (0.2 + i * 0.22)
            d.rounded_rectangle((x, base_y - big * h, x + bar_w, base_y), radius=bar_w * 0.4, fill=col)
        out = tile.resize((size, size), RESAMPLE)
        self._pil_cache[key] = out
        return out

    def logo(self, size: int = 36) -> ImageTk.PhotoImage:
        key = ("logo-photo", size)
        if key not in self._photos:
            self._photos[key] = ImageTk.PhotoImage(self.logo_image(size))
        return self._photos[key]

    def save_brand_assets(self) -> None:
        """Write logo PNG and Windows .ico to assets/ (best effort, optional)."""
        try:
            IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            ICONS_DIR.mkdir(parents=True, exist_ok=True)
            logo = self.logo_image(256)
            logo.save(IMAGES_DIR / "logo.png")
            logo.save(ICONS_DIR / "app.ico", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
        except Exception:
            log.warning("Could not save brand assets", exc_info=True)

    def avatar(self, initials: str, size: int = 38, c1: str = "#6366F1", c2: str = "#EC4899") -> ImageTk.PhotoImage:
        key = ("avatar", initials, size, c1, c2)
        if key not in self._photos:
            big = size * 4
            img = _gradient((big, big), c1, c2)
            mask = Image.new("L", (big, big), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
            img.putalpha(mask)
            d = ImageDraw.Draw(img)
            fnt = _load_font(round(big * 0.38))
            box = d.textbbox((0, 0), initials, font=fnt)
            d.text(((big - (box[2] - box[0])) / 2 - box[0], (big - (box[3] - box[1])) / 2 - box[1]),
                   initials, font=fnt, fill=(255, 255, 255, 255))
            self._photos[key] = ImageTk.PhotoImage(img.resize((size, size), RESAMPLE))
        return self._photos[key]

    # ---- decorative banner --------------------------------------------- #
    def banner_image(self, width: int, height: int, c1: str, c2: str, radius: int = 20) -> Image.Image:
        """Gradient banner with soft circles and a small rising-chart illustration."""
        width, height = max(width, 80), max(height, 60)
        s = 2
        w, h = width * s, height * s
        img = _gradient((w, h), c1, c2, horizontal=True)
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.ellipse((w * 0.70, -h * 0.9, w * 1.12, h * 0.75), fill=(255, 255, 255, 26))
        od.ellipse((w * 0.58, h * 0.35, w * 0.86, h * 1.35), fill=(255, 255, 255, 18))
        od.ellipse((-w * 0.05, h * 0.7, w * 0.16, h * 1.5), fill=(255, 255, 255, 16))

        # mini bar chart + trend line (right side)
        cx0, cx1 = w * 0.77, w * 0.95
        base = h * 0.82
        heights = (0.28, 0.4, 0.34, 0.52, 0.66)
        slot = (cx1 - cx0) / len(heights)
        pts = []
        for i, hh in enumerate(heights):
            x0 = cx0 + i * slot
            od.rounded_rectangle((x0, base - h * hh, x0 + slot * 0.55, base),
                                 radius=slot * 0.15, fill=(255, 255, 255, 70 + i * 22))
            pts.append((x0 + slot * 0.27, base - h * hh - h * 0.09))
        od.line(pts, fill=(255, 255, 255, 230), width=max(2, round(h * 0.022)), joint="curve")
        for x, y in pts:
            r = h * 0.022
            od.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 255))
        img.alpha_composite(overlay)

        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius * s, fill=255)
        img.putalpha(mask)
        return img.resize((width, height), RESAMPLE)
