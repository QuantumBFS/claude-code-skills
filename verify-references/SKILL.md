---
name: verify-references
description: Verify and validate bibliography references in BibTeX files by comparing with CrossRef metadata. Use when user asks to check, verify, or validate references.
---

When this skill is invoked, you must:

## Step 0: Pre-check

1. Ask user for:
   - `bib_file` path (e.g., `Biblio/ref.bib`)
   - `tex_dir` path (e.g., `Tex/`)

2. Generate report file path: `<bib_file_dir>/verification_report.md`

3. Check if report already exists:
   - If exists: Use AskUserQuestion tool to ask "Found existing verification report at `<report_path>`. What would you like to do?" with options:
     - "Re-run verification" (description: "Delete existing report and run full verification again")
     - "View existing report" (description: "Read and summarize the existing report without re-running")
   - If user chooses "View existing report": Read and summarize the existing report, then exit
   - If user chooses "Re-run verification" or report doesn't exist: Continue to Step 1

## Step 1: Check Unused References

1. Run: `python ~/.claude/skills/verify-references/check_unused_refs.py <bib_file> <tex_dir>`

2. Parse JSON output and write to report file:
   - Create report with header "# Bibliography Verification Report"
   - Add section "## Unused References"
   - List total references, cited count, uncited count
   - List uncited citation keys

## Step 2: Download CrossRef Metadata

1. Generate output file path: `<bib_file_dir>/ref_crossref.bib`

2. Tell user: "Downloading CrossRef metadata. You can monitor progress in real-time by viewing `<full_path_to_ref_crossref.bib>`"

3. Run: `python -u ~/.claude/skills/verify-references/download_crossref.py <bib_file> <output_file>`
   - Queries CrossRef API for all entries with DOIs
   - Generates a CrossRef version of the bib file for comparison
   - Maintains the same entry order as the original file
   - **Monitor and relay progress**: As the script outputs progress lines like "[1/50] Querying key: DOI", relay these to the user in real-time so they can see the download progress

4. Report progress summary:
   - Total entries processed
   - Entries with DOIs
   - Entries without DOIs (skipped)

## Step 3: Generate Comparison Report

1. Run: `python ~/.claude/skills/verify-references/compare_refs.py <bib_file> <crossref_bib> <report_file>`
   - Use the same `<bib_file_dir>/verification_report.md` from Step 1
   - Compares original bib file with CrossRef version
   - Identifies discrepancies in metadata fields
   - Calculates similarity scores
   - Appends comparison results to the existing report

2. Parse and present the comparison section:
   - Summary statistics
   - Entries with no discrepancies
   - Entries with discrepancies (sorted by similarity)
   - Detailed field-by-field comparison table

## Step 4: Final Summary

1. Read the complete verification report from `<bib_file_dir>/verification_report.md`

2. Provide a concise summary to the user:
   - Number of unused references
   - Number of entries verified against CrossRef
   - Number of entries with discrepancies
   - Key issues found (if any)

3. Tell the user: "Detailed report saved to: `<full_path_to_verification_report.md>`"
   
