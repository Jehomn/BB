#!/usr/bin/env python3
"""同义词扩召回 — 用 synonyms.yaml 在 pdftotext 输出中全量匹配知识点。

用法:
    python grep_synonyms.py synonyms.yaml input.txt > matches.json
    python grep_synonyms.py synonyms.yaml input.txt --format markdown > matches.md

输入: synonyms.yaml + pdftotext 输出的纯文本
输出: JSON（默认）或 Markdown 格式的匹配结果
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("需要 PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def load_synonyms(path: str) -> list[dict]:
    """解析 synonyms.yaml，返回 [{concept, en_variants, zh_variants, note}] 列表。"""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data:
        return []
    entries = []
    for concept, info in data.items():
        if info is None:
            continue
        entries.append({
            "concept": concept,
            "en_variants": info.get("en", []),
            "zh_variants": info.get("zh", []),
            "note": info.get("note", ""),
        })
    return entries


def build_pattern(entry: dict) -> re.Pattern | None:
    """将同义词表条目编译为正则。空变体列表返回 None。"""
    all_variants = entry["en_variants"] + entry["zh_variants"]
    if not all_variants:
        return None
    escaped = [re.escape(v) for v in all_variants]
    combined = "|".join(escaped)
    return re.compile(combined, re.IGNORECASE)


def find_page(lines: list[str], match_line_idx: int) -> int | None:
    """从匹配行向上搜索分页标记（^L 或 Form Feed）。"""
    for i in range(match_line_idx, max(match_line_idx - 10, 0), -1):
        if "\f" in lines[i]:
            page_match = re.search(r"(\d+)", lines[i])
            if page_match:
                return int(page_match.group(1))
    return None


def grep_synonyms(synonyms_path: str, text_path: str) -> dict:
    """主逻辑：对文本跑全部同义词匹配。"""
    entries = load_synonyms(synonyms_path)
    if not entries:
        return {"source": text_path, "matches": [], "error": "同义词表为空"}

    with open(text_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    source_name = Path(text_path).name
    results = {"source": source_name, "matches": []}

    for entry in entries:
        pattern = build_pattern(entry)
        if pattern is None:
            continue
        matched_lines = []
        matched_variants = set()
        snippets = []

        for i, line in enumerate(lines):
            if pattern.search(line):
                matched_lines.append(i + 1)  # 1-based line numbers
                for v in entry["en_variants"] + entry["zh_variants"]:
                    if re.search(re.escape(v), line, re.IGNORECASE):
                        matched_variants.add(v)
                snippets.append(line.strip()[:200])

        if matched_lines:
            merged = []
            group_start = matched_lines[0]
            prev = matched_lines[0]
            for ln in matched_lines[1:]:
                if ln - prev <= 3:
                    prev = ln
                else:
                    merged.append((group_start, prev))
                    group_start = ln
                    prev = ln
            merged.append((group_start, prev))

            page = find_page(lines, matched_lines[0] - 1)

            results["matches"].append({
                "concept": entry["concept"],
                "variants_matched": sorted(matched_variants),
                "line_ranges": merged,
                "page": page,
                "note": entry["note"],
                "snippet_preview": snippets[:3],
            })

    results["total_matches"] = len(results["matches"])
    return results


def format_markdown(results: dict) -> str:
    """将匹配结果格式化为 Markdown。"""
    lines = [f"# 同义词匹配结果: {results['source']}", ""]
    lines.append(f"**命中知识点数:** {results['total_matches']}")
    lines.append("")

    for m in results["matches"]:
        ranges_str = ", ".join(f"{s}-{e}" for s, e in m["line_ranges"])
        page_str = f"p.{m['page']}" if m["page"] else "N/A"
        lines.append(f"## {m['concept']}")
        lines.append(f"- **行号:** {ranges_str}")
        lines.append(f"- **页码:** {page_str}")
        lines.append(f"- **命中变体:** {', '.join(m['variants_matched'])}")
        if m["note"]:
            lines.append(f"- **备注:** {m['note']}")
        lines.append("")
        for snippet in m["snippet_preview"]:
            lines.append(f"> {snippet}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="同义词扩召回")
    parser.add_argument("synonyms", help="synonyms.yaml 文件路径")
    parser.add_argument("input", help="pdftotext 输出的文本文件")
    parser.add_argument("--format", choices=["json", "markdown"], default="json",
                        help="输出格式（默认 json）")
    args = parser.parse_args()

    results = grep_synonyms(args.synonyms, args.input)

    if args.format == "markdown":
        print(format_markdown(results))
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
