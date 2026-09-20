---
name: vet-lit-review
description: |
  兽医文献研究报告Skill。检索文献，提取核心证据，输出排版精美的PDF研究报告。
  支持用户自定检索域：兽医为主+人医参照（默认）、人医为主+兽医现状、纯兽医、纯人医。
  触发场景：兽医/人医临床问题研究、疾病诊疗证据查询、药物/麻醉方案对比、文献综述、循证医学决策支持、机制性药理综述。
  触发词：研究一下、查一下文献、证据如何、有没有最新研究、做个文献综述、帮我找找关于XX的文献、XX是什么研究现状、快速综述、详细的文献研究。
  不用于简单的名词解释、非学术性问答。
---

# 兽医文献研究报告

你正在执行一次兽医文献研究（Veterinary Literature Research Report）。最终产出一份**排版精美的PDF研究报告**。报告字数无上限，按主题需要完整展开，不以篇幅压缩内容。

## 前置准备

### 环境确认

依赖：`pip install reportlab markdown requests`（或 `pip install reportlab markdown requests --break-system-packages`）

**Python 路径**：系统可能有多个 Python 版本。执行脚本前先确认可用 Python：
- 先试 `python3`，再试 `python`，都不可用则检查 `C:\Python314\python.exe` 或 `where python`
- 用确认可用的 Python 路径执行所有脚本命令

**网络环境**：在中国大陆访问 PubMed Entrez API、Semantic Scholar、学术期刊网站时，需要 VPN/代理。检索前执行快速连通性检查：

```bash
python -c "import urllib.request; r=urllib.request.urlopen('https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmax=1&term=dog&retmode=json', timeout=10); print('PubMed OK' if r.status==200 else f'Status {r.status}')"
```

如果超时或返回错误，**提醒用户打开 VPN 后重试**。PubMed API 不通时不要继续检索——所有后续数据源都依赖外网。

检查 `scripts/md_to_pdf.py` 和 `scripts/lit_search.py` 可用。

### 明确研究问题

收到用户输入后，确认以下信息。用户已经给得足够明确就不追问，直接开始：
1. **研究主题**：具体的临床问题/药物/疾病/手术方案
2. **关注的方向**（可选）：有没有特别想关注的临床维度？
3. **时间范围**（可选）：默认近5年。机制性/药理性主题（受体、解剖、经典药物机制）不受近5年限制，检索全部年份——经典机制文献多在1990s-2010s
4. **检索域**（可选）：默认兽医为主+人医参照。用户可指定：
   - `兽医为主`（默认）：PubMed + veterinary[sb]，人医作为参照补充
   - `人医为主`：PubMed 不加 veterinary filter，优先检索人医数据库（Cochrane/PubMed Clinical Queries），兽医学作为现状补充
   - `纯兽医`：仅检索兽医文献
   - `纯人医`：仅检索人医文献

---

## 第一步：问题解析

把用户问题拆成结构化检索单元，**先写下来再搜**：

- **PICO 拆解**（临床问题）：患者/问题(P)、干预(I)、对照(C)、结局(O)
- **关键词组**：中英文各一套，含同义词和 MeSH 词
- **检索范围**：默认近5年，用户可指定；机制性主题检索全部年份
- **检索策略笔录**：写下主要检索式，避免漫无目的搜

### 查询构建原则（关键）

PubMed 对短查询响应最好。实测经验：

- ✅ 5-8 个关键词：`brachycephalic syndrome dog surgery palatoplasty` → 25 篇
- ❌ 15+ 个关键词：`dog brachycephalic airway obstruction BOAS diagnosis surgery treatment palatoplasty` → 0 篇

**策略**：把复杂 PICO 拆成 2-3 个短查询，每个查询聚焦一个子问题。例如：
- 查询1（诊断）：`brachycephalic dog diagnosis exercise test plethysmography`
- 查询2（手术）：`brachycephalic syndrome dog surgery palatoplasty`
- 查询3（预后）：`brachycephalic dog postoperative outcome complications`

每个短查询单独调用 `lit_search.py`，最后合并去重。脚本内置查询长度提示（>12词会警告）。

---

## 第二步：文献检索与筛选

### 2.1 运行检索脚本

**检索域适配：**

| 检索域 | 命令行 | 说明 |
|--------|--------|------|
| 兽医为主 / 纯兽医 | `python scripts/lit_search.py --query "..." --max 30 --text` | 默认加 veterinary[sb]，无需额外 flag |
| 人医为主 / 纯人医 | `python scripts/lit_search.py --query "..." --max 30 --text --no-vet-filter` | 移除 veterinary filter，检索全领域文献 |

