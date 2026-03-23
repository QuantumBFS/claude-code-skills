#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare bibliographic information between ref.bib and ref_.bib
"""

import sys
import os
import re
from difflib import SequenceMatcher

def parse_bib_entries(filepath):
    """Parse BibTeX file and extract entries with key fields"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        content = ''.join(lines)

    entries = {}
    pattern = r'@(\w+)\{([^,]+),([^@]*?)(?=\n@|\Z)'

    for match in re.finditer(pattern, content, re.DOTALL):
        key = match.group(2).strip()
        body = match.group(3)

        # Find line number
        line_num = content[:match.start()].count('\n') + 1

        entry = {'key': key, 'line': line_num}

        # Extract fields
        for field in ['title', 'author', 'journal', 'volume', 'number', 'pages', 'year', 'doi', 'url']:
            # Try matching with quotes: field = "..."
            field_pattern = rf'{field}\s*=\s*"([^"]*)"'
            match = re.search(field_pattern, body, re.IGNORECASE | re.DOTALL)
            if match:
                value = match.group(1).strip()
                # Remove outer braces if present
                if value.startswith('{') and value.endswith('}'):
                    value = value[1:-1].strip()
                entry[field] = value
                continue

            # Try matching with braces: field = {...}
            field_pattern = rf'{field}\s*=\s*\{{'
            match = re.search(field_pattern, body, re.IGNORECASE)
            if match:
                start = match.end()
                brace_count = 1
                i = start
                while i < len(body) and brace_count > 0:
                    if body[i] == '{':
                        brace_count += 1
                    elif body[i] == '}':
                        brace_count -= 1
                    i += 1
                value = body[start:i-1].strip()
                # Remove outer braces if present
                if value.startswith('{') and value.endswith('}'):
                    value = value[1:-1].strip()
                entry[field] = value

        entries[key] = entry

    return entries

def normalize(text):
    """Normalize text for comparison"""
    if not text:
        return ""
    # Remove extra spaces, convert to lowercase
    text = re.sub(r'\s+', ' ', text.lower())
    # Remove special LaTeX commands
    text = re.sub(r'\\[a-z]+\{([^}]*)\}', r'\1', text)
    text = re.sub(r'[{}]', '', text)
    return text.strip()

def similarity(a, b):
    """Calculate similarity ratio between two strings"""
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()

def compare_entries(orig, crossref):
    """Compare two entries and return differences"""
    issues = []
    details = {}
    min_sim = 1.0

    for field in ['title', 'author', 'journal', 'volume', 'number', 'pages', 'year']:
        orig_val = orig.get(field, '')
        cross_val = crossref.get(field, '')

        if not orig_val and not cross_val:
            continue

        if not orig_val:
            # Skip number field if missing in original
            if field == 'number':
                continue
            issues.append(f"  {field}: MISSING in original")
            details[field] = {'orig': '', 'cross': cross_val, 'issue': 'MISSING', 'sim': 0.0}
            min_sim = 0.0
            continue

        if not cross_val:
            continue

        sim = similarity(orig_val, cross_val)

        if sim < 0.9:
            issues.append(f"  {field}:")
            issues.append(f"    Original:  {orig_val}")
            issues.append(f"    CrossRef:  {cross_val}")
            issues.append(f"    Similarity: {sim:.2%}")
            details[field] = {'orig': orig_val, 'cross': cross_val, 'sim': sim}
            min_sim = min(min_sim, sim)

    return issues, details, min_sim

def main():
    if len(sys.argv) != 4:
        print(json.dumps({"error": "Usage: compare_refs.py <orig_bib> <crossref_bib> <output_report>"}))
        sys.exit(1)

    orig_file = sys.argv[1]
    cross_file = sys.argv[2]
    report_file = sys.argv[3]

    if not os.path.exists(orig_file):
        print(json.dumps({"error": f"Original file not found: {orig_file}"}))
        sys.exit(1)

    if not os.path.exists(cross_file):
        print(json.dumps({"error": f"CrossRef file not found: {cross_file}"}))
        sys.exit(1)

    print("Parsing files...")
    orig_entries = parse_bib_entries(orig_file)
    cross_entries = parse_bib_entries(cross_file)

    print(f"Found {len(orig_entries)} entries in ref.bib")
    print(f"Found {len(cross_entries)} entries in ref_.bib\n")

    print("=" * 80)
    print("COMPARISON RESULTS")
    print("=" * 80)

    report_data = []
    entries_with_doi = 0
    entries_without_doi = 0

    for key in sorted(orig_entries.keys()):
        if key in cross_entries:
            entries_with_doi += 1
            issues, details, min_sim = compare_entries(orig_entries[key], cross_entries[key])
            if issues:
                print(f"\n[{key}]")
                for issue in issues:
                    print(issue)
                doi = orig_entries[key].get('doi', cross_entries[key].get('doi', ''))
                url = orig_entries[key].get('url', cross_entries[key].get('url', ''))
                report_data.append({'key': key, 'doi': doi, 'url': url, 'details': details, 'min_sim': min_sim})
        else:
            entries_without_doi += 1

    entries_with_issues = len(report_data)
    entries_no_issues = entries_with_doi - entries_with_issues

    print("\n" + "=" * 80)
    print(f"Total entries with discrepancies: {entries_with_issues}")
    print("=" * 80)

    # Sort by similarity (lowest first)
    report_data.sort(key=lambda x: x['min_sim'])

    # Generate markdown report
    with open(report_file, 'a', encoding='utf-8') as f:
        f.write("\n\n## CrossRef Metadata Comparison\n\n")
        f.write("### Summary\n\n")
        f.write(f"- **Total entries in ref.bib**: {len(orig_entries)}\n")
        f.write(f"- **Entries with DOI (in ref_.bib)**: {entries_with_doi}\n")
        f.write(f"- **Entries without DOI (skipped)**: {entries_without_doi}\n")
        f.write(f"- **Entries with no discrepancies**: {entries_no_issues} ({entries_no_issues/entries_with_doi*100:.1f}%)\n")
        f.write(f"- **Entries with discrepancies**: {entries_with_issues} ({entries_with_issues/entries_with_doi*100:.1f}%)\n\n")
        f.write("### Detailed Comparison\n\n")
        f.write("Entries are sorted by similarity (lowest first).\n\n")
        f.write("| # | Citation Key | Field | Original | CrossRef | Similarity | URL |\n")
        f.write("|---|--------------|-------|----------|----------|------------|-----|\n")

        idx = 1
        for item in report_data:
            key = item['key']
            line = orig_entries[key].get('line', 0)
            doi = item['doi']
            url = item['url']
            link = f"https://doi.org/{doi}" if doi else url
            key_md = f"[{key}](ref.bib#L{line})"
            url_md = f"[url]({link})" if link else ""

            for field, info in item['details'].items():
                orig = info['orig'].replace('|', '\\|').replace('\n', ' ')[:60]
                cross = info['cross'].replace('|', '\\|').replace('\n', ' ')[:60]
                sim = info.get('sim', 0.0)
                sim_str = "MISSING" if info.get('issue') == 'MISSING' else f"{sim:.0%}"
                f.write(f"| {idx} | {key_md} | {field} | {orig} | {cross} | {sim_str} | {url_md} |\n")
            idx += 1

    print(f"\nMarkdown report saved to: {report_file}")

if __name__ == "__main__":
    main()
