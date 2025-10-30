import os
from typing import Tuple
from PIL import Image, ImageDraw


def _draw_crescent(draw: ImageDraw.ImageDraw, center: Tuple[int, int], outer_r: int, thickness: int, color_outer: Tuple[int, int, int, int], color_inner: Tuple[int, int, int, int]):
    cx, cy = center
    # Outer circle (full moon)
    draw.ellipse((cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r), fill=color_outer)
    # Inner circle to carve crescent
    offset = int(outer_r * 0.45)
    inner_r = outer_r - thickness
    draw.ellipse((cx - inner_r + offset, cy - inner_r, cx + inner_r + offset, cy + inner_r), fill=color_inner)


def _draw_star(draw: ImageDraw.ImageDraw, center: Tuple[int, int], r: int, fill: Tuple[int, int, int, int]):
    cx, cy = center
    # Simple 4-point star
    draw.line((cx - r, cy, cx + r, cy), fill=fill, width=2)
    draw.line((cx, cy - r, cx, cy + r), fill=fill, width=2)


def generate_tray_icon(path: str, size: int = 64) -> str:
    """Generate a nicer tray icon (night sky with crescent and stars) and save to file.

    Args:
        path: Absolute path to save the PNG icon.
        size: Width/height in pixels (square icon).

    Returns:
        The path for convenience.
    """
    width = height = size
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Background gradient (radial-like via concentric circles)
    bg_center = (width // 2, height // 2)
    max_r = min(bg_center)
    for i in range(max_r, 0, -1):
        t = i / max_r
        r = int(18 + 10 * (1 - t))
        g = int(24 + 12 * (1 - t))
        b = int(38 + 20 * (1 - t))
        a = 255
        draw.ellipse((bg_center[0] - i, bg_center[1] - i, bg_center[0] + i, bg_center[1] + i), fill=(r, g, b, a))

    # Glow ring
    ring_r = int(max_r * 0.95)
    draw.ellipse((bg_center[0] - ring_r, bg_center[1] - ring_r, bg_center[0] + ring_r, bg_center[1] + ring_r), outline=(80, 110, 200, 100), width=2)

    # Crescent moon
    crescent_r = int(size * 0.28)
    _draw_crescent(
        draw,
        center=(int(width * 0.60), int(height * 0.45)),
        outer_r=crescent_r,
        thickness=int(crescent_r * 0.55),
        color_outer=(240, 240, 255, 255),
        color_inner=(0, 0, 0, 0),
    )

    # Stars
    star_color = (250, 250, 255, 230)
    _draw_star(draw, (int(width * 0.28), int(height * 0.30)), r=3, fill=star_color)
    _draw_star(draw, (int(width * 0.38), int(height * 0.55)), r=2, fill=star_color)
    _draw_star(draw, (int(width * 0.20), int(height * 0.55)), r=2, fill=star_color)
    _draw_star(draw, (int(width * 0.48), int(height * 0.25)), r=2, fill=star_color)

    # Ensure directory exists and save
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.save(path, format='PNG')
    return path


