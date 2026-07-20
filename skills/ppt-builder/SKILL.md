---
name: ppt-builder
description: Use whenever the user wants to create a professional slide deck (.pptx) from source materials (PDFs, books, documents, research). Triggers include: "make a PPT", "create slides", "build a deck", "generate a presentation", "把这做成PPT", "做课件", "生成幻灯片". Also trigger when the user mentions turning knowledge base / textbook / research into teaching materials, or when they have a large volume of source content to compress into structured slides. Do NOT trigger for simple 1-2 page slides, Google Slides, or general "make it pretty" requests unrelated to structured knowledge-to-slide pipelines.

本技能为父技能：前期资料筹备（策选→索引→精读→内容稿）委托子技能 `source-library-builder` 完成，本技能专注于从内容稿到 PPTX 的排版工程。源码参考 (`references/PPT工程手册.md` + `references/intro-page-template.md`)。

## Agent 分派工作流

课件内容质量的核心瓶颈不在排版，在**内容草稿到用户审阅之间没有质量闸门**。当用户审阅时发现错误，意味着前面所有阶段没有拦截住。本节定义四 Agent 拓扑 + 验证闸门 + Obsidian vault 集成，每次启动 ppt-builder 必须按此流执行。

### 知识源：Obsidian Vault

生成课件内容前，先查 vault 中的已消化笔记。Vault 路径：`H:\Obsidian\Veterinary Knowledge Base`

- 已标 `#digested` 的笔记 → 可直接提取事实/数字/机制
- `#to-digest` 的笔记 → 需先由 Source Agent 深读后更新
- 源书 PDF 路径记录在各笔记的 `file_path` frontmatter 中

**Vault 优先，但不阻塞。** 有 `#digested` 笔记则直接提取；没有则 Source Agent 直接深读原书 PDF 或检索文献。Vault 是加速器，不是闸门——资料在哪就从哪读。

### 四 Agent 拓扑（每个模块）

不允许一个 Agent 从头写到尾。每个模块走完这条链，交一个审一个：

```
Source Agent (pua:p7)          Comparison Agent (pua:p7)         Draft Agent (pua:p7)
  ↓                                ↓                                ↓
深读指定章 → 提取知识点           交叉比对多源 → 标[差异]          Markdown 逐页草稿
  ↓                                ↓                                ↓
输出：该章知识点卡片              输出：差异报告                   输出：内容稿（含引证）
                                                                     ↓
                                                            Humanizer Agent (pua:p7)
                                                                     ↓
                                                             加载 humanizer skill → 去 AI 写作痕迹
                                                                     ↓
                                                             输出：人味化内容稿
                                                                     ↓
                                                              Verifier (pua:verifier)
                                                                     ↓
                                                              自检清单核验 → 不通过打回 Humanizer
                                                                     ↓
                                                              你审阅（最终质量闸门）
```

**每个 Agent 的职责边界**：

| Agent | 输入 | 输出 | 禁做 |
|-------|------|------|------|
| Source Agent | vault 笔记 + PDF 章节范围 | 知识点卡片（每条带 [来源 章.节] + 附图标记：有图则录 `[图 章.节/p.页]`，无图标 `[无图]`）| 不跨书比对，不写幻灯片 |
| Comparison Agent | 多个 Source Agent 的输出 + vault 交叉引用 | 差异报告（标 [差异] + 证据分级 ●●●/●●○/●○○ + 相关性标注）| 不生成新内容，不裁决对错 |
| Draft Agent | 知识点卡片（含附图标记）+ 差异报告 + vault `#digested` 笔记 | Markdown 内容稿（每页一张卡片，含引证角标 + 配图方案）| 不自行决定引用——必须来自上游输入 |
| Humanizer Agent | Draft Agent 输出的内容稿 | 人味化内容稿（去除 AI 写作痕迹，保留事实/引证/数字）| 不改事实、不删引证、不改数字、不改术语——只修文风和句式 |
| Verifier | 人味化内容稿 + 自检清单 | 逐条通过/不通过，标位置 | 不修改内容，只标记 |

