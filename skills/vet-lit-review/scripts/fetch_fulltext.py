#!/usr/bin/env python3
"""
Fetch full text or complete abstracts for selected PMIDs.
Priority: PMC OA → Europe PMC → Unpaywall → PubMed full abstract.

Usage:
  python fetch_fulltext.py --pmids "12345,67890" --output papers.json
  python fetch_fulltext.py --pmids "12345,67890" --output papers.json --text
"""

import sys
import json
import argparse
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import re
import os

# ── Endpoints ──

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PMC_BASE = "https://www.ncbi.nlm.nih.gov/pmc"
EUROPE_PMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UNPAYWALL_BASE = "https://api.unpaywall.org/v2"

# ── Rate limiting ──
# PubMed E-utils: 3/sec without API key, 10/sec with
# Wait 0.35s between requests to be safe
REQUEST_DELAY = 0.35


# ── PubMed: full record with structured abstract ──

def fetch_pubmed_full(pmid):
    """Fetch complete PubMed record (full abstract, MeSH, all authors)."""
    params = {
        "db": "pubmed",
        "id": pmid,
        "rettype": "abstract",
        "retmode": "xml",
    }
    url = f"{PUBMED_BASE}/efetch.fcgi?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")
        return parse_pubmed_full(xml_text)
    except Exception as e:
        print(f"  [PubMed fetch error] {e}", file=sys.stderr)
    return None


def parse_pubmed_full(xml_text):
    """Parse PubMed EFetch XML into rich structured record."""
    try:
        root = ET.fromstring(xml_text)
        articles = []
        for article_elem in root.findall(".//PubmedArticle"):
            medline = article_elem.find(".//MedlineCitation")
            art = medline.find(".//Article") if medline is not None else None

            pmid = _text(medline, ".//PMID") if medline is not None else ""

            # Title
            title = ""
            if art is not None:
                tn = art.find(".//ArticleTitle")
                if tn is not None:
                    title = "".join(tn.itertext()).strip()

            # Structured abstract (full, no truncation)
            abstract_parts = []
            if art is not None:
                abs_elem = art.find(".//Abstract")
                if abs_elem is not None:
                    for at in abs_elem.findall("AbstractText"):
                        label = at.get("Label", "")
                        text = "".join(at.itertext()).strip()
                        if label:
                            abstract_parts.append(f"{label}: {text}")
                        else:
                            abstract_parts.append(text)
            abstract = "\n".join(abstract_parts)

            # Journal
            journal = _text(art, ".//Journal/Title") if art is not None else ""

            # Year
            year = ""
            if art is not None:
                year = _text(art, ".//Journal/JournalIssue/PubDate/Year")
                if not year:
                    md = _text(art, ".//Journal/JournalIssue/PubDate/MedlineDate")
                    year = md[:4] if md else ""

            # All authors
            authors = []
            if art is not None:
                for a in art.findall(".//AuthorList/Author"):
                    ln = _text(a, "LastName")
                    fn = _text(a, "ForeName")
                    if ln:
                        authors.append(f"{ln} {fn}".strip())

            # DOI
            doi = ""
            for eid in article_elem.findall(".//ELocationID"):
                if eid.get("EIdType") == "doi":
                    doi = eid.text or ""

            # Publication types
            pub_types = []
            if art is not None:
                pts = art.find(".//PublicationTypeList")
                if pts is not None:
                    pub_types = [pt.text for pt in pts.findall("PublicationType") if pt.text]

            # MeSH terms
            mesh_terms = []
            if medline is not None:
                for mh in medline.findall(".//MeshHeading"):
                    desc = _text(mh, "DescriptorName")
                    if desc:
                        mesh_terms.append(desc)

            articles.append({
                "pmid": _safe(pmid),
                "title": _safe(title),
                "authors": [_safe(a) for a in authors],
                "journal": _safe(journal),
                "year": _safe(year),
                "doi": _safe(doi),
                "abstract": _safe(abstract),
                "pub_types": pub_types,
                "mesh_terms": mesh_terms,
            })
        return articles[0] if articles else None
    except ET.ParseError as e:
        print(f"  [PubMed XML parse error] {e}", file=sys.stderr)
    return None


# ── PMC: Open Access full text ──

def check_pmc(pmid):
    """Check if PMID has a PMC ID, fetch and parse full text if available."""
    pmc_id = _get_pmc_id(pmid)
    if not pmc_id:
        return None
    return fetch_pmc_fulltext(pmc_id)


