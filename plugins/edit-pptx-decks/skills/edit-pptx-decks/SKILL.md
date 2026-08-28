---
name: edit-pptx-decks
description: Edit, polish, and audit PowerPoint .pptx decks programmatically — reposition and align shapes, swap or regenerate figures, unify fonts and sizes, insert native OMML equations, and catch the defects that only appear once PowerPoint opens the file. Use whenever the user asks to fix a slide's layout, replace a figure in a deck, align or resize elements, add page numbers, "make this slide look better", audit a deck before a talk, or debug something that "looks fine here but is broken/distorted in PowerPoint". Triggers on phrases like "fix the layout on slide N", "replace this image in the pptx", "align these elements", "the logo is distorted in PowerPoint", "check the deck before I present", "add an equation to this slide".
---

# Edit PowerPoint decks

Editing a `.pptx` well is mostly about a **render-and-verify loop**, because
neither `python-pptx` nor your intuition tells you what the slide looks like.
The loop is: change one thing → render → look at the pixels → measure → repeat.

Everything below is written for that loop. `scripts/pptx_tools.py` bundles the
parts that are fiddly to redo by hand.

```bash
pip install python-pptx pillow pymupdf lxml fonttools
# rendering needs LibreOffice (macOS: /Applications/LibreOffice.app)
```

## The loop

```bash
S=${CLAUDE_SKILL_DIR}/scripts/pptx_tools.py
python $S audit  deck.pptx                       # before you touch anything
python $S render deck.pptx --pages 2,3 --out /tmp/r --width 1500
# ... edit ...
python $S render deck.pptx --pages 2 --out /tmp/r
```

Then **read the PNG**, and measure rather than eyeball: PyMuPDF gives you the
real geometry of everything on the page, in centimetres.

```python
import fitz
d = fitz.open("/tmp/r/_proxy.pdf"); p = d[1]          # 0-based
S = p.rect.width / 33.87                              # px per cm for a 16:9 deck
for b in p.get_text("dict")["blocks"]:
    if b["type"] == 0:
        x0, y0, x1, y1 = [v / S for v in b["bbox"]]
        print(f"{x0:.2f}-{x1:.2f}  {y0:.2f}-{y1:.2f}  "
              f"{''.join(s['text'] for l in b['lines'] for s in l['spans'])[:30]!r}")
for im in p.get_images(full=True):
    for r in p.get_image_rects(im[0]):
        print(f"image  x {r.x0/S:.2f}-{r.x1/S:.2f}  y {r.y0/S:.2f}-{r.y1/S:.2f}")
```

This is how you find the *real* free space on a slide. A picture's frame is
usually bigger than its ink — a figure with white margins can start 0.4 cm
below the top of its box — so laying out against `shape.top` alone produces
gaps that look wrong and collisions that look fine.

## What the preview cannot tell you

The renderer is LibreOffice, and it disagrees with PowerPoint in specific ways.
Know them, or you will "fix" things that were never broken and ship things that
are.

**Fonts live in two different worlds.** PowerPoint additionally loads fonts
Microsoft ships *inside its own app bundles* — Cambria Math, Microsoft YaHei,
Arial (`/Applications/Microsoft*.app/Contents/Resources/DFonts`). LibreOffice
sees only system-registered fonts. So a deck that renders with square boxes or
Latin fallbacks in your preview may be perfect on the presenter's machine, and
a font your audit calls "present" may still be missing for the preview.
`render` substitutes using the *system* set and `audit` reports using the
*PowerPoint* set; keep that distinction if you roll your own.

**LibreOffice ignores OMML run properties entirely.** Font and size on
`<m:r><a:rPr sz="1800">` have no effect — equations render at LibreOffice's own
default, at its own width. You cannot size or position an equation from the
preview. Measure it with TeX metrics instead and place it analytically:

```python
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams["mathtext.fontset"] = "cm"
fig = plt.figure(); r = fig.canvas.get_renderer()
t = fig.text(0, 0, r"$\hat H=-\sum_i\frac{\nabla_i^2}{2}+\dots$", fontsize=100)
bb = t.get_window_extent(renderer=r)
w_em = bb.width * 72 / fig.dpi / 100          # width in em
# Cambria Math runs ~15% wider than Computer Modern
print(f"at 18pt: {w_em * 1.15 * 18 / 72 * 2.54:.2f} cm wide")
```

To show the user what they will actually get, composite a matplotlib-rendered
equation onto a LibreOffice render of the slide *with the equation removed*.
Say plainly that the glyphs are a stand-in and the position is real.

**Only some defects survive the trip.** Anything in the "Audit" section below
is invisible in a LibreOffice PDF and shows up when PowerPoint opens the file.

## Audit

`python $S audit deck.pptx` checks, in order:

1. **Dangling relationships** and stale `[Content_Types].xml` defaults — the
   usual cause of PowerPoint's "needs to be repaired" dialog.
2. **`<p:blipFill>` with neither `<a:stretch>` nor `<a:tile>`.** LibreOffice
   silently stretches such a picture to its frame; PowerPoint applies its own
   default and draws the image at native size, so a 360×360 @100 dpi logo
   (9.1 cm native) in a 3.3 cm frame comes out mangled. The fix:

   ```xml
   <p:blipFill><a:blip r:embed="rId3"/>
     <a:stretch><a:fillRect/></a:stretch></p:blipFill>
   ```

   Add `<a:picLocks noChangeAspect="1"/>` in `<p:cNvPicPr>` while you are there.
3. **Aspect-ratio distortion** — visible pixels *after* `srcRect` cropping
   versus the frame. `python-pptx` exposes the crop as `crop_left/right/top/
   bottom`; a picture is undistorted when
   `w(1-cl-cr) / h(1-ct-cb) == width/height`. Fix by widening the crop (keeps
   the layout) or by resizing the frame (keeps the framing) — ask which.