### 证据相关性评估（Comparison Agent 执行）

每条证据从七个维度评估相关性。一个维度不匹配标 `[间接]`，两个及以上标 `[弱相关]`，全部匹配标 `[直接]`：

| 维度 | 评估问题 | 不匹配示例 |
|------|---------|-----------|
| 物种 | 研究对象是否为目标物种 | 人医/反刍动物数据用于犬猫 |
| 人群 | 年龄/品种/共病是否与临床场景一致 | 健康实验犬数据用于心衰老年犬 |
| 干预 | 药物/剂量/方案是否一致 | 不同给药途径、配方、剂量范围 |
| 结局 | 测量指标是否为临床关注的结局 | 你关心死亡率，文献只报生化指标 |
| 场景 | 条件是否接近临床实况 | 实验室诱导模型 vs 自然发病 |
| 时效 | 结论在当前是否仍成立 | 1990年代方案可能已被淘汰 |
| 临床可转化性 | 效应量有实际意义吗？典型兽医能落地吗？ | MAP 提 5 mmHg 有 p<0.05 但临床无所谓；或需要 $5 万设备 |

相关性标注格式：`[直接]` / `[间接：物种不匹配]` / `[弱相关：场景、人群不匹配]`

注：临床可转化性合并了临床意义和可行性——两者统一回答「这证据能不能在诊室里用」。

### 图片素材工作流

**文件管理：** 所有图片统一放 `images/` 目录下，不按模块分拆。命名用 `模块序号-描述.后缀`，如 `01-麻醉机回路.png`。

**素材优先级（降序）：**

1. **源书/原文插图** — 最直接、最正确、最快。Source Agent 深读时同步标记 `[图 章.节/p.页]`，记录插图位置和内容描述
2. **文献插图** — 同主题论文中的示意图、流程图、影像等
3. **公开版权素材** — Wikimedia Commons、公共领域医学图库等，需标注来源
4. **占位页** — 以上三者均无，留占位等待用户手工贴图。不可自绘

**配图原则：** 不设数量限制，但不要求每页配图。原文中有插图的都建议配，原文没有的不硬加。

**占位页规范：** 左右排版——左侧虚线框占位区，右侧正文文字。占位区下方写图注，但不写来源（图还没定，来源未知）。代码中用 `contentImgSide` 模板，`img` 字段为空时自动渲染虚线占位框。

**图片与文字互锁：** 图上关键结构/步骤用序号标注，文字讲解中对应 `(图①)` `(图②)`。不用无标注的装饰图。

**格式要求：** PNG（线图/示意图）或 JPG（照片/影像），分辨率 ≥ 150 DPI 对应显示尺寸。不做透明通道（PPT 原生渲染效果差）。

### 验证闸门

Draft Agent 输出内容稿后，先经 Humanizer Agent 过滤 AI 写作痕迹（加载 `humanizer` skill），再由 Verifier Agent 逐条核验以下清单。**不通过 → 打回 Humanizer Agent 修复 → 再核。** 核到全绿才呈现给用户。

| # | 检查项 | 不通过标准 |
|---|--------|-----------|
| 1 | 引证覆盖 | 存在无 `[来源 章节]` 的陈述句 |
| 2 | 数字精度 | 出现"较高""明显""大量""一般"等模糊词 |
| 3 | 差异标注 | 多源数据冲突但未标 `[差异]`（两边都列，不捏造共识）|
| 4 | 缩写展开 | 缩写首次出现未写"中文译名（English Full Name, ABBR）" |
| 5 | 引号规范 | 中文语境出现 ASCII `"` 而非「」 |
| 6 | 孤儿行 | 文字行末尾挂 1–4 个字 |
| 7 | vault 溯源 | 每条关键事实可在 vault `#digested` 笔记中找到对应原文 |
| 8 | 禁止句式 | 出现"值得注意的是""大量研究表明""在临床实践中" |
| 9 | 相关性标注 | 引用 `[间接]` / `[弱相关]` 证据但未在正文点明局限；不可落地的可展示但必须标 `[不可落地·学界常提]` 并简述原因 |
| 10 | 图片来源 | 使用未标注来源的非公开版权图；或试图自绘示意图而非留占位页 |

