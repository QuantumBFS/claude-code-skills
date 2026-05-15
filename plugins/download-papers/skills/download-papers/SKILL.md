---
name: download-papers
description: Use when the user asks to download an academic paper or get the PDF — given a URL, DOI, paper title, or citation. Uses the bundled helper script as the default path for DOI/URL/PDF downloads, with open-web and arXiv lookup as fallbacks for title-only requests. Triggers on phrases like "download paper", "get me the PDF", "fetch this paper", "get this DOI".
---

# Download Papers

Goal: get the PDF onto the local filesystem with minimum friction. The helper script is the default path once you have a DOI, URL, or direct PDF link.

## Default workflow

1. If the user gives a DOI, URL, or direct PDF link, run:
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/download_paper.py "<DOI_OR_URL>" --out-dir papers
   ```
2. Read the JSON output. On `status: "ok"`, report the `local_path`. On `status: "error"`, summarize the attempted URLs and try the fallback workflow below.
3. If the user gives only a title or citation, search for a DOI or PDF URL first, then pass that result to the helper script.

The helper resolves DOI or URL inputs, extracts embedded PDF links from HTML pages, prints JSON with `status`, `pdf_url`, and `local_path`, and verifies that the downloaded file starts with the PDF magic bytes.

## Fallback workflow

### 1. Find an open-web source
Search the web for a freely available copy:
- Google Scholar / general web search for the title; look for `[PDF]` links
- Author's personal homepage / institutional page (often hosts preprints)
- Lab group "Publications" page
- INSPIRE-HEP, NASA ADS, OSTI, ResearchGate (sometimes), university repositories

When a direct PDF URL or article URL turns up, pass it to the helper script.

### 2. arXiv
Search arXiv by title/author. Useful when the published version is unavailable but a preprint exists:
- `https://arxiv.org/abs/<id>` → PDF at `https://arxiv.org/pdf/<id>`
- For papers before ~Aug 1991 (cond-mat launch), arXiv won't have it — stop here and tell the user no PDF was found.

## Common publisher PDF locations

- **Nature / Springer:** "Download PDF"
- **Science / AAAS:** "PDF" in article tools
- **ACS:** "PDF" button near title
- **Elsevier / ScienceDirect:** "Download PDF"
- **Wiley:** "PDF" in tools section
- **APS (Physical Review):** "PDF" in article header
- **World Scientific (Mod. Phys. Lett., Int. J. Mod. Phys.):** "PDF" link
- **arXiv:** direct PDF link

## Tips

- Always verify the downloaded file is a valid PDF; the helper script checks PDF magic bytes.
- Save to a meaningful filename: `<firstauthor><year>_<shorttitle>.pdf`.