def _get_pmc_id(pmid):
    """Get PMC ID via PubMed E-utils elink."""
    params = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "id": pmid,
        "retmode": "json",
    }
    url = f"{PUBMED_BASE}/elink.fcgi?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        linksets = data.get("linksets") or [{}]
        for ls in linksets:
            for linkdb in ls.get("linksetdbs", []):
                if linkdb.get("linkname") == "pubmed_pmc":
                    ids = linkdb.get("links", [])
                    if ids:
                        return ids[0]
    except Exception as e:
        print(f"  [PMC ID lookup error] {e}", file=sys.stderr)
    return None


def fetch_pmc_fulltext(pmc_id, max_retries=2):
    """Fetch PMC XML full text and extract structured sections, with retry."""
    url = f"{PMC_BASE}/articles/{pmc_id}/?report=xml"
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VetLitReview/1.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                xml_text = resp.read().decode("utf-8", errors="replace")
            return parse_pmc_sections(xml_text, pmc_id)
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  [PMC fetch retry {attempt+1}/{max_retries-1}] {e}", file=sys.stderr)
                time.sleep(2)
            else:
                print(f"  [PMC fetch error] {e}", file=sys.stderr)
    return None


def parse_pmc_sections(xml_text, pmc_id):
    """Parse PMC XML, extract abstract + body sections."""
    sections = {
        "pmc_id": pmc_id,
        "abstract": "",
        "introduction": "",
        "methods": "",
        "results": "",
        "discussion": "",
        "conclusions": "",
    }

    try:
        root = ET.fromstring(xml_text)

        # Build parent map for proper ancestor traversal
        parent_map = {c: p for p in root.iter() for c in p}

        # Abstract paragraphs
        abs_paras = []
        for abs_elem in root.iter("abstract"):
            for p in abs_elem.iter("p"):
                text = _clean_xml_text(p)
                if text:
                    abs_paras.append(text)
        sections["abstract"] = "\n\n".join(abs_paras)

        # Body sections — classify by title keywords
        body_tag = _find_tag(root, "body")
        if body_tag is not None:
            for sec in body_tag.iter("sec"):
                title_elem = sec.find("title")
                stitle = _clean_xml_text(title_elem).lower() if title_elem is not None else ""

                paras = _collect_section_paras(sec, parent_map)
                content = "\n\n".join(paras)
                if not content:
                    continue

                # Classify by section title
                if _keywords_match(stitle, ["introduct", "background"]):
                    sections["introduction"] = content
                elif _keywords_match(stitle, ["method", "material", "protocol", "procedure", "design"]):
                    _append_section(sections, "methods", content)
                elif _keywords_match(stitle, ["result", "finding", "outcome"]):
                    _append_section(sections, "results", content)
                elif _keywords_match(stitle, ["discussion"]):
                    sections["discussion"] = content
                elif _keywords_match(stitle, ["conclusion", "summary", "implication"]):
                    _append_section(sections, "conclusions", content)
    except ET.ParseError as e:
        print(f"  [PMC XML parse error] {e}", file=sys.stderr)
    except Exception as e:
        print(f"  [PMC parse error] {e}", file=sys.stderr)

    return sections


def _collect_section_paras(sec, parent_map):
    """Collect all paragraph text from a section element (including nested secs)."""
    paras = []
    for p in sec.iter("p"):
        # Skip paragraphs nested inside child sections (we handle those separately)
        parent_sec = _find_ancestor(p, "sec", parent_map)
        if parent_sec is not sec:
            continue
        text = _clean_xml_text(p)
        if text:
            paras.append(text)
    return paras


def _find_ancestor(elem, tag, parent_map):
    """Find the nearest ancestor with given tag using parent map."""
    current = elem
    while current is not None:
        ct = _tag_name(current)
        if ct == tag:
            return current
        current = parent_map.get(current)
    return None


def _tag_name(elem):
    """Get tag name without namespace prefix."""
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


def _find_tag(parent, tag):
    """Find first element with given tag (namespace-aware) anywhere in tree."""
    for elem in parent.iter():
        if _tag_name(elem) == tag:
            return elem
    return None


def _clean_xml_text(elem):
    """Extract clean text from an XML element, stripping formatting tags."""
    if elem is None:
        return ""
    text = "".join(elem.itertext()).strip()
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text


def _keywords_match(text, keywords):
    return any(kw in text for kw in keywords)


def _append_section(sections, key, content):
    if sections.get(key):
        sections[key] += "\n\n" + content
    else:
        sections[key] = content


# ── Europe PMC ──