### 并行模块执行

多模块课件不要串行。每个模块独立走完四 Agent 链：

```
母 Agent（你直接控制，不写代码）
├── 模块1: Source → Comparison → Draft → Humanizer → Verifier → 你审
├── 模块2: Source → Comparison → Draft → Humanizer → Verifier → 你审（与模块1并行）
└── 模块3: Source → Comparison → Draft → Humanizer → Verifier → 你审（与1、2并行）
```

- 用 `Agent` 工具派发 `pua:p7` 子 Agent，`run_in_background: true`
- Humanizer Agent 加载 `humanizer` skill，仅修文风不改事实
- 每个模块的 Prompt 必须包含：源书范围 + vault 笔记路径 + 输出目标（知识点卡片 / 差异报告 / 内容稿 / 人味化内容稿）
- 模块间无依赖关系，完全并行

### 快捷入口

用户说"做 PPT"或"做课件"时，先确认以下三项再启动 Agent 链：

1. **主题和模块划分** — 几个模块？每模块覆盖什么？
2. **源书范围** — 从 vault 的 `1-Reference/Anesthesia/Index.md` 或对应索引页拉取，确认哪些书
3. **输出规格** — 课件用途（讲课/演讲/培训）→ 决定 slide 密度和 notes 深度

确认后即刻按此流执行，不省略任何环节。
---

# PPT-Builder

A streamlined methodology for transforming large source materials into professional, citation-backed slide decks. Born from a successful multi-textbook veterinary anesthesia course project.

## When to Use

This skill applies when ALL of these are true:
- Source materials exist (PDFs, books, documents) in volume (>5 sources or >500 pages)
- A structured multi-page presentation is the goal (>20 slides)
- Content fidelity matters (citations, specific data, cross-referencing)

## The 5-Stage Pipeline (overview)

Don't jump to slide generation. Follow the stages in order:

```
1-4. 前期资料筹备 → 5. 排版工程: Generate PPTX
```

### Stages 1-4 — 前期资料筹备

**委托子技能 `source-library-builder` 完成。** 该技能覆盖完整的 6 阶段流水线：

1. 定范围（PICO/TIS 框架 + 排除清单）
2. 源发现（学术 + 本地 + 网页三线并行）
3. 源筛选（Tier 1/2 分层 + 纳入排除标准）
4. 全量索引（synonyms.yaml + grep 扩召回 + 0-3 评分 + 反证校验）
5. 精读比对（pdftotext 分段提取 + [差异]标注 + 证据分级 ●●●/●●○/●○○）
6. 知识合成（5 压缩操作 → 结构化 Markdown 内容稿）

调用方式：加载 `source-library-builder` skill，明确告知研究主题和输出目标（"用于生成 PPT 课件"）。该技能产出以下文件，其中 `内容稿.md` 是本技能 Stage 5 的唯一入口：

```
项目目录/
├── 研究范围.md
├── 源清单.md
├── synonyms.yaml
├── 索引表.md
├── 差异报告.md
└── 内容稿.md          ← ppt-builder 入口
```

**内容稿格式要求：**
- 每条结论有引用角标 `[1][2]`
- 数字具体，不模糊（"MAP < 60 mmHg 持续 >3min" 而非 "血压过低"）
- 机制按因果链解释："A → B → C"
- 中文引号「」不用 ASCII "
- 缩写首次出现用"中文译名（英文全名，ABBR）"格式
- 禁止句式："值得注意的是""大量研究表明""在临床实践中"
- 搜不到的信息标注"该信息暂缺"

### Stage 5 — Generate PPTX (2-4h/module + iteration)
Use **pptxgenjs direct encoding** (Node.js). Do NOT attempt HTML→PPTX translation — it will fail (CSS cascade pollution, font metric differences, rendering engine incompatibility). This lesson cost 3 failed attempts.

