#!/usr/bin/env python3
"""Download a paper PDF from a DOI, publisher URL, Sci-Hub page, or direct PDF URL."""

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

DEFAULT_MIRRORS = [
    "https://sci-hub.se",
    "https://sci-hub.st",
    "https://sci-hub.ru",
    "https://sci-hub.ee",
]

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.I)
PDF_RE = re.compile(r"https?://[^\s'\"<>]+\.pdf(?:\?[^\s'\"<>]*)?", re.I)


class PdfLinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("src", "href"):
            value = attrs.get(key)
            if value and ".pdf" in value.lower():
                self.links.append(value)


def fetch(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.geturl(), response.headers.get_content_type(), response.read()


def extract_doi(value):
    match = DOI_RE.search(value)
    return match.group(0) if match else None


def is_url(value):
    return urllib.parse.urlparse(value).scheme in {"http", "https"}


def make_filename(input_value, pdf_url):
    doi = extract_doi(input_value)
    if doi:
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", doi).strip("_")
        return f"{stem}.pdf"

    path_name = Path(urllib.parse.urlparse(pdf_url or input_value).path).name
    if path_name.lower().endswith(".pdf"):
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", path_name)

    digest = hashlib.sha1(input_value.encode("utf-8")).hexdigest()[:12]
    return f"paper_{digest}.pdf"


def looks_like_pdf(data):
    return data.startswith(b"%PDF")


def absolutize(base_url, link):
    if link.startswith("//"):
        return "https:" + link
    return urllib.parse.urljoin(base_url, link)


def find_pdf_url(page_url, body):
    text = body.decode("utf-8", errors="ignore")
    parser = PdfLinkParser()
    parser.feed(text)
    if parser.links:
        return absolutize(page_url, parser.links[0])

    match = PDF_RE.search(text)
    if match:
        return absolutize(page_url, match.group(0))
    return None


def candidate_pages(input_value, mirror):
    if is_url(input_value):
        yield input_value
        doi = extract_doi(input_value)
    else:
        doi = extract_doi(input_value)
        if doi:
            yield f"https://doi.org/{urllib.parse.quote(doi, safe='/')}"

    if doi:
        mirrors = [mirror] if mirror else DEFAULT_MIRRORS
        for base in mirrors:
            yield f"{base.rstrip('/')}/{doi}"


def download(input_value, out_dir, filename=None, mirror=None, dry_run=False):
    errors = []
    for page in candidate_pages(input_value, mirror):
        try:
            final_url, content_type, body = fetch(page)
            if content_type == "application/pdf" or looks_like_pdf(body):
                if not looks_like_pdf(body):
                    errors.append(f"Downloaded content is not a PDF: {final_url}")
                    continue
                pdf_url = final_url
                pdf_data = body
            else:
                pdf_url = find_pdf_url(final_url, body)
                if not pdf_url:
                    errors.append(f"No PDF link found at {page}")
                    continue
                if dry_run:
                    pdf_data = b""
                else:
                    _, _, pdf_data = fetch(pdf_url)
                    if not looks_like_pdf(pdf_data):
                        errors.append(f"Downloaded content is not a PDF: {pdf_url}")
                        continue

            local_path = out_dir / (filename or make_filename(input_value, pdf_url))
            if dry_run:
                return {"status": "dry_run", "input": input_value, "pdf_url": pdf_url, "local_path": str(local_path)}

            out_dir.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(pdf_data)
            return {"status": "ok", "input": input_value, "pdf_url": pdf_url, "local_path": str(local_path)}
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"{page}: {exc}")

    return {"status": "error", "input": input_value, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Download a paper PDF from a DOI or URL.")
    parser.add_argument("input", help="DOI, publisher URL, Sci-Hub page, or direct PDF URL")
    parser.add_argument("--out-dir", default="papers", help="Output directory (default: papers)")
    parser.add_argument("--filename", help="Output filename")
    parser.add_argument("--mirror", help="Sci-Hub mirror to try instead of defaults")
    parser.add_argument("--dry-run", action="store_true", help="Resolve only; do not write a file")
    args = parser.parse_args()

    result = download(args.input, Path(args.out_dir), args.filename, args.mirror, args.dry_run)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] in {"ok", "dry_run"} else 1


if __name__ == "__main__":
    sys.exit(main())
