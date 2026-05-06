---
name: download-papers
description: Use when the user asks to download an academic paper or get the PDF — given a URL, DOI, paper title, or citation. Resolves in order: open-web (author homepage, repositories) → Sci-Hub mirrors → arXiv. Triggers on phrases like "download paper", "get me the PDF", "fetch this paper", "get this DOI".
---

# Download Papers

Goal: get the PDF onto the local filesystem with minimum friction. Try in this order — stop at the first hit.

## Resolution order

### 1. Easy open-web hit
Search the web for a freely available copy:
- Google Scholar / general web search for the title; look for `[PDF]` links
- Author's personal homepage / institutional page (often hosts preprints)
- Lab group "Publications" page
- INSPIRE-HEP, NASA ADS, OSTI, ResearchGate (sometimes), university repositories

If a direct PDF URL turns up, fetch it:
```bash
curl -L -o paper.pdf "<URL>"
```

### 2. Sci-Hub
For paywalled DOIs, try Sci-Hub mirrors in order — they rotate availability:
- `https://sci-hub.se/<DOI>`
- `https://sci-hub.st/<DOI>`
- `https://sci-hub.ru/<DOI>`
- `https://sci-hub.ee/<DOI>`

The DOI suffix is appended literally (parentheses and slashes included). Example:
```
https://sci-hub.se/10.1016/0550-3213(92)90424-A
```

Sci-Hub returns an HTML wrapper with an embedded PDF; the actual file lives at a URL inside an `<iframe src="...">` or `<embed src="...">`. Fetch the page, extract that URL, then download:
```bash
curl -sL "https://sci-hub.se/<DOI>" | grep -oE 'src="[^"]*\.pdf[^"]*"' | head -1
```

### 3. arXiv
Search arXiv by title/author. Useful when the published version is paywalled but a preprint exists:
- `https://arxiv.org/abs/<id>` → PDF at `https://arxiv.org/pdf/<id>`
- For papers before ~Aug 1991 (cond-mat launch), arXiv won't have it — stop here and tell the user no PDF was found.

## Common publisher PDF locations

- **Nature / Springer:** "Download PDF"
- **Science / AAAS:** "PDF" in article tools
- **ACS:** "PDF" button near title
- **Elsevier / ScienceDirect:** "Download PDF"
- **Wiley:** "PDF" in tools section
- **APS (Physical Review):** "PDF" in article header
- **World Scientific (Mod. Phys. Lett., Int. J. Mod. Phys.):** "PDF" link; often Sci-Hub-only
- **arXiv:** direct PDF link

## Tips

- Always verify the downloaded file is a valid PDF (`file paper.pdf` should report `PDF document`); Sci-Hub mirrors sometimes serve CAPTCHA HTML when rate-limited.
- If a mirror returns a CAPTCHA page, switch to a different `.se`/`.st`/`.ru` mirror.
- Save to a meaningful filename: `<firstauthor><year>_<shorttitle>.pdf`.
