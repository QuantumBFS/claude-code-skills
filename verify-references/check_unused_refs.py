#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查 .bib 文件中未被引用的参考文献
"""

import os
import re
import sys
import json
from collections import defaultdict

def extract_bib_keys(bib_file):
    """从 .bib 文件中提取所有参考文献的 citation keys"""
    with open(bib_file, 'r', encoding='utf-8') as f:
        content = f.read()
    return re.findall(r'@\w+\{([^,\s]+),', content)

def count_citations_in_file(file_path, bib_keys):
    """统计单个 .tex 文件中每个参考文献的引用次数"""
    citation_counts = defaultdict(int)
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 移除注释行
    content = re.sub(r'(?<!\\)%.*', '', content)

    # 匹配 \cite 命令
    matches = re.findall(r'\\cite[pns]*\{([^}]+)\}', content)
    for match in matches:
        for key in match.split(','):
            key = key.strip()
            if key in bib_keys:
                citation_counts[key] += 1

    return citation_counts

def main():
    if len(sys.argv) != 3:
        print(json.dumps({"error": "Usage: check_unused_refs.py <bib_file> <tex_dir>"}))
        sys.exit(1)

    bib_file = sys.argv[1]
    tex_dir = sys.argv[2]

    if not os.path.exists(bib_file):
        print(json.dumps({"error": f"BIB file not found: {bib_file}"}))
        sys.exit(1)

    if not os.path.exists(tex_dir):
        print(json.dumps({"error": f"TEX directory not found: {tex_dir}"}))
        sys.exit(1)

    # 提取参考文献 keys
    bib_keys = extract_bib_keys(bib_file)

    # 统计引用
    total_citations = defaultdict(int)
    for filename in os.listdir(tex_dir):
        if filename.endswith('.tex'):
            file_path = os.path.join(tex_dir, filename)
            citations = count_citations_in_file(file_path, bib_keys)
            for key, count in citations.items():
                total_citations[key] += count

    # 找出未被引用的文献
    uncited = [key for key in bib_keys if key not in total_citations]

    # 输出 JSON 结果
    result = {
        "total_refs": len(bib_keys),
        "cited_refs": len(total_citations),
        "uncited_refs": len(uncited),
        "uncited_keys": uncited
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
