---
name: digitize-plots
description: Extract numeric (x, y) data points from a plot/figure image — including a figure inside a PDF — into a CSV, the CLI alternative to WebPlotDigitizer/automeris. Use whenever the user wants to "get the numbers off this plot", digitize/trace a curve, read data points from a chart or graph image, pull a dispersion/gap/curve out of a paper figure to compare against their own data, or recover tabular values from a figure when the underlying data isn't available. Triggers on phrases like "digitize this plot", "extract data from this figure/chart/graph", "read the points off", "get the curve from this PDF figure", "WebPlotDigitizer but from the command line".
---

# Digitize plots

Goal: turn a plotted curve in an image into numbers (a CSV of `x,y`), from the
command line. This is the scriptable counterpart to WebPlotDigitizer
(automeris.io), which is GUI-only.

The engine is the `plotdigitizer` CLI, but **always drive it through the bundled
`scripts/digitize.py` wrapper** rather than calling `plotdigitizer` directly.
The raw tool has two silent footguns that produce `inf`/`nan` or wrong-by-a-
factor output, and the wrapper hides both (see "Why the wrapper" below). The
wrapper also bundles the surrounding workflow — PDF rendering, color isolation,
and a verification overlay — so the whole job is two or three commands.

## Setup

```bash
pip install plotdigitizer numpy Pillow   # plotdigitizer pulls in opencv
# PDF rendering uses PyMuPDF if installed, else the `pdftoppm` binary (poppler)
```

Reference the script as `${CLAUDE_SKILL_DIR}/scripts/digitize.py`.

## Workflow

### 1. Get a clean PNG of the figure

If the figure is in a PDF, render the page and crop to just the plot (a tight
crop makes calibration and tracing far more reliable):

```bash
python ${CLAUDE_SKILL_DIR}/scripts/digitize.py render paper.pdf --page 3 --dpi 150 -o page.png
# then crop to the figure with PIL, or read the page image and crop the axes box
```

### 2. Find the calibration: data value ↔ pixel for two points per axis

You need two reference points on each axis, each as `DATA:PIXEL` — the data
value and where it sits in the image. **x pixels are columns; y pixels are
top-origin rows** (what an image viewer or PIL reports — the wrapper flips them
to the convention plotdigitizer wants).

Two ways to get the pixel positions, both fine:

- **Read them by eye.** Look at the figure (Read the PNG) and read off, e.g.,
  "the `Kℓ=0.0` tick is at about column 420, `Kℓ=3.5` at 784; `E=0.00` at row
  362, `E=0.14` at row 106." For most figures this is accurate enough.
- **Assist with `inspect`.** It prints candidate axis-spine pixel positions and
  writes zoomed margin strips so ticks are easy to read:
  ```bash
  python ${CLAUDE_SKILL_DIR}/scripts/digitize.py inspect fig.png
  ```

Pick tick marks that are far apart (e.g. first and last labeled tick) — a long
baseline minimizes calibration error.

### 3. Isolate ONE series if the plot is a multi-color scatter

`plotdigitizer` traces a single curve. If the figure overlays several series,
reduce it to one with `--color`, which keeps only pixels near a target color and
writes a black-on-white image internally. Give the color as `R,G,B`, `#hex`, or
`@col,row` to sample the marker color straight from the image:

```bash
--color '@470,150'      # sample whatever marker is at column 470, row 150
--color '200,40,40'     # or name the RGB directly (here: red)  --tol 80
```

A single clean curve needs no `--color`.

### 4. Extract, then VERIFY with the overlay

```bash
python ${CLAUDE_SKILL_DIR}/scripts/digitize.py extract fig.png \
  --xref 0:420 3.5:784 \
  --yref 0:362 0.14:106 \
  --color '200,40,40' --tol 80 \
  -o data.csv --overlay overlay.png
```

Then **read `overlay.png`** (it marks each extracted point on the original
figure) and confirm the crosshairs sit on the data. This catches calibration
mistakes immediately — do not report numbers without looking at the overlay.

## Why the wrapper (do not call `plotdigitizer` directly)

1. **It int-truncates every calibration coordinate.** `plotdigitizer`'s
   `geometry.Point` does `int(x)`, so a data value of `0.14` becomes `0` and
   `3.5` becomes `3`. A fractional axis silently collapses (scale → 0, output
   all `inf`) or rescales by the wrong factor. The wrapper multiplies each axis
   by a power of ten so calibration values are integers, then divides the result
   back down.
2. **Its calibration pixel-y is bottom-origin.** It internally computes
   `image_height - y`, so passing the natural top-origin row breaks the y-scale.
   The wrapper accepts top-origin rows and flips them for you.

Both bugs are silent — the tool emits a CSV either way — which is exactly why
the overlay verification in step 4 is mandatory.

## When NOT to use this — read the figure directly instead

For a quick one-off, or when you need the *lower envelope* across many overlaid
series (which a single-curve tracer cannot follow), it is faster and often just
as good to read the image yourself and report a handful of anchor points. In
practice the two approaches agree to within a percent or two of the axis range.
Reach for `plotdigitizer` when you need many dense points, a reproducible
script, or batch extraction over many similar figures.

For interactive, messy, or genuinely multi-dataset figures where you want to
click points, WebPlotDigitizer (automeris.io) in a browser remains the better
tool — it is just not CLI-driven.
