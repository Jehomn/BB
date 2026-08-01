#!/usr/bin/env python3
"""
兽医学文献快报 Markdown → PDF 转换脚本 (ReportLab版)
用法: python md_to_pdf.py input.md output.pdf --title "报告标题" --author "作者"
依赖: pip install reportlab
"""

import sys
import os
import re
import argparse

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable
from reportlab.platypus.frames import Frame
from reportlab.platypus.doctemplate import PageTemplate
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# ── Super/Sub normalizer ──
# Chinese fonts (SimSun/YaHei) lack glyphs for Unicode super/subscript chars
# (e.g. ² ₃ CO₂). Convert them to ReportLab XML tags so they render as normal
# chars positioned up/down — no special glyph needed.

_SUPER_MAP = {
    '¹': '1', '²': '2', '³': '3',
    '⁰': '0', '⁴': '4', '⁵': '5', '⁶': '6',
    '⁷': '7', '⁸': '8', '⁹': '9',
    '⁺': '+', '⁻': '-', '⁼': '=', '⁽': '(', '⁾': ')',
    'ⁿ': 'n',
    'ʰ': 'h', 'ʲ': 'j', 'ʷ': 'w', 'ˠ': 'ɣ',
    'ᴬ': 'A', 'ᴮ': 'B', 'ᴰ': 'D', 'ᴱ': 'E',
    'ᴳ': 'G', 'ᴴ': 'H', 'ᴵ': 'I', 'ᴶ': 'J',
    'ᴷ': 'K', 'ᴸ': 'L', 'ᴹ': 'M', 'ᴺ': 'N',
    'ᴼ': 'O', 'ᴾ': 'P', 'ᴿ': 'R', 'ᵀ': 'T',
    'ᵁ': 'U', 'ᵂ': 'W', 'ᵃ': 'a', 'ᵇ': 'b',
    'ᵈ': 'd', 'ᵉ': 'e', 'ᵍ': 'g', 'ᵐ': 'm',
    'ᵒ': 'o', 'ᵖ': 'p', 'ᵗ': 't', 'ᵘ': 'u',
    'ᵛ': 'v',
}

_SUB_MAP = {
    '₀': '0', '₁': '1', '₂': '2', '₃': '3',
    '₄': '4', '₅': '5', '₆': '6', '₇': '7',
    '₈': '8', '₉': '9',
    '₊': '+', '₋': '-', '₌': '=', '₍': '(', '₎': ')',
    'ₐ': 'a', 'ₑ': 'e', 'ₒ': 'o', 'ₓ': 'x',
    'ₕ': 'h', 'ₖ': 'k', 'ₗ': 'l', 'ₘ': 'm',
    'ₙ': 'n', 'ₚ': 'p', 'ₛ': 's', 'ₜ': 't',
}


def _translate_super(text):
    return ''.join(_SUPER_MAP.get(c, c) for c in text)


def _translate_sub(text):
    return ''.join(_SUB_MAP.get(c, c) for c in text)


def normalize_super_sub(text):
    """Convert Unicode super/sub chars and HTML <sup>/<sub> tags to
    ReportLab <super>/<sub> XML tags. Run on every text block before rendering."""

    # Step 1: HTML <sup>...</sup> → <super>...</super>
    text = re.sub(r'<sup>(.*?)</sup>', r'<super>\1</super>', text, flags=re.DOTALL)
    # <sub> is already valid ReportLab XML, leave as-is

    # Step 2: Unicode superscript runs → <super>normal</super>
    super_chars = ''.join(_SUPER_MAP.keys())
    text = re.sub(f'[{re.escape(super_chars)}]+',
                  lambda m: f'<super>{_translate_super(m.group(0))}</super>', text)

    # Step 3: Unicode subscript runs → <sub>normal</sub>
    sub_chars = ''.join(_SUB_MAP.keys())
    text = re.sub(f'[{re.escape(sub_chars)}]+',
                  lambda m: f'<sub>{_translate_sub(m.group(0))}</sub>', text)

    return text


# ── Color Palette ──
DEEP_BLUE    = HexColor("#0a1e3c")
DARK_GREEN   = HexColor("#2c5f7c")
LIGHT_BLUE   = HexColor("#4b7d9e")
PURPLE       = HexColor("#5e8ba8")
DARK_GRAY    = HexColor("#2c3e50")
LIGHT_GRAY   = HexColor("#95a5a6")
VERY_LIGHT   = HexColor("#f4f7fa")
CARD_BG      = HexColor("#f4f7fa")
CARD_BORDER  = HexColor("#2c5f7c")
HUMAN_BG     = HexColor("#fdf3e0")
HUMAN_BORDER = HexColor("#f5a22e")
KEY_BG       = HexColor("#e8f0f8")
TABLE_HEAD   = HexColor("#0a1e3c")