## Architecture: Template-Data Separation

Define 5-7 slide templates once. Express all content as JS data objects. In a past project, this approach generated 109 slides from ~500 lines of code — slide count scales with data, not code.

**Templates** (write once):
| Template | Use case | Key params |
|----------|---------|-----------|
| `contentSlide` | Text + optional tip box | `sec, title, sub, paras[], tip, bodySize` (default 16, ↑ for sparse pages) |
| `contentImgLarge` | Image-top + text-bottom | Same as contentSlide + `img, imgCaption, imgCredit` |
| `contentImgSide` | Left-right split | Same as contentImgLarge + `imgSide` ('left'/'right') |
| `tableSlide` | Data tables | `tbl{h, r, cr}` — headers, rows, column ratios. For <4 rows, consider converting to `contentSlide` to avoid bottom whitespace |
| `cover()` | Title slide | Author, affiliation, module TOC |
| `intro()` | Speaker intro | Apple-style 3-layer photo stack; full code in `references/intro-page-template.md` |
| `modTitle()` | Module divider | Auto-adapts section lists per module |
| `refBooks()` | Bibliography | Grouped reference list with abbreviations |

**Data** (write per slide):
```javascript
{ t:'table', mi:1, pim:7, sec:'Section', title:'Title',
  intro:'...', tbl:{h:[...], cr:[...], r:[[...]]}, refs:[...], pn:0 }
```
`t` = template type, `mi` = module index (color), `pim` = page-in-module (progress bar), `pn` = auto-assigned by counter.

## Critical Constraints

### Whitespace
**Target: <20% whitespace per slide.** Calculate: `(content_bottom - content_top) / (refs_divider - header_bottom)`. Adjust via font sizes, row heights, and spacing — not by adding fluff.

### Typography (Chinese)
- Font: **Microsoft YaHei** globally
- Quotes: 「」 only — ASCII " will break JS string parsing
- **Anti-widow rule:** no text line should end with 1-4 orphan characters. Widen text boxes, use `shrinkText`, or restructure layout. This is the most common bug.
- Page numbers: width ≥ 0.5" (prevents 2-digit wrapping), format with `padStart(2,'0')`

### Text Highlighting (`{{}}` red marker)
- **Red = critical only.** Apply to: safety redlines, key numbers/thresholds, core conceptual distinctions. Never mark: product names, descriptive adjectives (e.g. "single-use", "optional"), routine item names in lists
- **Mark whole semantic units**, not fragments: `{{2–4 J/kg}}` not `2–{{4 J}}/kg`; `{{systolic < 90 mmHg}}` not `systolic < {{90 mmHg}}`
- Red marker validates by asking: "If the learner reads ONLY the red text on this slide, do they get the 3 most important things?" If a marked word fails this test, remove the marker
- Tip box already provides a separate visual layer — don't double-highlight tip content unless truly life-critical

### Abbreviation First-Use
- Body text first occurrence: `ABBR（中文全称）` — e.g. `VF（心室颤动）`. English full names belong in the glossary page, not inline — they bloat body text and trigger char-budget clipping
- Tip box: same format as body, but abbreviations already introduced in body don't need re-expansion
- Glossary page carries all abbreviations with Chinese + English full names — the authoritative reference

### Tip Content Rules
- tip = clinical pearl layer. Body says "what this is", tip says "what to watch out for when doing it"
- **Put in tip**: evidence limitations (no RCT/consensus only), safety warnings, specific doses/thresholds, species-specific traps, team coordination points
- **Do NOT put in tip**: core definitions/classifications, routine steps, mechanism explanations, lengthy background, full reference info — these belong in body or notes

### Progress Bar
- `shrinkText: true, wrap: false` — never let narrow-segment labels wrap
- Dynamic text color: dark when fill <45%, white when ≥45% (text is centered)
- Module transitions: `addProgressBar(slide, modIdx, pim)` — seamless across merged modules

