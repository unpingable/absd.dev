#!/usr/bin/env python3
"""Render the 1200x630 social preview card (src/static/og-card.png).

The terminal lines are verbatim from the RC1 outsider-agent trial (2026-10-18),
an SSH session against the published absd-preview-rc1 build. Rerun after
changing the copy: python3 -I scripts/make-og-card.py
"""
import pathlib
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "src/static/og-card.png"
FONTS = pathlib.Path("/usr/share/fonts/truetype/dejavu")

W, H = 1200, 630
BG = (27, 22, 34)          # plum-black
PANEL = (14, 12, 18)
CREAM = (238, 228, 205)
CORAL = (226, 128, 104)
TEAL = (86, 150, 152)
DIM = (150, 140, 128)

TRANSCRIPT = [
    ("$ ", "ssh -p 2222 -i ./absd-key operator@127.0.0.1"),
    ("absd$ ", "uname -a"),
    ("", "ABSD absd-rc1-c12c-20261018t161241z.fvcgzh x86_64 x86_64-unknown-absd pid=5"),
    ("absd$ ", "ps"),
    ("", "session 1 (this session), no terminal, connected 0 s"),
    ("", "  PID PROGRAM"),
    ("", "    4 /bin/absd-sh"),
    ("absd$ ", "uptime"),
    ("", "up 0 days 00:02:46, 166454 ticks since boot, boot 1ca5e0fb7a4ac056d204feee5e49209b"),
    ("absd$ ", "cat /home/operator/release-check.txt"),
    ("", "release-check"),
    ("absd$ ", ""),
]


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def main():
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # Trilobite, top right, framed.
    tri = Image.open(ROOT / "src/static/trilobite.jpg").convert("RGB")
    tw = 500
    th = round(tri.height * tw / tri.width)
    tri = tri.resize((tw, th), Image.LANCZOS)
    tx, ty = W - tw - 56, 48
    d.rectangle([tx - 4, ty - 4, tx + tw + 3, ty + th + 3], fill=CREAM)
    im.paste(tri, (tx, ty))

    # Wordmark and subtitle, top left.
    d.text((56, 30), "ABSD", font=font("DejaVuSansMono-Bold.ttf", 148), fill=CREAM)
    sub = font("DejaVuSans.ttf", 25)
    d.text((60, 206), "An experimental capability-based", font=sub, fill=CORAL)
    d.text((60, 240), "operating system", font=sub, fill=CORAL)
    d.text((60, 284), "absd.dev  ·  Developer Preview RC1", font=font("DejaVuSansMono.ttf", 18), fill=TEAL)

    # Terminal panel, bottom.
    px0, py0, px1, py1 = 56, 330, W - 56, H - 36
    d.rectangle([px0, py0, px1, py1], fill=PANEL, outline=(70, 60, 82), width=2)
    d.rectangle([px0, py0, px1, py0 + 26], fill=(44, 37, 54))
    d.text((px0 + 14, py0 + 5), "operator@absd  —  ssh", font=font("DejaVuSansMono.ttf", 14), fill=DIM)

    mono = font("DejaVuSansMono.ttf", 16)
    y = py0 + 38
    for prompt, text in TRANSCRIPT:
        x = px0 + 16
        if prompt:
            d.text((x, y), prompt, font=mono, fill=TEAL)
            x += d.textlength(prompt, font=mono)
            d.text((x, y), text, font=mono, fill=CREAM)
        else:
            d.text((x, y), text, font=mono, fill=DIM)
        if prompt == "absd$ " and not text:
            cx = x + d.textlength(text, font=mono)
            d.rectangle([cx, y + 2, cx + 9, y + 18], fill=CORAL)
        y += 19

    im.save(OUT, optimize=True)
    print(OUT, im.size, OUT.stat().st_size)


if __name__ == "__main__":
    main()