检索词本身不受域影响——PICO 关键词不变，变的只是是否加 veterinary 子集过滤。

每个子查询运行一次，使用 `--text` 模式直接输出可读文献列表：

```bash
python scripts/lit_search.py --query "[短查询1]" --max 30 --text
python scripts/lit_search.py --query "[短查询2]" --max 30 --text
```

输出格式：每篇文献包含 PMID、作者、年份、期刊、标题、摘要（前300字）、研究类型。

**可用输出模式**：
- `--text`：全文摘要模式（默认推荐，用于筛选文献）
- `--brief`：仅标题+类型（用于快速扫描）
- 不加 flag：JSON 模式（用于程序化处理）

**如果 PubMed 返回 0 结果**：
脚本已内置自动降级：PubMed vet filter 返回 0 时自动用 `--no-vet-filter` 重试一次。若仍为 0：
1. 缩短查询词（删除次要关键词，只留 3-5 个核心词）
2. 换用更通用的同义词（如 `surgery` 替代 `palatoplasty`）
3. 尝试 `"[疾病/药物]"[MeSH Terms]` 的 MeSH 词检索

**S2 限流说明**：Semantic Scholar 可能返回 HTTP 429，脚本已内置指数退避重试（起始 5s，最大 20s）。不依赖 S2 —— PubMed 是主源。

### 2.2 补搜指南源

根据主题获取权威指南。**优先用 PubMed 检索**（WebFetch 在部分环境可能不可用）：

| 来源 | 首选方式（PubMed） | 备选（WebFetch） |
|------|-------------------|-----------------|
| WSAVA | `"WSAVA"[org] AND guideline[ptyp]` | wsava.org/guidelines |
| ACVIM | `"consensus statement"[tiab] AND "J Vet Intern Med"[journal]` | — |
| ISFM/AAFP | `guideline[ptyp] AND "J Feline Med Surg"[journal]` | — |
| AAHA | `"AAHA"[org] AND guideline[ptyp]` | aaha.org/guidelines |
| RECOVER | PubMed: `recover[tiab] AND cpr[tiab] AND veterinary[sb]` | recoverinitiative.org |
| IVIS | — | ivis.org（仅 WebFetch） |

WebFetch 不可用时的通用替代：直接在 PubMed 搜索 `"[主题词]"[tiab] AND (guideline[ptyp] OR "consensus"[tiab]) AND veterinary[sb]`。

### 2.2b 人医指南源（人医为主/纯人医模式追加）

| 来源 | 首选方式（PubMed） | 备选（WebFetch） |
|------|-------------------|-----------------|
| Cochrane | `"[topic]" AND cochrane[ta]` | cochranelibrary.com |
| NICE | `"[topic]"[tiab] AND "NICE"[org]` | nice.org.uk/guidance |
| PubMed Clinical Queries | 在 PubMed 直接使用 Clinical Queries filter（therapy/diagnosis/etiology/prognosis） | — |
| 各专科学会 | `"[disease]"[tiab] AND guideline[ptyp] NOT veterinary[sb]` | — |

### 2.3 筛选文献

按纳入/排除标准筛选：

**纳入：**
- 兽医学：RCT、观察性研究、病例系列、系统综述/荟萃分析、临床指南（WSAVA/AAHA/ACVAA/ISFM/AAFP/RECOVER/ACVIM）、病例报告（罕见病/新技术）、叙述性综述（权威作者/高被引）
- 比较医学：动物模型研究，需有明确临床转化价值
- 人类医学：仅当兽医直接证据不足，或作为横断对比参照（必须标注来源域差异）

**排除：**
- 纯体外实验（in vitro only）
- 会议摘要（最近6个月内且无全文替代的除外）
- 非同行评议的个人博客/自媒体
- 人类医学纯临床研究，无动物/比较医学关联性

符合纳入标准的高质量文献**全部保留**进入报告，不对数量做人为限制。如需人医参照，追加检索（不加 veterinary filter）。

---

## 第三步：全文获取

筛选完成后，对入选的每篇文献逐篇获取全文。获取不到全文的，抓取 PubMed 完整结构化摘要。

**先分清两件事：文本（供阅读提取）和 PDF（交付物）。** `fetch_fulltext.py` 只解决前者——它取的是 XML/摘要文本，不产出 PDF 文件。用户要"原文"时指的是后者，必须走 `fetch_pdf.py`。

