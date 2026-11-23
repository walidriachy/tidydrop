"""The app icon, drawn in code so no image files are needed at runtime."""
from __future__ import annotations

from PIL import Image, ImageDraw

BLUE = (37, 99, 235, 255)
GREY = (107, 114, 128, 255)
WHITE = (255, 255, 255, 255)


def make_icon(size: int = 64, paused: bool = False) -> Image.Image:
    big = size * 4  # draw large, then shrink for smooth edges
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    s = big
    draw.rounded_rectangle([s * 0.04, s * 0.04, s * 0.96, s * 0.96], radius=s * 0.22, fill=GREY if paused else BLUE)
    draw.rectangle([s * 0.42, s * 0.16, s * 0.58, s * 0.50], fill=WHITE)                     # arrow shaft
    draw.polygon([(s * 0.25, s * 0.45), (s * 0.75, s * 0.45), (s * 0.50, s * 0.70)], fill=WHITE)  # arrow head
    draw.rounded_rectangle([s * 0.20, s * 0.75, s * 0.80, s * 0.85], radius=s * 0.04, fill=WHITE)  # tray
    if paused:
        draw.rectangle([s * 0.64, s * 0.08, s * 0.72, s * 0.30], fill=WHITE)
        draw.rectangle([s * 0.78, s * 0.08, s * 0.86, s * 0.30], fill=WHITE)
    return image.resize((size, size), Image.Resampling.LANCZOS)