### Color System
Use a per-module accent color for module identity. Content slides share neutral palette (`#172228` body, `#F6F8F9` background). Cover/intro/ref pages use `#F5F5F7` (Apple warm light gray). Clinical tips: amber `#FFF8E1` background + `#F0A500` left border.

### References
Divider line at `refsY - 0.08` serves as layout boundary — all content must end ≥0.04" above it. Per-page refs at 8.5pt, full format, ≤5 per page.

## Common Pitfalls

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| HTML→PPTX looks wrong | Browser and PPT engines are fundamentally different | Skip translation; use pptxgenjs directly |
| Content feels thin | Wrote JS before content draft | Write Markdown draft first, review it, then code |
| Page numbers duplicated | Hardcoded page numbers | Use global counter in `main()`; auto-assign |
| Whitespace >30% | Fonts too small, rows too short | Scale up: table body 13pt at 0.46" row height |
| Footer overlap | Enlarged content without checking boundary | Refs divider = safety line; verify all elements above it |
| Module title bar invisible | Module color = slide background on cover | Use lighter tint for cover TOC bars |
| Two-column text disappears | Nested arrays from `.map(supText)` | Flatten with paragraph breaks: `forEach + push(...supText(t, size))` |

## Content Presentation Rules

Choosing the right visual format for the content type:

| Content type | Best format | Rationale |
|-------------|------------|-----------|
| A vs B comparison | `tableSlide` | Side-by-side columns let learners compare at a glance — text paragraphs force mental toggling |
| Equipment / item inventory | `tableSlide` with category column | Grouped rows + category labels → scannable; avoids wall-of-text list |
| Thin page (<3 body lines) | Merge into adjacent page, or convert to A/B comparison table | Sparse slides feel incomplete; a comparison table fills space productively |
| Mechanism / theory | `contentSlide` with `{{}}` on key concepts | Red draws eye to the 3-4 takeaway points embedded in explanatory paragraphs |
| Visual object (anatomy, UI, device) | `contentImgSide` with annotated photo | Left text + right image → learner reads then sees, natural eye path |

Universal decision flow: *"Can this content be expressed as rows and columns?"* If yes → use a table. If no → *"Does it have a visual subject?"* If yes → `contentImgSide`. Otherwise → `contentSlide`.

### Slide Text Density — The "Lecture Card" Rule

A slide is a **lecture prompt card**, not a textbook page. The learner scans it in 3-5 seconds while listening to the instructor.

**Hard limits**:
| Parameter | Pure text page | Image page | Table page |
|-----------|---------------|-----------|------------|
| Max `paras` entries | 5 | 3 | intro ≤2 sentences |
| Max chars per entry | 50 | 50 | phrase-level only |
| Max `{{}}` per page | 5 (M4/emergency: 6) | 5 | 2 (intro+tip combined) |
| Sentence structure | Single clause, ≤2 lines | Single clause, ≤2 lines | N/A |

**What goes on the slide**: Key facts, numbers, distinctions, and safety redlines. Phrases, not sentences. Bullet-style, not paragraph-style.

**What goes to speaker notes**: All explanatory text, mechanisms, pathophysiology, academic context, data sources, clinical reasoning. Use the `notes` field in data objects and the `makeNotes()` function to route content to `s.addNotes()`.

**`notes` field pattern**:
```javascript
// In data:
{ t:'content', ..., paras:['{{关键概念}}：最核心的一句话。'], 
  notes:'【详细讲解——讲师用】\n\n1. 完整背景...\n\n2. 机制解释...\n\n3. 临床含义...',
  ... }

// In makeNotes():
function makeNotes(data) {
  if (data.notes) { n.push(data.notes); }  // priority: explicit notes
  else { /* fallback: auto-generate from paras+tip */ }
  // refs always appended
}
```

**Anti-patterns to eliminate**:
- ❌ Nested numbering (①②③) inside a single paragraph string → ✅ split into separate `paras` entries
- ❌ Parenthetical explanations in table cells → ✅ move to `notes` or simplify to bare term
- ❌ Complex sentences with 逗号-separated clauses → ✅ one clause per `paras` entry
- ❌ `{{}}` on routine terms like product names or adjectives → ✅ reserved for safety redlines and key thresholds only

