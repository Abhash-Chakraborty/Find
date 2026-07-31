#!/usr/bin/env python3
"""
Generate synthetic OCR test images for scripts/ocr_test_images/.

This is a stand-in for real photos/screenshots/receipts, meant to make
benchmark_ocr_variants.py's accuracy comparison meaningful even without
access to real device photos. It is NOT a substitute for real samples --
replace these with real photos/screenshots/receipts before treating the
benchmark's accuracy numbers as final, per the issue's acceptance criteria.

Each generated image's ground-truth text is embedded in its filename
(e.g. "gt_ASPIRIN_500MG.png") so a human (or a future accuracy script) can
compare OCR output against a known-correct answer.

Run with: uv run python scripts/generate_test_images.py
"""

import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Reproducible output. Both generators need seeding: `random` drives line
# sampling and rotation angles, numpy drives the per-pixel sensor noise in
# add_noise(), so seeding only `random` would still give a different corpus
# (and different accuracy numbers) on every regeneration.
random.seed(42)
_rng = np.random.default_rng(42)

OUT_DIR = Path(__file__).parent / "ocr_test_images"

SAMPLE_LINES = [
    "PARACETAMOL 500MG",
    "AMOXICILLIN 250MG",
    "IBUPROFEN 400MG TABLETS",
    "CETIRIZINE 10MG",
    "METFORMIN 500MG SR",
    "AZITHROMYCIN 500MG",
    "OMEPRAZOLE 20MG CAPSULES",
    "VITAMIN D3 60000 IU",
]


def _font(size):
    """Load a system TrueType font or fall back to default with the given size."""
    for name in ("arial.ttf", "DejaVuSans.ttf", "calibri.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default(size=size)


def add_noise(img: Image.Image, amount: float) -> Image.Image:
    """Add per-pixel random noise to simulate camera sensor grain."""
    arr = np.array(img).astype(np.int16)
    noise = _rng.integers(-int(255 * amount), int(255 * amount) + 1, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def make_photo(text: str) -> Image.Image:
    """Simulate an angled phone photo: uneven lighting, blur, grain."""
    img = Image.new("RGB", (700, 260), color=(235, 232, 225))
    draw = ImageDraw.Draw(img)
    draw.text((40, 100), text, fill=(20, 20, 25), font=_font(34))
    # Uneven lighting: darken one corner
    overlay = Image.new("L", img.size, 0)
    odraw = ImageDraw.Draw(overlay)
    odraw.ellipse((-200, -200, 300, 300), fill=60)
    img = Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, overlay)
    img = img.filter(ImageFilter.GaussianBlur(radius=1.1))
    img = add_noise(img, 0.03)
    return img


def make_screenshot(text: str) -> Image.Image:
    """Simulate a clean app/UI screenshot: crisp text, flat background."""
    img = Image.new("RGB", (700, 220), color=(250, 250, 252))
    draw = ImageDraw.Draw(img)
    draw.rectangle((20, 20, 680, 200), outline=(210, 210, 215), width=2)
    draw.text((40, 90), text, fill=(30, 30, 35), font=_font(30))
    return img


def make_receipt(text: str) -> Image.Image:
    """Simulate a thermal-printer receipt: grainy, monospace, tall/narrow."""
    lines = [text, "QTY: 1   MRP: 45.00", "BATCH: A1234   EXP: 12/27"]
    img = Image.new("RGB", (420, 280), color=(245, 245, 240))
    draw = ImageDraw.Draw(img)
    y = 40
    for line in lines:
        draw.text((20, y), line, fill=(15, 15, 15), font=_font(22))
        y += 45
    img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
    img = add_noise(img, 0.05)
    return img


def make_rotated(text: str) -> Image.Image:
    """Simulate a tilted photo (common when scanning strips by hand)."""
    base = make_photo(text)
    angle = random.choice([-25, -15, 12, 20, 30])
    return base.rotate(angle, expand=True, fillcolor=(235, 232, 225))


def make_low_contrast(text: str) -> Image.Image:
    """Simulate faded/worn print or a bad-lighting photo: low text/bg contrast."""
    img = Image.new("RGB", (700, 220), color=(210, 210, 205))
    draw = ImageDraw.Draw(img)
    draw.text((40, 90), text, fill=(175, 175, 170), font=_font(30))
    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    return img


GENERATORS = {
    "photos": make_photo,
    "screenshots": make_screenshot,
    "receipts": make_receipt,
    "rotated": make_rotated,
    "low_contrast": make_low_contrast,
}


def safe_filename(text: str) -> str:
    """Format ground-truth text into a valid, safe filename string."""
    return "gt_" + text.replace(" ", "_").replace("/", "-")


def main():
    """Generate synthetic test image categories and write them to disk."""
    for category, generator in GENERATORS.items():
        cat_dir = OUT_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        # Clear any old generated samples so re-runs don't accumulate stale files
        for old in cat_dir.glob("gt_*.png"):
            old.unlink()

        lines = random.sample(SAMPLE_LINES, k=4)
        for text in lines:
            img = generator(text)
            out_path = cat_dir / f"{safe_filename(text)}.png"
            img.save(out_path)
            print(f"  Wrote {out_path.relative_to(OUT_DIR.parent)}")

    print(f"\nDone. {len(GENERATORS) * 4} synthetic images written under {OUT_DIR}")
    print(
        "Ground truth is embedded in each filename (gt_<EXPECTED_TEXT>.png). "
        "Replace with real photos before finalizing accuracy conclusions."
    )


if __name__ == "__main__":
    main()