### 3.0 判定"拿不到"之前，必须先排除三种伪失败

**这是本技能最容易翻车的地方，2026-09-20 实际踩坑：把「返回 HTML」当成「没有 PDF」，导致 4 篇本可获取的文献被误报为拿不到，用户连续两次纠正。**

三种"看起来失败其实能拿到"的响应：

| 响应特征 | 实际是什么 | 正确做法 |
|---------|-----------|---------|
| ~1.8 KB，标题 `Preparing to download ...` | **PMC 的 PoW 挑战页**，解算约 13 ms | 非 headless 浏览器打开 PDF 直链 → 等 viewer 挂载 → 从 `.pdf` 那个 frame 里 `fetch(location.href)` 取字节。headless 拿不到 |
| ~1.4 KB，`<title>avma</title>` 之类的最小 SPA 壳 | **出版商下载页由 JS 加载真文件**（AVMA 等） | 在浏览器里**点** `Download PDF` 链接，用 `expect_download` 捕获，不要用 HTTP 直接请求那个 URL |
| 记录页正常、文件端点返回挑战页 | DSpace/ZORA 的 bitstream 反爬 | 记录页 + 文件端点是两套防护，分别判断；文件端点被拒≠没有开放版 |

**已被实测证伪的三条错误推理（对照 2026-09-20 的实际结果）：**

| 我当时的推理 | 实际 |
|---|---|
| `fetch_fulltext.py` 返回 `abstract_only` → 这篇拿不到原文 | 4 篇里有 4 篇能拿到。**`abstract_only` 只说明文本提取没走通，与 PDF 可得性无关** |
| Unpaywall `is_oa: false` + `locations: 0` → 付费墙 | Waldron 2025 在这两个库里都是 closed，出版商页面写着 `Free access` |
| HTTP 返回 HTML → 没有 PDF | PMC 返回的是 1817B 的 PoW 挑战页（可解），AVMA 返回的是 1444B 的 JS 壳（可点） |

**铁律：**

1. **判成功只看魔数 `%PDF-`。** HTTP 200、`content-type: application/pdf`、非零体积都不算数——Chrome 的 PDF viewer 会给你 536 字节的扩展外壳，PMC 挑战页是 1817 字节，SPA 壳是 1444 字节。
2. **元数据只用来"找"，绝不用来"判"。** Unpaywall / OpenAlex 的 `is_oa: false`、`oa_status: closed`、`locations: 0` **不能**证明没有开放版。**最终必须以出版商/来源页面的实际状态为准**（页面上找 `Free access` / `Open access` / `Restricted access` 徽章）。
3. **失败必须说清是哪种失败。** "内容不存在"和"我取不到"是两回事，前者可下结论，后者不能。报告里禁止把后者写成前者。**说"没有开放版"之前，必须先在出版商页面看到 `Restricted access`。**

### 3.0.1 PMC 取 PDF 的已验证序列

PMC 的 `/pdf/` 端点先返回 PoW 挑战页，解算约 13 ms。**可用的序列（2026-09-20 手动验证通过）：**

1. `headless=False` 启动（**headless 下必然失败**，PMC 直接 block）
2. 访问 `/pdf/` 直链 → 轮询等 cookie `cloudpmc-viewer-pow` 出现
3. 回到文章页 `https://pmc.ncbi.nlm.nih.gov/articles/<PMCID>/`
4. 在**页面上下文**里 `fetch(pdf_url, {credentials:'include'})` → 取 base64 → 解出 `%PDF-`

**不要用这两条路**：① 顶层页面的 `fetch`（拿到 1817B 挑战页）；② `ctx.request`（同样被拦）。必须走页面上下文。

**注意 PMC 限流**：短时间内反复测试会触发，表现为文章页 `goto` 超时或响应体积异常（如 358B）。**触发后停止重试**，等冷却，不要在限流状态下继续判定"拿不到"。

**`fetch_pdf.py` 的 PMC 分支为尽力而为**：出版商分支（读徽章 + 点击捕获）是稳定路径；PMC 分支依赖前述序列，在被限流时会失败。**PMC 分支失败 ≠ 该篇不存在开放版**，脚本会如实报出原因。

### 3.1 取 PDF 原文（交付物）

```bash
python scripts/fetch_pdf.py --pmids "PMID1,PMID2,..." --outdir "<任务路径>/原文" --email "you@example.com" --manifest manifest.json
```