### Content Traceability

Every fact on every slide must be traceable to a digested reference note in the Obsidian vault. Before writing slide content:
1. Read the relevant digested note in `H:\Obsidian\Veterinary Knowledge Base\`
2. Extract the specific fact/number/mechanism from the note
3. Write the slide text as a condensed version
4. Put the full source context into `notes`
5. Add the citation to `refs[]`

This ensures the PPT content doesn't drift from the source material across iterations.

### Reference Digestion — Exhaustive Principle

When building content for a module, **digest ALL cited reference books completely** before writing slide data. Do not stop after 2-3 books "feeling it's enough." Every reference cited in `refs[]` must have its relevant chapters fully extracted and written into the Obsidian vault. Cross-reference the digested notes against slide content to verify accuracy and completeness. See memory `thorough-reference-digestion` for the full principle.

### Whitespace Discipline
- Target: **<10% unused vertical space** between last content element and the refs divider
- For genuinely sparse pages (source materials have nothing more to add): **increase body font to 18pt** via `bodySize: 18`, add a descriptive `sub`, or convert thin tables to paragraph form
- **Never invent content** to pad whitespace — every added sentence must trace to the source content draft or cited reference. "This page looks empty" is a layout problem, not a content gap
- Thin tableSlide (<4 data rows): convert to `contentSlide` — a 2-row table wastes ~3" of vertical space by design. The same information as structured paragraphs fills the page naturally

### Printable Checklist Pattern

When a module teaches equipment/procedure/setup that learners will perform in real life:
1. **Teaching slide**: categorized `tableSlide` with columns for item, category, requirement, notes
2. **Separate file** for printable materials: checklists, handouts, worksheets output as standalone .pptx — never appended as bonus slides inside the training deck. Bonus slides lack progress bars and consistent backgrounds, breaking the learner's visual flow

## Table Template Rules

All `tableSlide` instances must follow these rules to prevent overflow:

### Dynamic Sizing
- **introH**: compute via `neededH(fontSize, estLines(text, w, fontSize), lineSpacingMultiple, pad)` — never hardcode `0.80`
- **rowH**: `Math.min(0.40, (REF_Y - GAP - y - 0.42) / dataRows)`, floor at `0.30`. If rowH would drop below 0.30, split the table into multiple pages in the data layer
- **colW**: must sum to 1.0 in column ratios; total table width = slide width - 2×GX

### Cell Safety
- Every table cell must include `shrinkText: true` — prevents horizontal text overflow past column boundaries
- `shrinkText` and `lineSpacingMultiple` are mutually exclusive (iron rule) — never set both on the same cell
- Zebra row fill color must differ from slide background by ≥4 hex digits (e.g. bg `F6F8F9` → even rows ≤ `EEF1F5`)

### Table Pagination
- When items are equivalent with no progressive relationship: split evenly (13 items → 7+6, not 10+3)
- When items have logical hierarchy: split at category boundaries, but keep page sizes within ±1 row of each other
- Each split page reuses the same `sec` field, with `title` adding `（1/2）` / `（2/2）` suffix

## Build Discipline
- Output file: `{ProjectName}.pptx` — semantic name, no version suffix
- Iteration versions: v2 → v3 only, delete the oldest when >3 exist. Never let version numbers drift to v10
- No orphan slides: every slide in the PPTX must belong to the content flow (cover→intro→glossary→refs→modTitle→contentPages). Printable extras go in separate files

## Iteration Pattern

1. Build 3-4 sample slides first — validate templates, colors, spacing
2. Build one full module — validate content density and flow
3. Build remaining modules — templates already proven
4. Merge independent module files only after all are validated

Each build cycle: `node build.js` → open PPTX → review → fix 2-3 issues → repeat. Don't batch 10 changes.

## Output Standards

- All data citations traceable to source PDFs
- Reference books use full names (Chinese title or complete English title). Never abbreviate to "author name + edition" form (e.g., "Lumb & Jones 6th") — author-only abbreviations hide what the book is about
- Final output: `{项目名}.pptx` (semantic name, no version suffix)
- Git version control for all text/code assets (not PDF binaries)

## Lessons Learned (2026-07 困难气道项目实战)

### pptxgenjs 段落间距
- 单个 `addText` 内 `\n` 是 PowerPoint 软换行，不产生段间距。**必须用 `\n\n`（双换行）** 创建可见段落分隔
- 逐段独立 `addText` + Y 轴累加方案在无溢出保护时会导致内容冲出幻灯片——**禁止使用**
- `shrinkText: true` 会压制自定义行距和段距
- 段间分隔 fontSize 建议为正文的 0.8 倍

### 进度条
- `pim` 是 0-based 模块内页码，`pim / pages` 导致首页 0 填充、末页非满色。**必须用 `(pim + 1) / pages`**
- `MOD_DEFS.pages` 必须与模块实际 slide 数量对齐，否则段宽比例失真
- 父库模板内部调用裸名 `addProgressBar`，monkey-patch `T.addProgressBar` **无效**——必须自写模板函数
- 图文页（contentImgSide/ImgLarge）也需单独覆盖

### 表格页
- 节号 `sec` 与标题 `title` 必须合并为**同行等大**渲染，禁止分两行
- 包装父模板（传空 `sec`）会留死空间——必须自写 `tableSlide`
- 所有三种模板（contentSlide / tableSlide / contentImgSide）必须统一进度条和 sec+title 合并

### 引用系统
- 正文每条 paras 末尾必须有 `[1][2]...[N]` 角标，连接底部 refs。角标不加粗、不标红、与正文同字号
- 期刊文献引用必须含：作者 + 文章标题（双引号）+ 期刊全名 + 年份卷号页码
- 参考书目只列有**实质性内容贡献**的书。仅做术语验证的不配进书目
- 原文截图放正文区（contentImgSide），不在脚注放缩略图

### 行文语言禁令
- 禁止 `→` 箭头——用逗号递进、导致、进而、继而、发展为、随即替代
- 禁止 `患者`——统一用 `动物`
- slide 可见文字禁止设计元语言：本课件、设计规格、A型页、B型页、提词器
- 禁止 AI 句式：值得注意的是、大量研究表明、在临床实践中、由浅入深
- 不展示"每模块多少页"等课程设计信息

### 颜色与视觉
- 设计令牌 `C` 对象必须含 `tipBgM1` 供父模板兼容，否则降级为黑色 `#000000`
- Logo 占位框比例锁 5.72:1，虚线框，不嵌实际图片
- 总结构图用横向色带时间线（非卡片式），左侧模块名+右侧简介，不标页数、不写设计逻辑

