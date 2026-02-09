"""Generate Token Meter app icon as a macOS .icns file.

Creates a dark circle with a teal gauge arc — matching the app's
●/◐/○ menu bar theme. Requires Pillow.
"""

import os
import subprocess
import sys

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Installing Pillow...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "Pillow"])
    from PIL import Image, ImageDraw

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ICONSET_DIR = os.path.join(SCRIPT_DIR, "TokenMeter.iconset")
ICNS_PATH = os.path.join(SCRIPT_DIR, "icon.icns")

os.makedirs(ICONSET_DIR, exist_ok=True)


def draw_icon(size):
    """Draw a Token Meter icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = size * 0.05
    cx, cy = size / 2, size / 2
    outer_r = (size / 2) - margin

    # Dark background circle
    draw.ellipse(
        [cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r],
        fill=(30, 30, 35, 255),
    )

    # Subtle ring border
    ring_width = max(1, size // 64)
    draw.ellipse(
        [cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r],
        outline=(80, 80, 90, 255),
        width=ring_width,
    )

    # Inner gauge arc — teal/green accent (representing remaining capacity)
    arc_r = outer_r * 0.65
    arc_width = max(3, size // 16)
    bbox = [cx - arc_r, cy - arc_r, cx + arc_r, cy + arc_r]
    draw.arc(bbox, 0, 360, fill=(50, 50, 60, 255), width=arc_width)
    draw.arc(bbox, -90, 180, fill=(0, 200, 180, 255), width=arc_width)

    # Center dot
    dot_r = outer_r * 0.12
    draw.ellipse(
        [cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
        fill=(0, 200, 180, 255),
    )

    return img


def main():
    # Generate all required sizes for macOS iconset
    for base in [16, 32, 128, 256, 512]:
        draw_icon(base).save(os.path.join(ICONSET_DIR, f"icon_{base}x{base}.png"))
        draw_icon(base * 2).save(
            os.path.join(ICONSET_DIR, f"icon_{base}x{base}@2x.png")
        )

    print(f"Generated iconset at {ICONSET_DIR}")

    # Convert to .icns using macOS iconutil
    try:
        subprocess.run(
            ["iconutil", "--convert", "icns", ICONSET_DIR, "--output", ICNS_PATH],
            check=True,
        )
        print(f"Created {ICNS_PATH}")
    except FileNotFoundError:
        print("Warning: iconutil not found (requires macOS). Skipping .icns creation.")
        print("Run this script on macOS to generate the .icns file.")


if __name__ == "__main__":
    main()