优先级链（每一步都以 `%PDF-` 验证）：

| 优先级 | 来源 | 判据 |
|--------|------|------|
| 1 | PMC OA | Europe PMC 记录 `hasPDF=Y` → 浏览器解 PoW → 取 frame 字节 |
| 2 | 出版商页面 | 页面徽章 `Free access` / `Open access` → 点下载按钮捕获 |
| 3 | 机构库绿色 OA | 记录页与文件端点分别验证 |

脚本对每篇输出 `source`（PMC / publisher / —）、`badge`（free / open / restricted）、`reason`（失败原因原文）。**`badge=free` 而 Unpaywall 报 closed 时以 badge 为准。**

**默认非 headless**（PMC 的 PoW 在 headless 下必然失败）。`--headless` 仅供调试。

### 3.2 取文本（供阅读提取）

```bash
python scripts/fetch_fulltext.py --pmids "PMID1,PMID2,..." --output papers_full.json
```

脚本按以下优先级尝试获取全文：

| 优先级 | 来源 | 方式 | 说明 |
|--------|------|------|------|
| 1 | PubMed Central (PMC) | E-utils elink → 解析 PMC XML | 提取引言/方法/结果/讨论/结论各章节 |
| 2 | Europe PMC | REST API `fullTextXML` | 实际下载 JATS 全文 XML（比 NCBI `?report=xml` 更可靠，后者常解析失败）；命中率约 1/3，付费墙文献降级为摘要 |
| 3 | Unpaywall | DOI API | 查找合法 OA 版本（含预印本/机构仓储） |
| 4 | PubMed 降级 | E-utils efetch | 完整结构化摘要（不截断，含 Objectives/Methods/Results/Conclusions 分段） |

`--email` 参数可选但推荐提供，用于 Unpaywall 礼貌访问。

**输出结构** (`papers_full.json`)：
```json
[
  {
    "pmid": "12345678",
    "title": "...",
    "authors": ["Last FM", ...],
    "journal": "...",
    "year": "2024",
    "doi": "10.xxx/yyy",
    "access_status": "full_text | abstract_only",
    "access_source": "PMC (PMC123456) | PubMed",
    "abstract": "完整摘要，无截断...",
    "pub_types": ["..."],
    "mesh_terms": ["..."],
    "full_text_sections": {
      "pmc_id": "PMC123456",
      "abstract": "...",
      "introduction": "...",
      "methods": "...",
      "results": "...",
      "discussion": "...",
      "conclusions": "..."
    }
  }
]
```

`access_status` 为 `full_text` 时，`full_text_sections` 包含各章节内容；为 `abstract_only` 时该字段为 `null`，使用 `abstract` 字段。

### 3.3 用人类可读模式审阅

```bash
python scripts/fetch_fulltext.py --pmids "..." --text
```

`--text` 模式直接输出每篇论文的全文/摘要内容到终端，方便阅读和提取要点。

### 3.4 逐文献提取

逐篇阅读 `papers_full.json` 中各篇内容，提取以下四项。**证据强度分级标准全文件仅此一处**，第四步成文时引用本节，不要再复制一份：

- 研究设计类型 + 样本量 + 对象特征
- 核心发现（1-2句，带关键数字）
- 临床价值判断（1句）
- 证据强度标记：
  - **强（●●●）**：多中心RCT、高质量系统综述/Meta分析、权威指南推荐
  - **中（●●○）**：单中心RCT、高质量观察性研究、样本充足的病例对照
  - **弱（●○○）**：小型RCT(n<30)、病例系列、专家共识、回顾性研究

全文获取的论文重点关注方法学细节和讨论中的局限性；仅获取摘要的论文如实标注获取限制。

---

## 第四步：按模板成文

严格遵循 `references/report-template.md` 的骨架。报告结构：

```
封面页
结论概览（根据证据量灵活调整，完整呈现核心发现）
一页总览（证据矩阵表 + 临床行动建议）
分区证据卡片（按主题维度分卡，含参照卡片；卡数以讲清楚为准，不设上限）
入选文献详览（全部入选文献的完整摘要+全文要点，按篇逐一呈现）
研究动向
研究缺口
结论与思考（四段式：临床建议/矛盾与张力/盲区/参照启发）
来源（全部文献标注PMID/DOI + 检索时间 + 检索平台）
```

**人医为主模式**时，"人医参照卡片"替换为"兽医现状卡片"，其余结构不变。