# ── Chinese font registration ──
_FONT_NAME = "Helvetica"

try:
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    _FONT_NAME = 'STSong-Light'
except Exception:
    pass

for _fp in [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]:
    if os.path.exists(_fp):
        try:
            pdfmetrics.registerFont(TTFont('ChineseFont', _fp))
            _FONT_NAME = 'ChineseFont'
            break
        except Exception:
            pass


# ── Styles ──
def build_styles():
    s = {}
    s['cover_title'] = ParagraphStyle(
        'CoverTitle', fontName=_FONT_NAME, fontSize=28, leading=36,
        textColor=DEEP_BLUE, alignment=TA_CENTER, spaceAfter=8*mm)
    s['cover_subtitle'] = ParagraphStyle(
        'CoverSubtitle', fontName=_FONT_NAME, fontSize=14, leading=18,
        textColor=LIGHT_GRAY, alignment=TA_CENTER, spaceAfter=6*mm)
    s['cover_meta'] = ParagraphStyle(
        'CoverMeta', fontName=_FONT_NAME, fontSize=10, leading=14,
        textColor=LIGHT_GRAY, alignment=TA_CENTER, spaceAfter=4*mm)
    s['h1'] = ParagraphStyle(
        'H1', fontName=_FONT_NAME, fontSize=20, leading=26,
        textColor=DEEP_BLUE, spaceBefore=4*mm, spaceAfter=1.5*mm)
    s['h2'] = ParagraphStyle(
        'H2', fontName=_FONT_NAME, fontSize=14, leading=19,
        textColor=DARK_GREEN, spaceBefore=3*mm, spaceAfter=1.5*mm)
    s['h3'] = ParagraphStyle(
        'H3', fontName=_FONT_NAME, fontSize=12, leading=16,
        textColor=LIGHT_BLUE, spaceBefore=2*mm, spaceAfter=1*mm)
    s['h4'] = ParagraphStyle(
        'H4', fontName=_FONT_NAME, fontSize=11, leading=15,
        textColor=PURPLE, spaceBefore=2*mm, spaceAfter=1*mm)
    s['body'] = ParagraphStyle(
        'Body', fontName=_FONT_NAME, fontSize=10.5, leading=18.5,
        textColor=DARK_GRAY, alignment=TA_LEFT,
        spaceBefore=1.5*mm, spaceAfter=1.5*mm)
    s['card_text'] = ParagraphStyle(
        'CardText', fontName=_FONT_NAME, fontSize=10, leading=17,
        textColor=DARK_GRAY, alignment=TA_LEFT,
        spaceBefore=2*mm, spaceAfter=2*mm)
    s['key_finding'] = ParagraphStyle(
        'KeyFinding', fontName=_FONT_NAME, fontSize=11, leading=16,
        textColor=DARK_GRAY, alignment=TA_CENTER)
    s['table_cell'] = ParagraphStyle(
        'TableCell', fontName=_FONT_NAME, fontSize=9, leading=12,
        textColor=DARK_GRAY)
    s['table_header'] = ParagraphStyle(
        'TableHeader', fontName=_FONT_NAME, fontSize=9.5, leading=13,
        textColor=white)
    s['small'] = ParagraphStyle(
        'Small', fontName=_FONT_NAME, fontSize=9, leading=13,
        textColor=LIGHT_GRAY)
    return s


# ── Block builders ──

def make_card(text, styles, bg=CARD_BG, border_color=CARD_BORDER):
    """Create a card: left-border block with background."""
    text = normalize_super_sub(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    p = Paragraph(text, styles['card_text'])
    t = Table([[p]], colWidths=[460])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LINEBEFORE', (0, 0), (0, 0), 4, border_color),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    return t


def make_key_finding(text, styles):
    """Create the summary-title box (概括标题)."""
    text = text.replace('**概括标题：**', '').replace('**概括标题:**', '').replace('**结论概览：**', '').replace('**结论概览:**', '').replace('**一句话结论：**', '').replace('**一句话结论:**', '').strip()
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = normalize_super_sub(text)
    p = Paragraph(text, styles['key_finding'])
    t = Table([[p]], colWidths=[460])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), KEY_BG),
        ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LINEBEFORE', (0, 0), (0, 0), 1.5, DARK_GREEN),
        ('LINEAFTER', (0, 0), (0, 0), 1.5, DARK_GREEN),
        ('BOX', (0, 0), (-1, -1), 1.5, DARK_GREEN),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def make_table(rows, styles):
    """Build evidence matrix table from parsed rows."""
    # Filter separator rows (|---|---|)
    filtered = []
    for row in rows:
        if all(c.strip().replace('-', '').replace(':', '').strip() == '' for c in row):
            continue
        filtered.append(row)

    if len(filtered) < 2:
        # Not a real table, render as text
        text = '<br/>'.join([' | '.join(r) for r in filtered])
        return Paragraph(text, styles['body'])

    # Build header + body
    processed = []
    for i, row in enumerate(filtered):
        pr = []
        for cell in row:
            cell = normalize_super_sub(cell.strip())
            cell = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', cell)
            if i == 0:
                pr.append(Paragraph(cell, styles['table_header']))
            else:
                pr.append(Paragraph(cell, styles['table_cell']))
        processed.append(pr)

    ncols = len(processed[0])
    avail = 460
    col_w = [avail / ncols] * ncols

    table = Table(processed, colWidths=col_w, repeatRows=1)
    cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), TABLE_HEAD),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor("#bdc3c7")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(processed)):
        if i % 2 == 0:
            cmds.append(('BACKGROUND', (0, i), (-1, i), VERY_LIGHT))
    table.setStyle(TableStyle(cmds))
    return table


