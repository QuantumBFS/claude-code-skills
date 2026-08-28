#!/usr/bin/env python3
"""Helpers for editing and auditing PowerPoint .pptx decks.

Subcommands
-----------
render     pptx -> PDF -> PNG, substituting fonts the machine lacks so the
           preview is not silently wrong.
audit      report the defects that only surface once PowerPoint opens the file.
fix-nums   re-add the <a:t> fallback inside slide-number fields (do this LAST,
           after every save, or exported PDFs show blank page numbers).
swap-image replace one picture's bytes in place, keeping rels / z-order / crop.
tiff2png   losslessly re-encode every TIFF part as PNG and rewire references.

Every subcommand that writes takes --backup (default on): a sibling
<file>.bak_YYYYmmdd_HHMMSS copy is made before the first byte is changed.
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
EMU_PER_CM = 360000
SLIDE_RE = re.compile(r"ppt/slides/slide(\d+)\.xml$")


# --------------------------------------------------------------------------- #
# small utilities
# --------------------------------------------------------------------------- #
def backup(path: str) -> str:
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = f"{path}.bak_{stamp}"
    shutil.copy2(path, dst)
    return dst


def rewrite_zip(path: str, transform) -> None:
    """Rewrite every part through `transform(name, bytes) -> (name, bytes) | None`.

    Returning None drops the part. Order is preserved, which keeps diffs small
    and avoids upsetting readers that assume [Content_Types].xml comes first.
    """
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for item in zin.infolist():
            out = transform(item.filename, zin.read(item.filename))
            if out is None:
                continue
            name, data = out
            if name == item.filename:
                zo.writestr(item, data)
            else:
                zo.writestr(name, data)
    os.replace(tmp, path)


def cm(emu) -> float:
    return (emu or 0) / EMU_PER_CM


# --------------------------------------------------------------------------- #
# fonts
# --------------------------------------------------------------------------- #
def font_dirs(include_office: bool) -> list[str]:
    """Font directories.

    `include_office` decides *whose* view of the machine you get, and the two
    answers genuinely differ:

    * PowerPoint additionally loads the fonts Microsoft ships inside its own
      app bundles - Cambria Math, Microsoft YaHei, Arial, ... - so for judging
      what the presenter will see, include them.
    * LibreOffice (and every other app) only sees system-registered fonts, so
      for deciding what to substitute before a headless preview, exclude them.

    Getting this backwards produces a preview that quietly renders CJK with a
    Latin fallback while reporting that nothing was substituted.
    """
    home = os.path.expanduser("~")
    dirs = [
        "/System/Library/Fonts",
        "/Library/Fonts",
        f"{home}/Library/Fonts",
        "/usr/share/fonts",
        f"{home}/.local/share/fonts",
    ]
    if include_office:
        import glob

        dirs += glob.glob("/Applications/Microsoft*.app/Contents/Resources/DFonts")
    return [d for d in dirs if os.path.isdir(d)]


def installed_font_names(include_office: bool = True) -> set[str]:
    """Family/full names of the fonts loadable by PowerPoint (or, with
    include_office=False, by every other application)."""
    import glob

    try:
        from fontTools.ttLib import TTCollection, TTFont
    except ImportError:  # degrade gracefully rather than lie
        return set()
    names: set[str] = set()
    for d in font_dirs(include_office):
        for p in glob.glob(os.path.join(d, "**", "*"), recursive=True):
            if not p.lower().endswith((".ttf", ".ttc", ".otf", ".otc")):
                continue
            try:
                fonts = (
                    TTCollection(p).fonts
                    if p.lower().endswith((".ttc", ".otc"))
                    else [TTFont(p, fontNumber=0, lazy=True)]
                )
            except Exception:
                continue
            for f in fonts:
                try:
                    for nid in (1, 4, 16):
                        nm = f["name"].getDebugName(nid)
                        if nm:
                            names.add(nm)
                except Exception:
                    pass
                finally:
                    try:
                        f.close()
                    except Exception:
                        pass
    return names


def referenced_fonts(path: str) -> dict[str, collections.Counter]:
    """typeface -> Counter of the slots (latin/ea/cs/sym) it appears in."""
    out: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if not re.match(r"ppt/(slides|slideLayouts|slideMasters|theme)/.*\.xml$", n):
                continue
            x = z.read(n).decode("utf-8", "replace")
            for m in re.finditer(r"<a:(latin|ea|cs|sym)\s+typeface=\"([^\"]+)\"", x):
                slot, face = m.group(1), m.group(2)
                if face and not face.startswith("+"):
                    out[face][slot] += 1
    return out


MATH_FONTS = {"Cambria Math", "Latin Modern Math", "STIX Two Math",
              "XITS Math", "Asana Math", "TeX Gyre Termes Math"}


def _cjk_fallback(avail: set[str]) -> str:
    for cand in ("PingFang SC", "Heiti SC", "Hiragino Sans GB W3", "Noto Sans CJK SC",
                 "Source Han Sans SC", "WenQuanYi Zen Hei", "SimHei"):
        if cand in avail:
            return cand
    return "sans-serif"


# --------------------------------------------------------------------------- #
# render
# --------------------------------------------------------------------------- #
def soffice_bin() -> str:
    for c in ("/Applications/LibreOffice.app/Contents/MacOS/soffice",
              shutil.which("soffice"), shutil.which("libreoffice")):
        if c and os.path.exists(c):
            return c
    sys.exit("LibreOffice not found (install it, or pass --pdf to reuse an existing PDF)")


def cmd_render(args) -> None:
    """pptx -> proxy with substituted fonts -> PDF -> PNGs.

    The substitution matters: a deck authored on a machine with Microsoft
    YaHei renders with a Latin fallback (no CJK glyphs, wrong metrics) on a
    machine without it, and the preview then lies about wrapping and overflow.
    """
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.pptx)) or ".", "render")
    os.makedirs(out, exist_ok=True)

    # LibreOffice cannot use the fonts bundled inside the Office apps.
    avail = installed_font_names(include_office=False)
    subs: dict[str, str] = {}
    if avail:
        cjk = _cjk_fallback(avail)
        for face, slots in referenced_fonts(args.pptx).items():
            if face in avail:
                continue
            if "sym" in slots and len(slots) == 1:
                continue  # symbol slot only: never reaches visible text
            if face in MATH_FONTS:
                # only ever appears inside <m:oMath>, whose run properties
                # LibreOffice ignores wholesale - substituting cannot help and
                # would misreport what was changed
                continue
            subs[face] = cjk if any(s in slots for s in ("ea", "cs")) else "Helvetica"
    for pair in args.sub or []:
        a, _, b = pair.partition("=")
        subs[a] = b
    if subs:
        print("font substitutions for preview:", subs)

    proxy = os.path.join(out, "_proxy.pptx")

    def tr(name, data):
        if subs and name.endswith((".xml", ".rels")):
            t = data.decode("utf-8", "replace")
            for a, b in subs.items():
                t = t.replace(f'typeface="{a}"', f'typeface="{b}"')
            data = t.encode()
        return name, data

    shutil.copy2(args.pptx, proxy)
    rewrite_zip(proxy, tr)

    subprocess.run([soffice_bin(), "--headless", "--convert-to", "pdf",
                    "--outdir", out, proxy],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pdf = os.path.join(out, "_proxy.pdf")
    if not os.path.exists(pdf):
        sys.exit("LibreOffice produced no PDF")

    import fitz

    doc = fitz.open(pdf)
    pages = (
        [int(p) for p in args.pages.split(",")] if args.pages
        else list(range(1, doc.page_count + 1))
    )
    for p in pages:
        page = doc[p - 1]
        zoom = args.width / page.rect.width
        png = os.path.join(out, f"slide{p:02d}.png")
        page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(png)
        print("wrote", png)
    print(f"PDF: {pdf}  ({doc.page_count} pages)")


# --------------------------------------------------------------------------- #
# audit
# --------------------------------------------------------------------------- #
def cmd_audit(args) -> None:
    path = args.pptx
    problems = 0

    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())

        print("== package integrity ==")
        # dangling relationships are the classic "PowerPoint wants to repair it"
        from lxml import etree

        dangling = []
        for n in sorted(names):
            if not n.endswith(".rels"):
                continue
            base = "/".join(n.split("/")[:-2])
            for rel in etree.fromstring(z.read(n)):
                if rel.get("TargetMode") == "External":
                    continue
                p = (base + "/" + rel.get("Target")) if base else rel.get("Target")
                parts: list[str] = []
                for seg in p.split("/"):
                    if seg == "..":
                        parts and parts.pop()
                    elif seg not in (".", ""):
                        parts.append(seg)
                if "/".join(parts) not in names:
                    dangling.append((n, rel.get("Id"), rel.get("Target")))
        print("  dangling relationships:", dangling or "none")
        problems += len(dangling)

        ct = z.read("[Content_Types].xml").decode()
        stale = [e for e, _ in re.findall(r'<Default Extension="([^"]+)" ContentType="([^"]+)"/>', ct)
                 if not any(x.lower().endswith("." + e.lower()) for x in names)]
        if stale:
            print("  Default declarations with no matching part:", stale)

        print()
        print("== blipFill without a fill mode ==")
        print("  (PowerPoint falls back to its own default and the picture is")
        print("   drawn at native size; LibreOffice silently stretches, so this")
        print("   is invisible in a headless preview)")
        missing = []
        for n in sorted(names):
            if not SLIDE_RE.match(n):
                continue
            x = z.read(n).decode()
            for m in re.finditer(r"<p:blipFill[^>]*>.*?</p:blipFill>", x, re.S):
                b = m.group(0)
                if "<a:stretch" not in b and "<a:tile" not in b:
                    s = x.rfind("<p:pic>", 0, m.start())
                    nm = re.search(r'name="([^"]*)"', x[s:m.start()])
                    missing.append((n, nm.group(1) if nm else "?"))
        for n, nm in missing:
            print(f"  {n}  {nm}")
        print("  ->", len(missing), "found")
        problems += len(missing)

        print()
        print("== duplicate shape ids ==")
        for n in sorted(names):
            if not SLIDE_RE.match(n):
                continue
            x = z.read(n).decode()
            ids = re.findall(r'<p:cNvPr id="(\d+)"', x)
            dups = [k for k, v in collections.Counter(ids).items() if v > 1]
            if not dups:
                continue
            # an mc:Choice / mc:Fallback pair legitimately repeats the same id
            benign = x.count("<mc:AlternateContent") > 0
            note = "  (inside mc:AlternateContent - expected)" if benign else "  <-- real clash"
            print(f"  {n}: {dups}{note}")
            if not benign:
                problems += len(dups)

        print()
        print("== image formats ==")
        ext = collections.Counter(
            m.rsplit(".", 1)[-1].lower()
            for m in names
            if m.startswith("ppt/media/") and not m.endswith("/") and "." in m.split("/")[-1]
        )
        print(" ", dict(ext))
        if ext.get("tiff") or ext.get("tif"):
            print("  TIFF is poorly supported by PowerPoint on Windows; run"
                  " `tiff2png` to re-encode losslessly.")
            problems += 1

    print()
    print("== picture aspect ratio (visible pixels vs frame) ==")
    from pptx import Presentation

    prs = Presentation(path)
    bad = 0
    for i, slide in enumerate(prs.slides, 1):
        def walk(shapes):
            nonlocal bad
            for sh in shapes:
                if sh.shape_type == 6:  # GROUP
                    walk(sh.shapes)
                    continue
                if sh.shape_type != 13:  # PICTURE
                    continue
                w, h = sh.image.size
                vw = w * (1 - sh.crop_left - sh.crop_right)
                vh = h * (1 - sh.crop_top - sh.crop_bottom)
                if vw <= 0 or vh <= 0 or not sh.width or not sh.height:
                    continue
                pa, fa = vw / vh, cm(sh.width) / cm(sh.height)
                dev = abs(pa - fa) / pa * 100
                if dev > 1.0:
                    print(f"  slide {i}: {sh.name[:26]!r} pixels {pa:.3f} vs frame"
                          f" {fa:.3f}  -> distorted {dev:.1f}%")
                    bad += 1
        walk(slide.shapes)
    if not bad:
        print("  all within 1%")
    problems += bad

    print()
    print("== slide-number fields without an <a:t> fallback (informational) ==")
    print("  PowerPoint evaluates the field, and so do renderers that understand")
    print("  type=\"slidenum\". Ones that do not fall back to the literal <a:t>,")
    print("  and show a blank when it is absent. python-pptx edits and hand-rolled")
    print("  XML rewrites routinely strip it. Trust the rendered PDF, not this")
    print("  count: run `render` and read the numbers off the page.")
    missing_t = []
    with zipfile.ZipFile(path) as z:
        for n in sorted(z.namelist()):
            m = SLIDE_RE.match(n)
            if not m:
                continue
            x = z.read(n).decode()
            for fld in re.findall(r"<a:fld[^>]*type=\"slidenum\".*?</a:fld>", x, re.S):
                if "<a:t>" not in fld:
                    missing_t.append(int(m.group(1)))
    print(" ", sorted(set(missing_t)) or "none")

    print()
    print("== fonts (as PowerPoint sees them, Office-bundled ones included) ==")
    avail = installed_font_names(include_office=True)
    if not avail:
        print("  (fontTools not installed - skipped)")
    else:
        for face, slots in sorted(referenced_fonts(path).items(),
                                  key=lambda kv: -sum(kv[1].values())):
            if face in avail:
                continue
            visible = any(s in slots for s in ("latin", "ea", "cs"))
            tag = "AFFECTS VISIBLE TEXT" if visible else "sym slot only - harmless"
            print(f"  missing: {face!r} {dict(slots)}  {tag}")
            problems += int(visible)

    print()
    print(f"== {problems} issue(s) worth looking at ==")


# --------------------------------------------------------------------------- #
# slide numbers
# --------------------------------------------------------------------------- #
def cmd_fix_nums(args) -> None:
    if args.backup:
        print("backup:", backup(args.pptx))
    fixed: list[int] = []

    def tr(name, data):
        m = SLIDE_RE.match(name)
        if not m:
            return name, data
        num = int(m.group(1))
        x = data.decode()

        def rep(mm):
            blk = mm.group(0)
            if "<a:t>" in blk:
                return blk
            return blk.replace("</a:fld>", f"<a:t>{num}</a:t></a:fld>")

        new, _ = re.subn(r"<a:fld[^>]*type=\"slidenum\".*?</a:fld>", rep, x, flags=re.S)
        if new != x:
            fixed.append(num)
            data = new.encode()
        return name, data

    rewrite_zip(args.pptx, tr)
    print("restored <a:t> on slides:", sorted(fixed) or "none needed")


# --------------------------------------------------------------------------- #
# image swap
# --------------------------------------------------------------------------- #
def cmd_swap_image(args) -> None:
    from pptx import Presentation

    prs = Presentation(args.pptx)
    slide = prs.slides[args.slide - 1]
    pics = [sh for sh in slide.shapes if sh.shape_type == 13]
    if not pics:
        sys.exit(f"slide {args.slide} has no pictures")
    if args.index is None:
        for k, sh in enumerate(pics):
            print(f"  [{k}] {sh.name[:30]!r} {sh.image.size} {sh.image.ext} "
                  f"L{cm(sh.left):.2f} T{cm(sh.top):.2f} "
                  f"W{cm(sh.width):.2f} H{cm(sh.height):.2f}")
        return
    if args.backup:
        print("backup:", backup(args.pptx))
    target = pics[args.index]
    part = target.part.related_part(target._element.blip_rId)
    part._blob = open(args.file, "rb").read()
    prs.save(args.pptx)
    print(f"replaced picture [{args.index}] on slide {args.slide} with {args.file}")
    print("NOTE: run `fix-nums` afterwards - saving can strip slide-number fallbacks.")


# --------------------------------------------------------------------------- #
# tiff -> png
# --------------------------------------------------------------------------- #
def cmd_tiff2png(args) -> None:
    from PIL import Image

    with zipfile.ZipFile(args.pptx) as z:
        names = set(z.namelist())
        tiffs = sorted(n for n in names
                       if n.startswith("ppt/media/") and n.lower().endswith((".tif", ".tiff")))
        if not tiffs:
            print("no TIFF parts")
            return
        used = {int(m.group(1)) for m in
                (re.match(r"ppt/media/image(\d+)\.", n) for n in names) if m}
        nxt = (max(used) + 1) if used else 1
        mapping: dict[str, str] = {}
        for t in tiffs:
            while f"ppt/media/image{nxt}.png" in names or f"ppt/media/image{nxt}.png" in mapping.values():
                nxt += 1
            mapping[t] = f"ppt/media/image{nxt}.png"
            nxt += 1
        conv: dict[str, bytes] = {}
        for old, new in mapping.items():
            raw = z.read(old)
            im = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)   # lossless: same pixels, same mode
            conv[old] = buf.getvalue()
            print(f"  {os.path.basename(old):18s} {im.size} {im.mode} "
                  f"{len(raw)/1e6:6.2f}MB -> {len(conv[old])/1e6:5.2f}MB")

    if args.backup:
        print("backup:", backup(args.pptx))
    repl = {os.path.basename(k): os.path.basename(v) for k, v in mapping.items()}

    def tr(name, data):
        if name in conv:
            return mapping[name], conv[name]
        if name.endswith(".rels"):
            t = data.decode()
            for a, b in repl.items():
                t = t.replace(a, b)
            return name, t.encode()
        if name == "[Content_Types].xml":
            t = data.decode()
            for e in ("tiff", "tif"):
                t = t.replace(f'<Default Extension="{e}" ContentType="image/tiff"/>', "")
            if '<Default Extension="png"' not in t:
                t = t.replace("</Types>", '<Default Extension="png" ContentType="image/png"/></Types>')
            return name, t.encode()
        return name, data

    rewrite_zip(args.pptx, tr)
    print(f"converted {len(mapping)} part(s); "
          f"file is now {os.path.getsize(args.pptx)/1e6:.1f} MB")


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="pptx -> PDF -> PNG with font substitution")
    r.add_argument("pptx")
    r.add_argument("--out")
    r.add_argument("--pages", help="1-based, comma separated, e.g. 2,3,15")
    r.add_argument("--width", type=int, default=1500)
    r.add_argument("--sub", action="append", metavar="FROM=TO",
                   help="extra font substitution, repeatable")
    r.set_defaults(func=cmd_render)

    a = sub.add_parser("audit", help="report PowerPoint-only defects")
    a.add_argument("pptx")
    a.set_defaults(func=cmd_audit)

    f = sub.add_parser("fix-nums", help="restore <a:t> in slide-number fields")
    f.add_argument("pptx")
    f.add_argument("--no-backup", dest="backup", action="store_false")
    f.set_defaults(func=cmd_fix_nums, backup=True)

    s = sub.add_parser("swap-image", help="replace a picture's bytes in place")
    s.add_argument("pptx")
    s.add_argument("--slide", type=int, required=True)
    s.add_argument("--index", type=int, help="omit to list the pictures")
    s.add_argument("--file")
    s.add_argument("--no-backup", dest="backup", action="store_false")
    s.set_defaults(func=cmd_swap_image, backup=True)

    t = sub.add_parser("tiff2png", help="losslessly re-encode TIFF parts as PNG")
    t.add_argument("pptx")
    t.add_argument("--no-backup", dest="backup", action="store_false")
    t.set_defaults(func=cmd_tiff2png, backup=True)

    args = ap.parse_args()
    if args.cmd == "swap-image" and args.index is not None and not args.file:
        ap.error("--file is required when --index is given")
    args.func(args)


if __name__ == "__main__":
    main()
