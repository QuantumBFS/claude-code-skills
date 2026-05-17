---
name: download-papers
description: Use when the user asks to download an academic paper or get the PDF — given a URL, DOI, paper title, or citation. The agent resolves discovery (Unpaywall, arXiv, author page, sci-hub) into a single candidate URL, then hands it to the bundled helper which does only the fetch-and-verify step. Triggers on phrases like "download paper", "get me the PDF", "fetch this paper", "get this DOI".
---

# Download Papers

Goal: put a verified PDF on local disk with minimum friction. **The agent
does discovery; the helper script does the narrow download.** This split
keeps the script reliable and lets the agent use its full toolset (web
search, MCP lookups, judgement about which mirror is up today) for the
parts that need judgement.

## Workflow

1. **Resolve the user's request to one candidate URL.** Start from the
   highest-quality source and stop as soon as you have a plausible link:

   | Input | Discovery order |
   |---|---|
   | Direct PDF URL | use as-is |
   | arXiv ID or arXiv abs page | use `https://arxiv.org/pdf/<id>` |
   | DOI or publisher URL | (a) → (b) → (c) → (d) → (e) below |
   | Title or citation only | search arXiv first; if found, jump to arXiv path. Otherwise web-search for a DOI or PDF URL and follow the DOI path |

   For DOIs:

   - **(a) Unpaywall** — query
     `https://api.unpaywall.org/v2/<DOI>?email=anonymous@example.com`.
     Returns JSON; if `is_oa` is true, the candidate URL is
     `best_oa_location.url_for_pdf` (fall back to `best_oa_location.url`
     if the PDF field is null). Unpaywall is free, legitimate, and
     fast — the right primary check.
   - **(b) arXiv preprint of the same DOI.** Many published papers have
     a preprint on arXiv. Search by title/author; the arXiv API supports
     `query=ti:"…" AND au:"…"`.
   - **(c) Author homepage or institutional repository.** Web-search
     `site:<author-domain> "<paper title>" filetype:pdf` or look at the
     author's "Publications" page. Older Nobel-laureate papers often
     surface here.
   - **(d) Publisher page itself.** Sometimes serves a free PDF (editor's
     pick, open-access trial, transitional OA). Worth trying once.
   - **(e) Sci-Hub** — last resort. Try a current mirror
     (`sci-hub.{se,st,ru,ee,ren,box}` — list goes stale, expect attrition).
     The Sci-Hub landing page is HTML with the PDF embedded via
     `<embed src="//…/uploads/…/paper.pdf">`. **You can hand that landing
     page URL straight to the helper** — it will extract the embed and
     fetch the PDF, no extra parsing needed. Note: probing Sci-Hub
     mirrors from inside the agent harness may be blocked by the
     auto-mode classifier; if so, surface that to the user and let them
     run the helper directly.

2. **Call the helper script** with the resolved URL:
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/download_paper.py "<URL>" \
       --out-dir papers --hint "<firstauthor><year>_<shorttitle>"
   ```
   The helper:
   - Accepts either a direct PDF URL or an HTML page that embeds one
     (via `<embed>`, `<iframe>`, `<a href>`, or `<object data>`).
   - Verifies the result is a real PDF (`%PDF` magic bytes).
   - Outputs JSON: `{"status": "ok"|"dry_run"|"error", "url": ..., "local_path": ..., "bytes": ...}`.
   - Exits 0 on ok/dry_run, 1 on error.

3. **On `status: ok`** — report the `local_path` to the user.
   **On `status: error`** — read the message, pick another candidate from
   step 1, and try again. If every path is exhausted and Unpaywall said
   `is_oa: false`, the paper is genuinely paywalled with no OA version;
   stop and tell the user, suggest legitimate alternatives (institutional
   access via library proxy, ILL, author request).

## Honest negatives

Some papers are genuinely paywalled with no OA copy and not present on
Sci-Hub. Don't loop endlessly:
- If Unpaywall says `is_oa: false` AND arXiv search returns nothing AND
  Sci-Hub returns 403 / "no PDF found" on multiple mirrors → that's the
  answer. The same scrape harder will not change it.
- Surface to the user:
  - The DOI you tried.
  - Unpaywall's verdict (verbatim if useful).
  - Suggested next steps: institutional access via proxy, library ILL,
    author email. For older Nobel-laureate work, direct author request
    often succeeds within a day.

## Helper script — what's NOT in it

The helper is deliberately narrow. It does NOT:
- Resolve DOIs to publisher URLs (publisher URLs are paywalled anyway).
- Query Unpaywall, Crossref, or arXiv — these are agent-side concerns.
- Maintain a Sci-Hub mirror list — mirrors change too often for static
  config; the agent picks one based on current discovery.

If you find yourself wanting to add discovery logic to the script, stop:
that's the skill's responsibility, not the script's.

## Common publisher PDF locations (cheat sheet for step 1d)

| Publisher | Where the PDF link lives on the article page |
|---|---|
| Nature / Springer | "Download PDF" button (top right) |
| Science / AAAS | "PDF" link in article tools |
| ACS | "PDF" button near title |
| Elsevier / ScienceDirect | "Download PDF" (often paywalled but worth a shot) |
| Wiley | "PDF" in tools section |
| APS (Phys. Rev. *) | "PDF" in article header — paywalled unless your network has APS sub |
| World Scientific | "PDF" link |
| arXiv | `https://arxiv.org/pdf/<id>` directly |

## Tips

- Always save with a meaningful filename: use `--hint "<firstauthor><year>_<shorttitle>"`. The helper will append `.pdf` if missing.
- The helper verifies PDF magic bytes; if it fails, the URL probably
  pointed at a publisher's "we couldn't find this" HTML page, not a PDF.
- For papers before ~Aug 1991 (cond-mat launch on arXiv), arXiv won't
  have a preprint — go straight to (c) or (e).