def make_heading(text, level, styles):
    """Build a heading with bottom border.
    Deliberately NOT wrapped in KeepTogether — forcing a heading + HR to the
    next page when they don't fit leaves a large white gap on the current page.
    A heading at the bottom of a page with its HR on the next page is less
    disruptive to reading flow than a half-empty page."""
    s = styles.get(f'h{level}', styles['body'])
    text = normalize_super_sub(text)
    p = Paragraph(text, s)
    elements = [p]
    if level == 1:
        elements.append(HRFlowable(width="100%", thickness=2, color=DEEP_BLUE, spaceAfter=3*mm))
    elif level == 2:
        elements.append(HRFlowable(width="100%", thickness=0.8, color=DARK_GREEN, spaceAfter=2*mm))
    return elements


# ── Header/Footer ──
def header_footer(canvas, doc, report_title):
    canvas.saveState()
    if doc.page > 1:
        canvas.setFont(_FONT_NAME, 8)
        canvas.setFillColor(LIGHT_GRAY)
        canvas.drawString(20*mm, A4[1] - 18*mm, f"{report_title}  |  兽医学文献快报")
        canvas.line(20*mm, A4[1] - 20*mm, A4[0] - 20*mm, A4[1] - 20*mm)
        canvas.drawCentredString(A4[0]/2, 15*mm, f"第 {doc.page} 页")
        canvas.setStrokeColor(DARK_GREEN)
        canvas.line(20*mm, 17*mm, A4[0] - 20*mm, 17*mm)
    canvas.restoreState()


# ── Line-by-line state machine parser ──