def check_europe_pmc(pmid):
    """Check Europe PMC for OA full text availability."""
    url = f"{EUROPE_PMC_BASE}/search?query=ext_id:{pmid}&format=json&resultType=core"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        results = data.get("resultList", {}).get("result", [])
        if not results:
            return None
        paper = results[0]
        result = {"source": "Europe PMC"}

        if paper.get("hasPDF") == "Y":
            result["has_pdf"] = True

        ft_urls = paper.get("fullTextUrlList", {}).get("fullTextUrl", [])
        if ft_urls:
            result["full_text_urls"] = [
                u.get("url") for u in ft_urls
            ]

        pmcid = paper.get("pmcid")
        if pmcid:
            result["pmcid"] = pmcid

        return result if (result.get("has_pdf") or result.get("full_text_urls")) else None
    except Exception as e:
        print(f"  [Europe PMC error] {e}", file=sys.stderr)
    return None


# ── Unpaywall ──

def check_unpaywall(doi, email=""):
    """Check Unpaywall API for legal open access versions."""
    if not doi:
        return None
    # Always include an email — Unpaywall requires it for polite access
    if not email:
        email = "vet-lit-review@example.com"
    params = urllib.parse.urlencode({"email": email})
    url = f"{UNPAYWALL_BASE}/{doi}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VetLitReview/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        if data.get("is_oa"):
            best = data.get("best_oa_location") or {}
            return {
                "source": "Unpaywall",
                "oa_url": best.get("url_for_pdf") or best.get("url") or "",
                "oa_status": data.get("oa_status", ""),
                "host_type": best.get("host_type", ""),
                "license": best.get("license", ""),
            }
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        print(f"  [Unpaywall error] HTTP {e.code} for DOI {doi}: {body}", file=sys.stderr)
    except Exception as e:
        print(f"  [Unpaywall error] {e} for DOI {doi}", file=sys.stderr)
    return None


# ── Helpers ──

def _text(parent, path):
    """Safely extract text from an XML path."""
    if parent is None:
        return ""
    node = parent.find(path)
    if node is None:
        return ""
    return (node.text or "").strip()


def _safe(s):
    """Sanitize strings for safe output."""
    if not s:
        return ""
    return s.replace('\x00', '').replace('�', '')


