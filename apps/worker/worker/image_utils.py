"""
Image utilities for thumbnail generation.

Provides placeholder image creation and text overlay using Pillow.
All functions work on raw bytes so they integrate cleanly with S3 upload.
"""
from __future__ import annotations

import io
import textwrap
from typing import Any

_THUMB_W = 1280
_THUMB_H = 720


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def create_placeholder_image(color_scheme: dict[str, Any]) -> bytes:
    """Create a 1280×720 PNG from a ColorScheme dict (no Pillow fonts needed)."""
    from PIL import Image, ImageDraw

    bg = _hex_to_rgb(color_scheme.get("background", "#1A1A1A"))
    primary = _hex_to_rgb(color_scheme.get("primary", "#2D2D2D"))
    accent = _hex_to_rgb(color_scheme.get("accent", "#F7B731"))

    img = Image.new("RGB", (_THUMB_W, _THUMB_H), bg)
    draw = ImageDraw.Draw(img)

    # Gradient bands to give depth
    for i in range(_THUMB_H):
        ratio = i / _THUMB_H
        r = int(bg[0] + (primary[0] - bg[0]) * ratio * 0.4)
        g = int(bg[1] + (primary[1] - bg[1]) * ratio * 0.4)
        b = int(bg[2] + (primary[2] - bg[2]) * ratio * 0.4)
        draw.line([(0, i), (_THUMB_W, i)], fill=(r, g, b))

    # Accent strip at top
    draw.rectangle([(0, 0), (_THUMB_W, 12)], fill=accent)
    # Accent strip at bottom
    draw.rectangle([(0, _THUMB_H - 12), (_THUMB_W, _THUMB_H)], fill=accent)
    # Subtle vertical accent bar on left
    draw.rectangle([(0, 12), (8, _THUMB_H - 12)], fill=accent)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def overlay_text(
    image_bytes: bytes,
    headline: str,
    sub_text: str | None,
    color_scheme: dict[str, Any],
    layout: str = "bold_text",
) -> bytes:
    """Overlay headline and optional sub_text onto an image."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)

    text_color = _hex_to_rgb(color_scheme.get("text", "#FFFFFF"))
    accent_color = _hex_to_rgb(color_scheme.get("accent", "#F7B731"))

    w, h = img.size

    # Load font — fall back to default if no system font available
    headline_size = _pick_font_size(headline, w, layout)
    try:
        from PIL import ImageFont
        font_headline = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", headline_size)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(headline_size // 3, 28))
    except (OSError, IOError):
        font_headline = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    if layout == "split_layout":
        _draw_split(draw, headline, sub_text, font_headline, font_sub, text_color, accent_color, w, h)
    else:
        _draw_centered(draw, headline, sub_text, font_headline, font_sub, text_color, accent_color, w, h)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def _pick_font_size(text: str, width: int, layout: str) -> int:
    available_width = width * (0.45 if layout == "split_layout" else 0.85)
    chars = max(len(text), 1)
    # Rough estimate: each char at size N is ~0.55*N wide
    size = int(available_width / (chars * 0.55))
    return max(48, min(size, 160))


def _draw_centered(draw, headline, sub_text, font_h, font_s, text_color, accent_color, w, h):
    # Drop shadow for readability
    _draw_text_with_shadow(draw, headline, font_h, text_color, w // 2, h // 2 - 40, anchor="mm")
    if sub_text:
        _draw_text_with_shadow(draw, sub_text, font_s, accent_color, w // 2, h // 2 + 80, anchor="mm")


def _draw_split(draw, headline, sub_text, font_h, font_s, text_color, accent_color, w, h):
    # Text block on left half
    x_center = w // 4
    _draw_text_with_shadow(draw, headline, font_h, text_color, x_center, h // 2 - 30, anchor="mm")
    if sub_text:
        _draw_text_with_shadow(draw, sub_text, font_s, accent_color, x_center, h // 2 + 70, anchor="mm")


def _draw_text_with_shadow(draw, text: str, font, color, x, y, anchor="mm"):
    shadow_offset = 3
    shadow_color = (0, 0, 0)
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color, anchor=anchor)
    draw.text((x, y), text, font=font, fill=color, anchor=anchor)