4. **Duplicate shape ids.** Only a real clash matters: an `mc:Choice` /
   `mc:Fallback` pair legitimately repeats the same id, and every equation
   PowerPoint has saved produces one.
5. **TIFF parts.** Legal but poorly supported by PowerPoint on Windows, and
   usually uncompressed. `python $S tiff2png deck.pptx` re-encodes losslessly,
   rewires the `.rels` and content types, and typically halves the file.
6. **Fonts** that PowerPoint will substitute — but check the *slot* before
   worrying. A face used only in `<a:sym>` never touches visible text; one in
   `<a:latin>` / `<a:ea>` / `<a:cs>` does. Fonts in `notesSlides/` are speaker
   notes and the audience never sees them.

Two more worth a manual look:

- **`<a:normAutofit fontScale="…">`** — PowerPoint shrinks the text by that
  factor, LibreOffice often does not, so the preview shows text larger than
  reality.
- **`wrap="none"`** (pervasive in Keynote exports). The text renders on one
  line at its natural width and simply overflows its box. Harmless until it
  reaches a neighbour or the slide edge; measure with the fonts PowerPoint will
  actually use.

## Editing

**Prefer `python-pptx` for geometry, raw XML for everything it cannot model.**

```python
from pptx import Presentation
from pptx.util import Cm, Emu
prs = Presentation(path); s = prs.slides[1]           # 0-based
for i, sh in enumerate(s.shapes):
    print(i, sh.shape_type, sh.name,
          f"L{Emu(sh.left).cm:.2f} T{Emu(sh.top).cm:.2f} "
          f"W{Emu(sh.width).cm:.2f} H{Emu(sh.height).cm:.2f}")
s.shapes[2].top = Cm(4.60)
prs.save(path)
```

Traps:

- **Hidden slides.** `slide._element.get("show") == "0"`. Count and review only
  the shown ones; a 31-slide file can be a 16-slide talk.
- **Shapes inside `mc:AlternateContent` are invisible to `python-pptx`.** Every
  equation saved by PowerPoint lives there. If a shape you can see in the
  render is missing from `shapes`, that is why — edit the XML.
- **`shape.image.blob` is the *uncropped* source.** What the slide shows is the
  blob after `srcRect`. Apply the crop yourself before comparing or re-using.
- **Group children** have their own coordinate space (`chOff`/`chExt`); scaling
  a group means scaling graphics and repositioning text separately, or the
  annotations drift off the thing they annotate.

**Replacing a figure**: swap the bytes, do not delete and re-add — that
preserves the relationship, z-order, crop, and effects.

```bash
python $S swap-image deck.pptx --slide 2              # list the pictures
python $S swap-image deck.pptx --slide 2 --index 1 --file new.png
```

Render the replacement to the frame's exact aspect ratio, or pad it to that
ratio, so the slide geometry never has to change.

**Inserting a native OMML equation.** `python-pptx` cannot; inject XML before
`</p:spTree>`. Build it from small helpers (`m:nary`, `m:f`, `m:sSub`,
`m:sSubSup`, `m:d`, `m:acc`) rather than by hand, put `<a:rPr>` — *not* the
WordprocessingML `<w:rPr>` a LaTeX-to-OOXML converter emits — inside every
`<m:r>`, and declare the `a14` namespace on the element itself:

```xml
<a:p><a:pPr algn="ctr"><a:defRPr sz="1800"><a:latin typeface="Cambria Math"/></a:defRPr></a:pPr>
  <a14:m xmlns:a14="http://schemas.microsoft.com/office/drawing/2010/main">
    <m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
      <m:r><a:rPr sz="1800" i="1"><a:latin typeface="Cambria Math"/></a:rPr><m:t>H</m:t></m:r>
    </m:oMath></a14:m></a:p>
```

Validate with `lxml.etree.fromstring` on the whole slide part before saving.
When PowerPoint next saves the file it rewrites this into `mc:AlternateContent`
with a raster fallback — expect the file to grow, and do not delete the
fallback.

**Slide-number fields.** A `<a:fld type="slidenum">` carries a literal `<a:t>`
fallback. PowerPoint computes the number and ignores it; renderers that do not
understand the field show a blank without it, and `python-pptx` saves and
hand-rolled XML rewrites both strip it. `python $S fix-nums deck.pptx` puts it
back — run it **last, after every write**. One caveat: the literal goes stale
if slides are reordered, so re-run it then too, and trust the rendered PDF over
the literal.

## Working alongside the user

They will have the deck open. Two habits save a lot of lost work:

- **Check `mtime` and file size before and after each of your writes.** If the
  file changed underneath you, PowerPoint saved over your edits — say so, ask
  them to close it, and redo. A sudden size jump plus new `mc:AlternateContent`
  blocks means PowerPoint re-saved and rewrote your equations.
- **Back up before every write** (all writing subcommands do, to
  `<file>.bak_YYYYmmdd_HHMMSS`) and keep the backups. They are the only undo,
  and they are how you restore an original figure byte-for-byte later:

  ```python
  from pptx import Presentation
  blob = Presentation("deck.pptx.bak_20260828_205337").slides[1].shapes[1].image.blob
  ```

## Layout judgement

- Fix alignment against the *ink*, not the frames: measure from the rendered
  PDF, and give elements in a column a shared axis.
- Match a replacement figure to its neighbours' visual language — a lone clean
  object beside a dense reference figure reads as contrast; two dense figures
  read as clutter.
- When a slide feels crowded, moving an element to the slide where it carries
  the argument beats shrinking everything to fit.
- Say what you could not verify. If the preview cannot show a font or an
  equation faithfully, hand over the numbers you used and ask them to confirm
  in PowerPoint.
