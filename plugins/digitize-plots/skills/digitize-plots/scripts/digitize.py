#!/usr/bin/env python3
"""digitize.py — extract (x, y) data from a plot image into CSV.

Thin, robust wrapper around the `plotdigitizer` CLI. Its job is to hide the two
footguns that otherwise silently corrupt the output:

  1. plotdigitizer int-truncates EVERY calibration coordinate (`geometry.Point`
     does `int(x)`). So a data value of 0.14 becomes 0 and 3.5 becomes 3 —
     collapsing an axis scale to zero (→ `inf`/`nan`) or rescaling it. We work
     around this by multiplying each data axis by a power of ten so the
     calibration values are integers, then dividing the result back down.

  2. plotdigitizer expects the calibration pixel y-coordinates in BOTTOM-origin
     (it computes `image_height - y` internally). We accept natural top-origin
     rows (what you read off an image viewer / what PIL/your eyes use) and flip
     them for you.

It also handles the common preprocessing: rendering a figure out of a PDF,
isolating a single colored data series (plotdigitizer traces one curve, so a
multi-series scatter must be reduced to one), and producing an overlay so you
can VISUALLY confirm the extraction landed on the data before trusting numbers.

Subcommands
-----------
  render   PDF page  -> PNG
  inspect  zoom the axis margins so calibration ticks can be read off
  extract  image + calibration -> CSV (+ optional overlay)

Run `python digitize.py <subcommand> -h` for details.

Dependencies: numpy, Pillow, and `plotdigitizer` (pip install plotdigitizer,
which pulls in opencv). `render` additionally uses PyMuPDF if present, else the
`pdftoppm` binary (poppler).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _int_scale(values, max_pow=6):
    """Smallest 10**k that turns every value into (near-)integer.

    e.g. [0, 3.5] -> 10 ; [0, 0.14] -> 100 ; [0, 12] -> 1.
    """
    for k in range(max_pow + 1):
        f = 10 ** k
        if all(abs(v * f - round(v * f)) < 1e-6 for v in values):
            return f
    return 10 ** max_pow


def _parse_color(spec, img):
    """Return an (R, G, B) target from 'R,G,B', '#rrggbb', or '@col,row' sample."""
    if spec.startswith("@"):
        col, row = (int(t) for t in spec[1:].split(","))
        return tuple(int(c) for c in np.array(img.convert("RGB"))[row, col][:3])
    if spec.startswith("#"):
        h = spec[1:]
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    return tuple(int(t) for t in spec.split(","))


def _isolate_color(img, target, tol, out_path):
    """Write a black-on-white image keeping only pixels within `tol` of target."""
    rgb = np.array(img.convert("RGB")).astype(int)
    diff = np.abs(rgb - np.array(target)).max(axis=2)
    mask = diff <= tol
    out = np.full(mask.shape, 255, np.uint8)
    out[mask] = 0
    Image.fromarray(out).save(out_path)
    return int(mask.sum())


# --------------------------------------------------------------------------- #
# render: PDF page -> PNG
# --------------------------------------------------------------------------- #
def render(args):
    out = args.output or f"page-{args.page}.png"
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(args.pdf)
        page = doc[args.page - 1]
        zoom = args.dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        pix.save(out)
    except ImportError:
        if not shutil.which("pdftoppm"):
            sys.exit("Need PyMuPDF (pip install pymupdf) or pdftoppm (poppler).")
        prefix = tempfile.mktemp()
        subprocess.run(
            ["pdftoppm", "-png", "-r", str(args.dpi),
             "-f", str(args.page), "-l", str(args.page), args.pdf, prefix],
            check=True,
        )
        produced = sorted(__import__("glob").glob(prefix + "*"))[0]
        shutil.move(produced, out)
    print(f"wrote {out}  ({Image.open(out).size[0]}x{Image.open(out).size[1]} px)")


# --------------------------------------------------------------------------- #
# inspect: zoom margins so ticks can be read off for calibration
# --------------------------------------------------------------------------- #
def inspect(args):
    img = Image.open(args.image).convert("RGB")
    W, H = img.size
    g = np.array(img.convert("L"))
    dark = g < 120

    def longest_run(vec):
        best = cur = 0
        for v in vec:
            cur = cur + 1 if v else 0
            best = max(best, cur)
        return best

    vrun = np.array([longest_run(dark[:, x]) for x in range(W)])
    hrun = np.array([longest_run(dark[y, :]) for y in range(H)])
    spine_cols = np.where(vrun > 0.5 * H)[0]
    spine_rows = np.where(hrun > 0.5 * W)[0]
    print(f"image {W}x{H}")
    print(f"candidate vertical spines  (x px): {[int(c) for c in spine_cols]}")
    print(f"candidate horizontal spines(y px): {[int(r) for r in spine_rows]}")

    # zoomed margin strips for visual tick reading
    base = os.path.splitext(os.path.basename(args.image))[0]
    bx = img.crop((0, max(0, H - args.margin), W, H)).resize((W * 2, args.margin * 2))
    by = img.crop((0, 0, args.margin, H)).resize((args.margin * 2, H * 2))
    bx.save(f"{base}_xaxis.png")
    by.save(f"{base}_yaxis.png")
    print(f"wrote {base}_xaxis.png and {base}_yaxis.png "
          f"(zoomed margins — read tick pixel positions off these, "
          f"or read them directly from the figure by eye)")


# --------------------------------------------------------------------------- #
# extract: image + calibration -> CSV
# --------------------------------------------------------------------------- #
def extract(args):
    img = Image.open(args.image)
    W, H = img.size
    src = args.image

    if args.color:
        target = _parse_color(args.color, img)
        tmp = tempfile.mktemp(suffix=".png")
        n = _isolate_color(img, target, args.tol, tmp)
        print(f"isolated color {target} (tol {args.tol}): {n} px -> {tmp}")
        src = tmp

    (x0, xpx0), (x1, xpx1) = args.xref
    (y0, yrow0), (y1, yrow1) = args.yref
    fx = _int_scale([x0, x1])
    fy = _int_scale([y0, y1])

    # Build plotdigitizer's 3 calibration points. Its x-fit and y-fit are
    # independent, so we only need x-data to vary across two of them and y-data
    # across two. Pixel y must be bottom-origin (H - row).
    def P(xd, yd):                       # data -> "-p X,Y" (integer-scaled)
        return f"{round(xd * fx)},{round(yd * fy)}"

    def L(px, row):                      # pixel -> "-l COL,BOTTOMROW"
        return f"{int(px)},{int(H - row)}"

    out = args.output or (os.path.splitext(args.image)[0] + ".csv")
    cmd = [
        sys.executable, "-m", "plotdigitizer.plotdigitizer", src,
        "-p", P(x0, y0), "-p", P(x1, y0), "-p", P(x0, y1),
        "-l", L(xpx0, yrow0), "-l", L(xpx1, yrow0), "-l", L(xpx0, yrow1),
        "-o", out,
    ]
    # `python -m plotdigitizer.plotdigitizer` may not be exposed; fall back to
    # the console script if the module entry point is missing.
    if not _module_runnable("plotdigitizer.plotdigitizer"):
        cmd[1:3] = []                    # drop "-m module"
        cmd[0] = shutil.which("plotdigitizer") or "plotdigitizer"
    subprocess.run(cmd, check=True)

    data = np.loadtxt(out)
    data = data[np.isfinite(data).all(axis=1)]
    data[:, 0] /= fx
    data[:, 1] /= fy
    data = data[np.argsort(data[:, 0])]
    np.savetxt(out, data, fmt="%.6g", delimiter=",", header="x,y", comments="")
    print(f"wrote {out}: {len(data)} points; "
          f"x in [{data[:,0].min():.4g}, {data[:,0].max():.4g}], "
          f"y in [{data[:,1].min():.4g}, {data[:,1].max():.4g}]")

    if args.overlay:
        _overlay(args.image, data, args.xref, args.yref, H, args.overlay)
        print(f"wrote {args.overlay} — open it and confirm the markers sit on "
              f"the data before trusting the numbers")


def _module_runnable(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def _overlay(image, data, xref, yref, H, out_path):
    """Map extracted data back to pixels and mark them on the original image."""
    (x0, xpx0), (x1, xpx1) = xref
    (y0, yrow0), (y1, yrow1) = yref
    sx = (xpx1 - xpx0) / (x1 - x0)
    sy = (yrow1 - yrow0) / (y1 - y0)
    im = Image.open(image).convert("RGB")
    dr = ImageDraw.Draw(im)
    for x, y in data:
        px = xpx0 + (x - x0) * sx
        row = yrow0 + (y - y0) * sy
        dr.line([px - 3, row, px + 3, row], fill=(0, 0, 0))
        dr.line([px, row - 3, px, row + 3], fill=(0, 0, 0))
    im.save(out_path)


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
def _ref(s):
    """Parse 'DATA:PIXEL' calibration pair, e.g. '3.5:784'."""
    d, p = s.split(":")
    return (float(d), float(p))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render a PDF page to PNG")
    r.add_argument("pdf")
    r.add_argument("--page", type=int, default=1)
    r.add_argument("--dpi", type=int, default=150)
    r.add_argument("-o", "--output")
    r.set_defaults(func=render)

    i = sub.add_parser("inspect", help="zoom axis margins to read calibration ticks")
    i.add_argument("image")
    i.add_argument("--margin", type=int, default=70,
                   help="margin thickness in px to crop+zoom (default 70)")
    i.set_defaults(func=inspect)

    e = sub.add_parser("extract", help="extract data points to CSV")
    e.add_argument("image")
    e.add_argument("--xref", type=_ref, nargs=2, required=True,
                   metavar="DATA:PIXEL",
                   help="two x-axis calibration points, e.g. --xref 0:420 3.5:784")
    e.add_argument("--yref", type=_ref, nargs=2, required=True,
                   metavar="DATA:ROW",
                   help="two y-axis calibration points (ROW = top-origin pixel "
                        "row), e.g. --yref 0:362 0.14:106")
    e.add_argument("--color",
                   help="isolate one series before tracing: 'R,G,B', '#hex', "
                        "or '@col,row' to sample the marker color from the image")
    e.add_argument("--tol", type=int, default=70,
                   help="per-channel color tolerance for --color (default 70)")
    e.add_argument("-o", "--output")
    e.add_argument("--overlay", help="write a verification overlay PNG")
    e.set_defaults(func=extract)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
