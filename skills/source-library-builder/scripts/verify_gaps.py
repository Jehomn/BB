#!/usr/bin/env python3
"""反证校验 — 对评分 1 的源材料反向检索遗漏知识点。

用法:
    python verify_gaps.py book_chapter.txt --known known_topics.json > gaps.md

输入: 评分 1 的书的 pdftotext 输出 + 已知知识点列表（JSON 数组）
输出: Markdown 格式的候选遗漏清单，人工审核后决定是否纳入索引
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from openai import OpenAI


def extract_skeleton(text: str) -> str:
    """从 pdftotext 输出提取轻量骨架：章节标题 + 每段首句。"""
    lines = text.split("\n")
    skeleton_lines = []
    prev_empty = True

    for line in lines:
        stripped = line.strip()
        if not stripped:
            prev_empty = True
            continue

        is_heading = (
            stripped.isupper() and len(stripped) < 80
            or re.match(r"^(Chapter|CHAPTER|第.+章|[IVX]+\.)\s", stripped)
        )

        if is_heading:
            skeleton_lines.append(f"[H] {stripped}")
            prev_empty = False
        elif prev_empty:
            skeleton_lines.append(stripped[:200])
            prev_empty = False

    return "\n".join(skeleton_lines)


def load_known_topics(path: str) -> list[str]:
    """加载已知知识点列表。支持 JSON 数组或纯文本（每行一个）。"""
    p = Path(path)
    if not p.exists():
        print(f"[WARN] 已知知识点文件不存在: {path}", file=sys.stderr)
        return []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if content.startswith("["):
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"[WARN] JSON 解析失败，按纯文本处理: {e}", file=sys.stderr)
            return [line.strip() for line in content.split("\n") if line.strip()]
    else:
        return [line.strip() for line in content.split("\n") if line.strip()]


def query_llm(skeleton: str, known_topics: list[str], api_key: str, model: str) -> str:
    """让 LLM 扫描文本骨架，找出已知列表未覆盖的内容。"""
    if not skeleton.strip():
        return "（文本为空，无法分析）"

    known_str = "\n".join(f"- {t}" for t in known_topics) if known_topics else "（无已知知识点）"

    prompt = f"""你是研究助手。以下是某本书的章节目录和段落首句（骨架）。

已知知识点列表：
{known_str}

请找出这本书中**有实质内容**但知识点列表**未覆盖**的主题。要求：
1. 只列真实存在于文本中的内容，不编造
2. 标注来源章节/段落位置
3. 每个候选用一句话说明为什么值得纳入
4. 如果所有内容都已覆盖，写"未发现遗漏"

格式：
## 候选遗漏项

### [主题名]
- **位置:** 第X章 / 段落Y
- **内容:** 一句话描述
- **纳入理由:** 一句话

---

文本骨架：
{skeleton[:8000]}"""

    client = OpenAI(api_key=api_key, base_url="https://open.bigmodel.cn/api/paas/v4/")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
    )
    return response.choices[0].message.content


def main():
    parser = argparse.ArgumentParser(description="反证校验 — 检索遗漏知识点")
    parser.add_argument("input", help="评分 1 的书的 pdftotext 文本文件")
    parser.add_argument("--known", required=True, help="已知知识点列表（JSON 数组或每行一个的文本文件）")
    parser.add_argument("--api-key", default=None, help="LLM API key（默认读 ZHIPU_API_KEY 环境变量）")
    parser.add_argument("--model", default="glm-4.6", help="LLM 模型名（默认 glm-4.6，骨架扫描不需要 VL）")
    parser.add_argument("--no-llm", action="store_true", help="只输出文本骨架，不调 LLM（调试用）")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ZHIPU_API_KEY")
    if not api_key and not args.no_llm:
        print("错误：需要 API key。设置 ZHIPU_API_KEY 环境变量或用 --api-key", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.input, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except FileNotFoundError:
        print(f"错误：文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    skeleton = extract_skeleton(text)
    known = load_known_topics(args.known)

    print(f"# 反证校验: {Path(args.input).name}", file=sys.stderr)
    print(f"# 已知知识点: {len(known)} 个", file=sys.stderr)
    print(f"# 骨架行数: {len(skeleton.splitlines())}", file=sys.stderr)
    print(file=sys.stderr)

    if args.no_llm:
        print("## 文本骨架（调试模式）")
        print()
        print("```")
        print(skeleton[:5000])
        print("```")
    else:
        result = query_llm(skeleton, known, api_key, args.model)
        print(result)


if __name__ == "__main__":
    main()