def _truncate(text, max_chars=5000):
    """Truncate text with ellipsis if over limit."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... truncated for length]"


# ── Text output formatter ──

def render_text_output(results):
    """Render all results as human-readable text to stdout."""
    print("=" * 70)
    print(f"文献全文/摘要获取结果 — {len(results)} 篇")
    print("=" * 70)

    ft_count = sum(1 for r in results if r["access_status"] == "full_text")
    ab_count = sum(1 for r in results if r["access_status"] == "abstract_only")
    print(f"全文: {ft_count} 篇 | 仅摘要: {ab_count} 篇\n")

    for i, r in enumerate(results, 1):
        print(f"\n{'─' * 70}")
        print(f"[{i}] {r['title']}")
        print(f"    作者: {r['authors'][0] if r['authors'] else '?'} et al. "
              f"| {r['journal']} ({r['year']})")
        print(f"    PMID: {r['pmid']}  DOI: {r['doi']}")
        print(f"    获取状态: {_status_label(r['access_status'])} "
              f"({'来源: ' + r['access_source'] if r.get('access_source') else 'PubMed'})")

        ft = r.get("full_text_sections")
        if ft and r["access_status"] == "full_text":
            for sec_name, sec_label in [
                ("abstract", "摘要"),
                ("introduction", "引言"),
                ("methods", "方法"),
                ("results", "结果"),
                ("discussion", "讨论"),
                ("conclusions", "结论"),
            ]:
                content = ft.get(sec_name, "")
                if content:
                    print(f"\n  ── {sec_label} ──")
                    for line in _truncate(content, 2000).split("\n"):
                        print(f"  {line}")
        else:
            print(f"\n  ── 摘要 ──")
            abstract = r.get("abstract", "(无摘要)")
            for line in abstract.split("\n"):
                print(f"  {line}")

    print(f"\n{'=' * 70}")
    print(f"总计: {len(results)} 篇 (全文 {ft_count} | 摘要 {ab_count})")
    print(f"{'=' * 70}")


def _status_label(status):
    return "[全文]" if status == "full_text" else "[仅摘要]"


# ── Main ──

def main():
    # Fix Windows GBK encoding: force UTF-8 stdout
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(
        description="Fetch full text / detailed abstracts for selected PMIDs")
    parser.add_argument("--pmids", required=True,
                        help="Comma-separated PMIDs, e.g. '12345,67890'")
    parser.add_argument("--output", "-o", default="papers_full.json",
                        help="Output JSON path (default: papers_full.json)")
    parser.add_argument("--email", default="",
                        help="Email for Unpaywall polite access (recommended)")
    parser.add_argument("--text-dir", default=None,
                        help="If set, save individual .txt files per paper in this directory")
    parser.add_argument("--text", action="store_true",
                        help="Print human-readable output to stdout")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY,
                        help=f"Delay between requests in seconds (default: {REQUEST_DELAY})")
    args = parser.parse_args()

    pmids = [p.strip() for p in args.pmids.split(",") if p.strip()]
    if not pmids:
        print("[ERROR] No valid PMIDs provided", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Processing {len(pmids)} PMIDs...", file=sys.stderr)

    results = []
    for i, pmid in enumerate(pmids, 1):
        print(f"[{i}/{len(pmids)}] PMID:{pmid}", file=sys.stderr)

        # Always fetch full PubMed record first
        paper = fetch_pubmed_full(pmid)
        if not paper:
            print(f"  [SKIP] Could not fetch PubMed record for PMID:{pmid}", file=sys.stderr)
            continue

        ft_status = "abstract_only"
        ft_sections = None
        access_source = "PubMed"

        # 1. Try PMC OA
        print(f"  Checking PMC...", file=sys.stderr)
        sections = check_pmc(pmid)
        if sections and _has_content(sections):
            ft_status = "full_text"
            ft_sections = sections
            access_source = f"PMC ({sections.get('pmc_id', '?')})"

        # 2. Try Europe PMC (informational — we can't easily DL full text)
        if ft_status != "full_text":
            print(f"  Checking Europe PMC...", file=sys.stderr)
            epmc = check_europe_pmc(pmid)
            if epmc:
                access_source = f"Europe PMC (has PDF)" if epmc.get("has_pdf") else "Europe PMC"

        # 3. Try Unpaywall
        doi = paper.get("doi", "")
        if ft_status != "full_text" and doi:
            print(f"  Checking Unpaywall...", file=sys.stderr)
            uw = check_unpaywall(doi, args.email)
            if uw:
                access_source = f"Unpaywall ({uw.get('oa_status', 'OA')})"

        # Build result
        result = {
            "pmid": pmid,
            "title": paper["title"],
            "authors": paper["authors"],
            "journal": paper["journal"],
            "year": paper["year"],
            "doi": doi,
            "access_status": ft_status,
            "access_source": access_source,
            "abstract": paper["abstract"],
            "pub_types": paper.get("pub_types", []),
            "mesh_terms": paper.get("mesh_terms", []),
            "full_text_sections": ft_sections,
        }
        results.append(result)

        # Save individual text file
        if args.text_dir:
            _save_text_file(result, args.text_dir)

        # Rate-limit between requests
        if i < len(pmids):
            time.sleep(args.delay)

    # Output
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    ft_count = sum(1 for r in results if r["access_status"] == "full_text")
    ab_count = sum(1 for r in results if r["access_status"] == "abstract_only")
    print(f"\n[DONE] {len(results)} papers: {ft_count} full text, {ab_count} abstract-only",
          file=sys.stderr)
    print(f"Output: {args.output}", file=sys.stderr)

    if args.text:
        render_text_output(results)


def _has_content(sections):
    """Check if parsed sections have any real content beyond empty strings."""
    if not sections:
        return False
    for key in ["abstract", "introduction", "methods", "results", "discussion", "conclusions"]:
        if sections.get(key, "").strip():
            return True
    return False


def _save_text_file(result, text_dir):
    """Save a single paper as a structured text file."""
    os.makedirs(text_dir, exist_ok=True)
    pmid = result["pmid"]
    fname = f"pmid_{pmid}.txt"
    fpath = os.path.join(text_dir, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(f"Title: {result['title']}\n")
        authors = result.get("authors", [])
        f.write(f"Authors: {', '.join(authors[:10])}{'...' if len(authors) > 10 else ''}\n")
        f.write(f"Journal: {result.get('journal', '?')} ({result.get('year', '?')})\n")
        f.write(f"PMID: {pmid}  DOI: {result.get('doi', 'N/A')}\n")
        f.write(f"Access: {result['access_status']} ({result.get('access_source', 'N/A')})\n")
        f.write(f"{'=' * 60}\n\n")

        ft = result.get("full_text_sections")
        if ft and result["access_status"] == "full_text":
            for sec_name, sec_label in [
                ("abstract", "ABSTRACT"),
                ("introduction", "INTRODUCTION"),
                ("methods", "METHODS"),
                ("results", "RESULTS"),
                ("discussion", "DISCUSSION"),
                ("conclusions", "CONCLUSIONS"),
            ]:
                content = ft.get(sec_name, "")
                if content:
                    f.write(f"--- {sec_label} ---\n")
                    f.write(_truncate(content, 5000))
                    f.write("\n\n")
        else:
            f.write("--- ABSTRACT ---\n")
            f.write(result.get("abstract", "(No abstract available)"))
            f.write("\n")
    print(f"  Saved: {fpath}", file=sys.stderr)


if __name__ == "__main__":
    main()