每篇入选文献的提取内容与证据强度分级，统一按「3.4 逐文献提取」的四项 + 分级标准执行，本处不另立一套。

---

## 第五步：PDF生成

成文保存为 `[主题].md`，运行转换：

```bash
python scripts/md_to_pdf.py "[主题].md" "[主题].pdf" --author "Jehomn Bea"
```

脚本使用 ReportLab 生成 PDF，自动生成封面（标题+副标题+作者+检索信息）、页眉页脚、证据矩阵表（海军蓝表头）、证据卡片（钢蓝左边框）、人医参照卡片（琥珀金左边框）、结论概览高亮框。

**封面副标题不再硬编码**，由 `extract_subtitle()` 读 MD 自己的声明，优先级：`**副标题：**X` > `> … 研究类型：X` > 裸加粗类型行 `**X**` > H1 里的类型词 > 文件名里的类型词。含「快报」→「兽医学文献快报」，含「研究报告」→「兽医文献研究报告」，全都读不到才回落到默认「兽医文献研究报告」。**报告类型务必在 MD 里声明清楚**，否则副标题会跟着文件名走。

### PDF 生成后：弹出资源管理器

PDF 生成完成后，用全局脚本定位输出文件：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\realj\.claude\reveal.ps1" "<反斜杠完整路径>\[主题].pdf"
```

**禁止**直接调 `explorer /select,...`：经 bash 调用时 MSYS 会破坏引号解析，explorer 的 `/select` 解析失败后回退打开默认目录，表现为"弹桌面/弹文档"，且目标文件不被选中。

- 已有资源管理器窗口停在该目录时，脚本只闪动原窗口，不新开。
- 同任务同目录多产物**只弹一次**，定位主产物（PDF 优先）；MD 走 Typora 打开，不重复弹窗。
- 路径必须反斜杠。

---

## 写作风格

### 核心原则

"看完第1页就能做决策。"

### 风格规则

| 规则 | 说明 |
|------|------|
| 数字优先 | 不说"效果更好"，说"呼吸暂停风险降低38%，RR=0.62" |
| 一句一事 | 每句话只传递一个信息点 |
| 无背景铺陈 | 不开场介绍疾病背景/流行病学，直接进入证据 |
| 结论先行 | 每个卡片/段落第一句就是结论 |
| 证据强度每一处都标 | 强/中/弱 + 一句话理由 |
| 不确定性直接说 | 不模糊、不回避，"目前证据不能回答这个问题" |

### 人医参照写法

必须标注来源域差异，格式固定：

> **人医参照：** Cochrane系统综述（2023）显示丙泊酚在儿童麻醉中呼吸暂停发生率18-30%。兽医学尚无同等质量数据。**跨物种外推需谨慎**。

### 兽医现状写法（人医为主模式）

格式固定：

> **兽医现状：** [兽医学同领域现有证据简述]。**兽医学证据目前[充足/有限/缺乏]**，[具体说明差距或可借鉴方向]。

### 术语规范（用户强制原则）

兽医专业文本走术语层，不走口语层。英文 "dog" 一律译为**犬**，不译"狗"。

| 禁用（口语） | 使用（专业） |
|-------------|-------------|
| 狗 | 犬 |
| 小狗 / 大狗 | 幼犬 / 成犬、大型犬 |
| 猫狗 / 狗猫 | 犬猫 |
| 狗狗、狗子 | 犬 |

- 猫无此语域分裂，直接写"猫"。
- 组合词用专业形式：患犬、公犬、母犬、老龄犬、幼犬、实验犬、比格犬、犬只、犬瘟热、犬咬伤。
- 例外仅三种，且必须带引号或标明出处：引号内直接引语（主人原话、新闻标题）、文献标题原文、正在讨论口语用法本身。
- 命名与正文一致：报告文件名叫"犬猫XX"，正文就不得出现"猫狗""狗猫"。

### 缩写规范（用户强制原则）

- 首次出现：**"缩写ABC（英文全称。中文译名）"**。示例："BOAS（Brachycephalic Obstructive Airway Syndrome。短头阻塞性气道综合征）"
- 英文全称与中文译名之间用句号分隔，不写逗号
- 第二次及之后：全部保留缩写，不再展述
- 标题中也遵守：标题首次出现的缩写同样展述，后文标题可沿用缩写
- 不预设读者知道任何缩写，哪怕兽医通用缩写（如 CBC、NSAID）也须首次展述

### 禁区

- 套话："综上所述""值得注意的是""不难发现""在当今AI快速发展的时代"
- 空洞词："赋能""抓手""打造""说白了""本质上""换句话说"
- 不写"需要更多研究"，写"目前最缺X类型的证据"
- 不写"可能""或许"软化语气，除非不确定性本身就是结论
- 不写叙事性背景（"XX病在兽医临床中越来越常见"——删）
- 搜不到的信息写"该信息暂缺"，不编造

### 篇幅控制

| 板块 | 限制 |
|------|------|
| 全文（不含参考文献） | **无字数上限**，按主题需要完整展开，不以篇幅压缩内容 |
| 结论概览 | 完整呈现核心发现 |
| 证据卡片 | 以讲清楚为准，不设字数上限 |
| 证据矩阵表 | 覆盖全部主要临床维度，行数不限 |
| 研究动向 | 简洁，以讲清楚为准 |
| 研究缺口 | 简洁，以讲清楚为准 |
| 结论与思考 | 四段式写完整，不设字数上限 |

**核心原则：完整研究报告，不是摘要。** 每个机制链条、每个证据矛盾都要展开到能支撑临床决策的深度。

### 结论与思考：四维框架

四段式，不设字数上限。这是全文的收束——**不是前面证据的概括重复**，而是综合所有证据后的判断和反思：

1. **临床建议** — 基于现有证据，今天临床实践该怎么做？不给虚话，给出具体可操作的建议
2. **矛盾与张力** — 证据之间有冲突吗？怎么理解和解释这种冲突？冲突本身可能意味着什么？
3. **盲区** — 目前最缺什么证据？缺的这个为什么重要？不是"需要更多研究"，而是"最缺X类型的证据，因为Y"
4. **跨域参照** — 兽医为主时：人医同领域证据给了什么参照和警示？人医为主时：兽医学现有证据是什么状态？有什么差距和可借鉴方向？

---

## 质检清单

交付前逐条自检：

- [ ] 检索域是否确认？人医为主/纯人医时是否用了 `--no-vet-filter` 并追加了人医指南源？兽医为主时是否保留了 `veterinary[sb]`？
- [ ] PICO拆解是否清晰？检索是否拆成了2-3个短查询（非一个长查询）？
- [ ] 关键词是否覆盖中英文+同义词+MeSH？
- [ ] 检索了PubMed + Semantic Scholar + 指南源？
- [ ] 人医参照是否检索并标注了来源域差异？
- [ ] 入选文献是否覆盖了主要临床维度？所有符合纳入标准的高质量文献是否全部保留？
- [ ] 报告是否按完整研究报告标准展开（无字数限制的删减）？机制链条是否展开到可支撑临床决策的深度？
- [ ] 每篇入选文献是否标注了证据强度+理由？
- [ ] 结论概览是否能独立传达核心信息且完整呈现关键发现？
- [ ] 证据矩阵表是否覆盖了主要临床维度？
- [ ] 分区证据卡片是否覆盖全部主要临床维度、内容完整？
- [ ] 结论与思考是否回应了四维框架的每一问？
- [ ] 是否有触犯禁区（套话、空洞形容词、编造信息）？
- [ ] 全文是否用"犬"而非"狗"？并列是否写"犬猫"而非"猫狗/狗猫"？（引号内直接引语、文献标题原文除外）
- [ ] 是否对入选文献运行了 `fetch_fulltext.py`？
- [ ] 用户要"原文 PDF"时，是否运行了 `fetch_pdf.py`（而非只给文本）？
- [ ] 每份 PDF 是否以魔数 `%PDF-` 验证过，而非只看 HTTP 状态或文件大小？
- [ ] 判定"无开放版"前，是否核对过出版商页面的访问徽章（Free/Open/Restricted access）？是否只凭 Unpaywall/OpenAlex 元数据就下了结论？
- [ ] 报告中的"未获取"措辞，是否区分了「内容不存在」与「我取不到」？
- [ ] 每篇文献的获取状态（全文/仅摘要/PDF 已得）是否在报告中标注？
- [ ] 仅获取摘要的文献，摘要是否完整（非截断）且标注了获取限制？
- [ ] 所有文献标注了PMID/DOI？
- [ ] 检索时间和平台是否注明？
- [ ] 所有缩写首次出现是否用"缩写ABC（英文全称。中文译名）"格式展述，第二次及之后保留缩写？
- [ ] PDF排版美观、矩阵表可读、证据强度标记清晰？
