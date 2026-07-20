# 兽医学文献检索策略速查

## 检索入口优先级

1. **PubMed (Entrez API)** — `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`
   - 兽医子集过滤: `veterinary[sb]`
   - 系统综述过滤: `systematic review[ptyp]` 或 `meta-analysis[ptyp]`
   - RCT过滤: `randomized controlled trial[ptyp]`
   - 指南过滤: `guideline[ptyp]` 或 `consensus[tiab]`
2. **Semantic Scholar API** — `https://api.semanticscholar.org/graph/v1`
   - 引文网络最强，适合查高被引文献和研究脉络
3. **Europe PMC** — `https://www.ebi.ac.uk/europepmc/webservices/rest`
   - 开放获取全文比例最高

## 兽医指南源（直接检索）

| 来源 | URL | 检索方式 |
|------|-----|---------|
| WSAVA | wsava.org/guidelines | WebFetch 直接访问 |
| AAHA | aaha.org/guidelines | WebFetch |
| ACVIM 共识声明 | 发表于 *J Vet Intern Med* | PubMed: `"consensus statement"[tiab] AND journal:"J Vet Intern Med"` |
| ISFM/AAFP 猫科指南 | 发表于 *J Feline Med Surg* | PubMed: `guideline[ptyp] AND journal:"J Feline Med Surg"` |
| RECOVER CPR | recoverinitiative.org | WebFetch |
| IVIS | ivis.org | WebFetch |

## PubMed 检索语法速查

```
# 基本逻辑
(canine OR dog) AND (propofol OR "propofol"[MeSH]) AND anesthesia

# 限定字段
propofol[tiab]          # 标题+摘要
canine[ti]               # 仅标题
"Smith J"[au]            # 作者

# 限定文献类型
AND (randomized controlled trial[ptyp] OR systematic review[ptyp])

# 限定时间
AND ("2021"[dp] : "2026"[dp])

# 兽医子集（必须加！）
AND veterinary[sb]

# 排除体外实验
NOT (in vitro[tiab])

# 完整示例
(cat OR feline) AND (dexmedetomidine OR medetomidine) AND sedation
AND veterinary[sb]
AND ("2021"[dp] : "2026"[dp])
AND (english[la] OR chinese[la])
```

## Semantic Scholar API 查询

```
# 搜索
GET https://api.semanticscholar.org/graph/v1/paper/search
  ?query=canine+propofol+induction
  &limit=20
  &fields=title,authors,year,abstract,journal,externalIds,citationCount

# 获取单篇详情
GET https://api.semanticscholar.org/graph/v1/paper/PMID:12345678
  ?fields=title,abstract,citations,references

# 查引用网络
GET https://api.semanticscholar.org/graph/v1/paper/PMID:12345678/citations
  ?fields=title,year,citationCount
```

## 人医参照检索

当兽医学直接证据不足时追加：

```
# PubMed 不加 veterinary[sb]
(propofol OR "propofol"[MeSH]) AND (apnea OR "respiratory depression")
AND systematic review[ptyp]
AND ("2021"[dp] : "2026"[dp])

# Cochrane Library
https://www.cochranelibrary.com/search
```

检索到人医证据后，必须在报告中标注来源域差异："人医证据，跨物种外推需谨慎"。