### 构建与文件
- WPS 云盘锁 `.pptx` 文件时用时间戳回退文件名
- 临时 `.pptx` 不提交 git

## Reference

## Deep Reference

When the user needs deeper guidance, read `references/PPT工程手册.md` — the complete 18-chapter engineering manual bundled with this skill. It covers: photo layering, whitespace calculation, capnography handling, knowledge compression, aesthetic vocabulary building, trust calibration, failure decision logs, and the full 13-pattern meta-methodology. This file travels with the skill — no external dependencies.

**Read the manual BEFORE doing any of these:**
- Designing a cover, intro page, or closing page (manual §三, §八 for design tokens and photo techniques; also `references/intro-page-template.md` for the canonical Apple-style 3-layer stack code)
- Setting up the progress bar system (manual §四 for state machine and color-switching logic)
- Troubleshooting whitespace (manual §七 for calculation methodology)
- Establishing a book abbreviation standard (manual §九 for naming principles)
- Debugging a layout bug you can't explain (manual §十一 for the 12-item trap table)
- Starting a new module from scratch (manual §一 for the full 5-stage pipeline details)
- Planning file organization or naming conventions (manual §十 for version management patterns)
- Evaluating whether to automate a visual element or leave it manual (manual §十四, pattern 14.9 Escape Hatch)
