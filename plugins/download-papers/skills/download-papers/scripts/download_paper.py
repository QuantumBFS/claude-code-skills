#!/usr/bin/env python3
"""Download a PDF from a single URL.

This script is intentionally narrow: it does NOT resolve DOIs, probe
Sci-Hub mirrors, or do open-access discovery. Those steps are the calling
agent's job (it has richer tools — web search, Unpaywall, arXiv lookup,
etc.). The script only handles the final "fetch this URL and save a
verified PDF" step.

Input: a single URL. Either:
  * a direct PDF URL (e.g. an arXiv PDF, an Unpaywall OA URL), or
  * an HTML page that embeds a PDF via <embed>/<iframe>/<a> with `.pdf`
    in the href (e.g. a Sci-Hub landing page).

Output (stdout): JSON with one of:
  {"status": "ok",      "url": "...", "local_path": "...", "bytes": N}
  {"status": "dry_run", "url": "...", "local_path": "...", "bytes": N}
  {"status": "error",   "url": "...", "errors": ["..."]}

Exit code: 0 on ok/dry_run, 1 on error.
"""

import argparse
import hashlib
import html.parser
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PDF_RE = re.compile(r"https?://[^\s'\"<>]+\.pdf(?:\?[^\s'\"<>]*)?", re.I)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)


class PdfLinkParser(html.parser.HTMLParser):
    """Collect any tag attribute whose value contains `.pdf`."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("src", "href", "data"):
            value = attrs.get(key)
            if value and ".pdf" in value.lower():
                self.links.append(value)


def fetch(url, timeout=30):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; download-paper/2.0)",
            "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.geturl(), response.headers.get_content_type(), response.read()


def looks_like_pdf(data):
    return data.startswith(b"%PDF")


def absolutize(base_url, link):
    if link.startswith("//"):
        return "https:" + link
    return urllib.parse.urljoin(base_url, link)


def extract_pdf_url(page_url, body):
    """Find a PDF link inside an HTML body. Returns absolute URL or None."""
    text = body.decode("utf-8", errors="ignore")
    parser = PdfLinkParser()
    parser.feed(text)
    if parser.links:
        return absolutize(page_url, parser.links[0])
    match = PDF_RE.search(text)
    if match:
        return absolutize(page_url, match.group(0))
    return None


def make_filename(url, hint=None):
    if hint:
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", hint).strip("_")
        if not slug.lower().endswith(".pdf"):
            slug += ".pdf"
        return slug

    doi = DOI_RE.search(url)
    if doi:
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", doi.group(0)).strip("_")
        return f"{stem}.pdf"

    path_name = Path(urllib.parse.urlparse(url).path).name
    if path_name.lower().endswith(".pdf"):
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", path_name)

    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return f"paper_{digest}.pdf"


def download(url, out_dir, filename=None, hint=None, dry_run=False):
    errors = []

    try:
        final_url, content_type, body = fetch(url)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": "error", "url": url, "errors": [f"fetch {url}: {exc}"]}

    if content_type == "application/pdf" or looks_like_pdf(body):
        if not looks_like_pdf(body):
            return {
                "status": "error",
                "url": final_url,
                "errors": [
                    f"Content-Type {content_type} but body lacks %PDF magic at {final_url}",
                ],
            }
        pdf_url, pdf_data = final_url, body
    else:
        pdf_url = extract_pdf_url(final_url, body)
        if not pdf_url:
            return {
                "status": "error",
                "url": final_url,
                "errors": [
                    f"No PDF link found at {final_url} (Content-Type {content_type}). "
                    "Have the agent resolve a direct PDF URL and call again.",
                ],
            }
        try:
            _, ctype2, pdf_data = fetch(pdf_url)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return {
                "status": "error",
                "url": pdf_url,
                "errors": [f"fetch {pdf_url}: {exc}"],
            }
        if not looks_like_pdf(pdf_data):
            return {
                "status": "error",
                "url": pdf_url,
                "errors": [
                    f"URL extracted from page is not a PDF: {pdf_url} (Content-Type {ctype2})",
                ],
            }

    local_path = out_dir / (filename or make_filename(pdf_url, hint))
    if dry_run:
        return {
            "status": "dry_run",
            "url": pdf_url,
            "local_path": str(local_path),
            "bytes": len(pdf_data),
        }
    out_dir.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(pdf_data)
    return {
        "status": "ok",
        "url": pdf_url,
        "local_path": str(local_path),
        "bytes": len(pdf_data),
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Download a PDF from a URL (direct PDF or HTML page with embedded PDF). "
            "Discovery (DOI resolution, OA lookup, mirror probing) is the agent's job."
        )
    )
    parser.add_argument("url", help="Direct PDF URL, or HTML page containing an embedded PDF")
    parser.add_argument("--out-dir", default="papers", help="Output directory (default: papers)")
    parser.add_argument("--filename", help="Exact output filename")
    parser.add_argument(
        "--hint",
        help="Filename slug (e.g. 'haldane1983_prl') used when URL has no DOI / .pdf basename",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Resolve only; do not write a file"
    )
    args = parser.parse_args()

    if urllib.parse.urlparse(args.url).scheme not in {"http", "https"}:
        print(
            json.dumps(
                {
                    "status": "error",
                    "url": args.url,
                    "errors": [
                        "Input must be an http(s) URL. DOIs and titles require "
                        "agent-side resolution before calling this script.",
                    ],
                },
                indent=2,
            )
        )
        return 1

    result = download(args.url, Path(args.out_dir), args.filename, args.hint, args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"ok", "dry_run"} else 1


if __name__ == "__main__":
    sys.exit(main())
