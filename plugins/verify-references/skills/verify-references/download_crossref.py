#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Download CrossRef metadata for all entries with DOIs in ref.bib
"""

import os
import sys
import re
import json
import urllib.request
import urllib.error
import time

def query_crossref(doi):
    """Query Crossref API for DOI metadata"""
    url = f"https://api.crossref.org/works/{doi}"
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'BibManager/1.0')
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
        if data['status'] != 'ok':
            return None
        return data['message']
    except Exception as e:
        print(f"Error querying {doi}: {e}")
        return None

def crossref_to_bibtex(key, msg):
    """Convert CrossRef message to BibTeX entry"""
    entry_type = msg.get('type', 'article')
    if entry_type == 'journal-article':
        entry_type = 'article'

    lines = [f"@{entry_type}{{{key},"]

    # Title
    if msg.get('title'):
        title = msg['title'][0].replace('{', '\\{').replace('}', '\\}')
        lines.append(f"  title = {{{title}}},")

    # Authors
    if msg.get('author'):
        authors = []
        for author in msg['author']:
            given = author.get('given', '')
            family = author.get('family', '')
            authors.append(f"{family}, {given}" if given else family)
        lines.append(f"  author = {{{' and '.join(authors)}}},")

    # Journal
    if msg.get('container-title'):
        lines.append(f"  journal = {{{msg['container-title'][0]}}},")

    # Volume, number, pages
    if msg.get('volume'):
        lines.append(f"  volume = {{{msg['volume']}}},")
    if msg.get('issue'):
        lines.append(f"  number = {{{msg['issue']}}},")
    if msg.get('page'):
        lines.append(f"  pages = {{{msg['page']}}},")

    # Year
    year = None
    for date_field in ['published', 'published-print', 'published-online']:
        if date_field in msg:
            date_parts = msg[date_field].get('date-parts', [[]])[0]
            if date_parts:
                year = date_parts[0]
                break
    if year:
        lines.append(f"  year = {{{year}}},")

    # Publisher
    if msg.get('publisher'):
        lines.append(f"  publisher = {{{msg['publisher']}}},")

    # DOI and URL
    if msg.get('DOI'):
        lines.append(f"  doi = {{{msg['DOI']}}},")
    if msg.get('URL'):
        lines.append(f"  url = {{{msg['URL']}}}")

    lines.append("}\n")
    return '\n'.join(lines)

def parse_bib_file(filepath):
    """Parse BibTeX file and extract entries with citation keys and DOIs"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = []
    pattern = r'@(\w+)\{([^,]+),([^@]*?)(?=\n@|\Z)'

    for match in re.finditer(pattern, content, re.DOTALL):
        entry_type = match.group(1)
        key = match.group(2).strip()
        body = match.group(3)

        # Extract DOI
        doi_match = re.search(r'doi\s*=\s*\{([^}]+)\}', body, re.IGNORECASE)
        doi = doi_match.group(1).strip() if doi_match else None

        entries.append({'key': key, 'doi': doi, 'type': entry_type})

    return entries

def main():
    if len(sys.argv) != 3:
        print(json.dumps({"error": "Usage: download_crossref.py <input_bib> <output_bib>"}))
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    if not os.path.exists(input_file):
        print(json.dumps({"error": f"Input file not found: {input_file}"}))
        sys.exit(1)

    print("Parsing ref.bib...")
    entries = parse_bib_file(input_file)

    print(f"Found {len(entries)} entries, {sum(1 for e in entries if e['doi'])} with DOIs")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("%---------------------------------------------------------------------------%\n")
        f.write("%-                                                                         -%\n")
        f.write("%-                   CrossRef Downloaded Bibliography                      -%\n")
        f.write("%-                                                                         -%\n")
        f.write("%---------------------------------------------------------------------------%\n\n")

        for i, entry in enumerate(entries):
            if not entry['doi']:
                print(f"[{i+1}/{len(entries)}] Skipping {entry['key']} (no DOI)")
                continue

            print(f"[{i+1}/{len(entries)}] Querying {entry['key']}: {entry['doi']}")
            msg = query_crossref(entry['doi'])

            if msg:
                bibtex = crossref_to_bibtex(entry['key'], msg)
                f.write(bibtex + '\n')
                f.flush()  # Immediately write to disk
            else:
                print(f"  Failed to retrieve metadata")

            time.sleep(0.5)  # Rate limiting

    print(f"\nDone! Results written to {output_file}")

if __name__ == "__main__":
    main()