def parse_and_build(lines, styles):
    """Parse markdown lines and yield ReportLab flowables."""
    i = 0
    n = len(lines)

    # State for accumulating multi-line elements
    blockquote_buf = []       # accumulating > lines
    table_rows = []           # accumulating | rows
    body_buf = []             # accumulating non-special lines

    def flush_body():
        nonlocal body_buf
        if body_buf:
            text = '<br/>'.join(body_buf).strip()
            if text:
                text = normalize_super_sub(text)
                text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
                text = text.replace('\n- ', '<br/>• ').replace('\n1. ', '<br/>1. ')
                yield Paragraph(text, styles['body'])
            body_buf = []

    def flush_blockquote():
        nonlocal blockquote_buf
        if blockquote_buf:
            # Join, strip > prefixes
            joined = '<br/>'.join(blockquote_buf)
            text = '\n'.join(blockquote_buf)
            # Determine card type
            stripped = text.strip()
            if '人医参照' in stripped:
                bg, bc = HUMAN_BG, HUMAN_BORDER
            else:
                bg, bc = CARD_BG, CARD_BORDER
            yield make_card(joined, styles, bg=bg, border_color=bc)
            yield Spacer(1, 2*mm)
            blockquote_buf = []

    def flush_table():
        nonlocal table_rows
        if table_rows:
            yield make_table(table_rows, styles)
            yield Spacer(1, 4*mm)
            table_rows = []

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # ── H1 ──
        if stripped.startswith('# ') and not stripped.startswith('## '):
            yield from flush_blockquote()
            yield from flush_table()
            yield from flush_body()
            text = stripped[2:].strip()
            yield from make_heading(text, 1, styles)
            i += 1
            continue

        # ── H2 ──
        if stripped.startswith('## ') and not stripped.startswith('### '):
            yield from flush_blockquote()
            yield from flush_table()
            yield from flush_body()
            text = stripped[3:].strip()
            yield from make_heading(text, 2, styles)
            i += 1
            continue

        # ── H3 ──
        if stripped.startswith('### ') and not stripped.startswith('#### '):
            yield from flush_blockquote()
            yield from flush_table()
            yield from flush_body()
            text = stripped[4:].strip()
            yield from make_heading(text, 3, styles)
            i += 1
            continue

        # ── H4 ──
        if stripped.startswith('#### '):
            yield from flush_blockquote()
            yield from flush_table()
            yield from flush_body()
            text = stripped[5:].strip()
            yield from make_heading(text, 4, styles)
            i += 1
            continue

        # ── Table separator or row ──
        if stripped.startswith('|'):
            yield from flush_blockquote()
            yield from flush_body()
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            table_rows.append(cells)
            i += 1
            continue

        # ── Blockquote ──
        if stripped.startswith('>'):
            yield from flush_table()
            yield from flush_body()
            content = stripped[1:].strip()
            blockquote_buf.append(content)
            i += 1
            continue

        # ── 概括标题 / 结论概览 / 一句话结论 (special bold-only line) ──
        if (stripped.startswith('**概括标题：') or stripped.startswith('**结论概览：') or stripped.startswith('**一句话结论：')) and not stripped.startswith('>'):
            yield from flush_blockquote()
            yield from flush_table()
            yield from flush_body()
            yield make_key_finding(stripped, styles)
            yield Spacer(1, 3*mm)
            i += 1
            continue

        # ── "临床行动建议" bold header within body ──
        if stripped.startswith('**临床行动建议：**'):
            yield from flush_blockquote()
            yield from flush_table()
            yield from flush_body()
            body_buf.append(stripped)
            i += 1
            continue

        # ── Horizontal rule ──
        if stripped == '---' or stripped == '***' or stripped == '___':
            yield from flush_blockquote()
            yield from flush_table()
            yield from flush_body()
            yield HRFlowable(width="100%", thickness=0.4, color=HexColor("#d5dbdb"),
                             spaceBefore=4*mm, spaceAfter=4*mm)
            i += 1
            continue

        # ── Normal line ──
        yield from flush_blockquote()
        yield from flush_table()
        if stripped == '':
            # Empty line: flush body paragraph
            yield from flush_body()
        else:
            body_buf.append(stripped)
        i += 1

    # End of file: flush everything
    yield from flush_blockquote()
    yield from flush_table()
    yield from flush_body()


# ── Main ──

def extract_meta(lines):
    """Extract metadata line (starts with > and contains 检索)."""
    for line in lines:
        s = line.strip().lstrip('>').strip()
        if any(kw in s for kw in ['检索时间', '检索平台', '研究类型']):
            return s
    return ''


def md_to_pdf(input_path, output_path, title="兽医学文献快报", author="Jehomn Bea"):
    with open(input_path, 'r', encoding='utf-8') as f:
        md_text = f.read()

    all_lines = md_text.split('\n')
    styles = build_styles()
    meta_line = extract_meta(all_lines)

    # Find report title from first H1
    report_title = title
    for line in all_lines:
        s = line.strip()
        if s.startswith('# ') and not s.startswith('## '):
            report_title = s[2:].strip()
            break

    # ── Build story ──
    story = []

    # Cover page
    story.append(Spacer(1, 60*mm))
    story.append(Paragraph(report_title, styles['cover_title']))
    story.append(Paragraph("兽医学文献快报", styles['cover_subtitle']))
    if meta_line:
        story.append(Paragraph(meta_line, styles['cover_meta']))
    story.append(HRFlowable(width="50%", thickness=1.5, color=DARK_GREEN, spaceAfter=6*mm))
    story.append(Paragraph(f"作者: {author}", styles['cover_meta']))
    story.append(PageBreak())

    # Skip the first H1 in body (it's on the cover)
    body_lines = []
    first_h1_found = False
    for line in all_lines:
        s = line.strip()
        if not first_h1_found and s.startswith('# ') and not s.startswith('## '):
            first_h1_found = True
            continue
        body_lines.append(line)

    # Parse body and build
    for flowable in parse_and_build(body_lines, styles):
        story.append(flowable)

    # ── Build PDF ──
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=25*mm, bottomMargin=20*mm,
        title=report_title, author=author)

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    template = PageTemplate(
        id='main', frames=[frame],
        onPage=lambda c, d: header_footer(c, d, report_title))
    doc.addPageTemplates([template])
    doc.build(story)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"[OK] PDF 已生成: {output_path} ({size_kb:.1f} KB)")


def main():
    parser = argparse.ArgumentParser(description="兽医学文献快报 Markdown → PDF")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--title", default=None)
    parser.add_argument("--author", default="Jehomn Bea")
    args = parser.parse_args()
    md_to_pdf(args.input, args.output, title=args.title or "兽医学文献快报", author=args.author)


if __name__ == "__main__":
    main()
