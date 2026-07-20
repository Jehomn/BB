#!/usr/bin/env python3
"""
Veterinary Literature Search — PubMed + Semantic Scholar API wrapper.
Usage: python lit_search.py --query "canine propofol induction" --max 30
Output: JSON to stdout with structured literature results.
"""

import sys
import json
import argparse
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET

# ── PubMed Entrez API ──

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def pubmed_search(query, max_results=20):
    """Search PubMed via E-utilities, return list of PMIDs."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance",
    }
    url = f"{PUBMED_BASE}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"[PubMed search error] {e}", file=sys.stderr)
        return []


def pubmed_fetch(pmids, rettype="abstract", retmode="xml"):
    """Fetch PubMed records for a list of PMIDs."""
    if not pmids:
        return ""
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": rettype,
        "retmode": retmode,
    }
    url = f"{PUBMED_BASE}/efetch.fcgi?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[PubMed fetch error] {e}", file=sys.stderr)
        return ""


def parse_pubmed_xml(xml_text):
    """Parse PubMed EFetch XML into structured records."""
    results = []
    try:
        root = ET.fromstring(xml_text)
        for article in root.findall(".//PubmedArticle"):
            medline = article.find(".//MedlineCitation")
            article_node = medline.find(".//Article") if medline is not None else None

            pmid = medline.findtext(".//PMID", "N/A") if medline is not None else "N/A"

            title_node = article_node.find(".//ArticleTitle") if article_node is not None else None
            title = (title_node.text or "") if title_node is not None else ""

            abstract_node = article_node.find(".//Abstract/AbstractText") if article_node is not None else None
            abstract = (abstract_node.text or "") if abstract_node is not None else ""

            journal = article_node.findtext(".//Journal/Title", "") if article_node is not None else ""

            year = article_node.findtext(".//Journal/JournalIssue/PubDate/Year", "")
            if not year:
                medline_date = article_node.findtext(".//Journal/JournalIssue/PubDate/MedlineDate", "")
                year = medline_date[:4] if medline_date else ""

            author_list = article_node.findall(".//AuthorList/Author") if article_node is not None else []
            first_author = ""
            if author_list:
                last = author_list[0].findtext("LastName", "")
                fore = author_list[0].findtext("ForeName", "")
                first_author = f"{last} {fore}".strip()

            doi = ""
            for eid in article.findall(".//ELocationID"):
                if eid.get("EIdType") == "doi":
                    doi = eid.text or ""

            pub_types = []
            pts_node = article_node.find(".//PublicationTypeList") if article_node is not None else None
            if pts_node is not None:
                pub_types = [pt.text for pt in pts_node.findall("PublicationType") if pt.text]

            # Sanitize fields for safe JSON output
            def safe_str(s):
                return s.replace('\x00', '').replace('�', '') if s else ''

            results.append({
                "pmid": safe_str(pmid),
                "title": safe_str(title),
                "first_author": safe_str(first_author),
                "journal": safe_str(journal),
                "year": safe_str(year),
                "doi": safe_str(doi),
                "abstract": safe_str(abstract[:600]),
                "pub_types": pub_types,
                "source": "PubMed",
            })
    except ET.ParseError as e:
        print(f"[XML parse error] {e}", file=sys.stderr)
    return results


# ── Semantic Scholar API ──

S2_BASE = "https://api.semanticscholar.org/graph/v1"


def s2_search(query, max_results=20, max_retries=3):
    """Search Semantic Scholar for papers, with exponential backoff on 429."""
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,authors,year,abstract,journal,externalIds,publicationTypes,citationCount",
    }
    url = f"{S2_BASE}/paper/search?{urllib.parse.urlencode(params)}"

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VetLitReview/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 429:
                    wait = 5 * (2 ** attempt)
                    print(f"[S2 rate limited, retrying in {wait}s...]", file=sys.stderr)
                    time.sleep(wait)
                    continue
                data = json.loads(resp.read())
                break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                wait = 5 * (2 ** attempt)
                print(f"[S2 rate limited (429), retry {attempt+1}/{max_retries} in {wait}s...]", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"[Semantic Scholar error] HTTP {e.code}", file=sys.stderr)
                return []
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 5 * (2 ** attempt)
                print(f"[S2 error, retry {attempt+1}/{max_retries} in {wait}s: {e}]", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"[Semantic Scholar search error] {e}", file=sys.stderr)
                return []
    else:
        print(f"[Semantic Scholar] all {max_retries} retries exhausted", file=sys.stderr)
        return []

    results = []
    for paper in data.get("data", []):
        pmid = paper.get("externalIds", {}).get("PubMedId", "N/A") or "N/A"
        doi = paper.get("externalIds", {}).get("DOI", "")
        authors = paper.get("authors", [])
        first_author = authors[0].get("name", "") if authors else ""
        results.append({
            "pmid": pmid,
            "title": paper.get("title", ""),
            "first_author": first_author,
            "journal": (paper.get("journal") or {}).get("name", ""),
            "year": str(paper.get("year", "")),
            "doi": doi,
            "abstract": (paper.get("abstract") or "")[:600],
            "citations": paper.get("citationCount", 0),
            "source": "Semantic Scholar",
        })
    return results


# ── Merge & Deduplicate ──

def merge_results(pubmed_results, s2_results):
    """Merge results, deduplicate by PMID or title similarity."""
    seen_pmids = set()
    seen_titles = set()
    merged = []

    def add(paper):
        pmid = paper.get("pmid", "N/A")
        title_key = paper.get("title", "").lower().strip(".")[:60]
        if pmid != "N/A" and pmid in seen_pmids:
            return
        if title_key in seen_titles:
            return
        if pmid != "N/A":
            seen_pmids.add(pmid)
        seen_titles.add(title_key)
        merged.append(paper)

    for p in pubmed_results:
        add(p)
    for p in s2_results:
        add(p)

    merged.sort(key=lambda x: x.get("year", "0"), reverse=True)
    return merged


# ── Query helpers ──

def check_query_length(query):
    """Warn if query is too long for effective PubMed search."""
    words = query.split()
    if len(words) > 12:
        print(f"[HINT] Query has {len(words)} words. PubMed works best with <10 words. "
              f"Consider breaking into multiple focused sub-queries.", file=sys.stderr)


def build_vet_query(query, veterinary_only=True):
    """Build PubMed query, optionally appending veterinary subset filter."""
    if veterinary_only:
        return f"({query}) AND veterinary[sb]"
    return query


def main():
    # Fix Windows GBK encoding: force UTF-8 stdout
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(
        description="Veterinary Literature Search — PubMed + Semantic Scholar")
    parser.add_argument("--query", required=True, help="Search query string (English, keep <10 words)")
    parser.add_argument("--years", type=int, default=5, help="Years back from current")
    parser.add_argument("--max", type=int, default=30, dest="max_results",
                        help="Max results per source")
    parser.add_argument("--veterinary-only", action="store_true", default=True,
                        help="Append veterinary subset filter (default: True)")
    parser.add_argument("--no-vet-filter", action="store_false", dest="veterinary_only",
                        help="Don't append veterinary filter")
    parser.add_argument("--s2-retries", type=int, default=3,
                        help="Max Semantic Scholar retries on 429 (default: 3)")
    parser.add_argument("--text", action="store_true", default=False,
                        help="Output human-readable text instead of JSON")
    parser.add_argument("--brief", action="store_true", default=False,
                        help="Output brief listing (PMID, author, year, title, types only)")
    args = parser.parse_args()

    check_query_length(args.query)

    pubmed_query = build_vet_query(args.query, args.veterinary_only)

    # ── PubMed ──
    print(f"[INFO] PubMed: {pubmed_query[:100]}", file=sys.stderr)
    pubmed_pmids = pubmed_search(pubmed_query, max_results=args.max_results)
    print(f"[INFO] PubMed returned {len(pubmed_pmids)} PMIDs", file=sys.stderr)

    if not pubmed_pmids and args.veterinary_only:
        # Auto-retry without vet filter
        print("[INFO] PubMed vet-filter returned 0 results. Auto-retrying without filter...", file=sys.stderr)
        pubmed_query = build_vet_query(args.query, False)
        pubmed_pmids = pubmed_search(pubmed_query, max_results=args.max_results)
        print(f"[INFO] PubMed (no-filter) returned {len(pubmed_pmids)} PMIDs", file=sys.stderr)
    elif not pubmed_pmids:
        print("[HINT] PubMed returned 0 results. Try: shorten query, remove some terms, "
              "or use --no-vet-filter to broaden scope.", file=sys.stderr)

    pubmed_records = []
    if pubmed_pmids:
        xml_text = pubmed_fetch(pubmed_pmids)
        pubmed_records = parse_pubmed_xml(xml_text)
        print(f"[INFO] Parsed {len(pubmed_records)} PubMed records", file=sys.stderr)

    # ── Semantic Scholar ──
    time.sleep(0.5)
    print(f"[INFO] S2: {args.query[:100]}", file=sys.stderr)
    s2_records = s2_search(args.query, max_results=args.max_results,
                           max_retries=args.s2_retries)
    print(f"[INFO] S2 returned {len(s2_records)} papers", file=sys.stderr)

    # ── Merge ──
    merged = merge_results(pubmed_records, s2_records)
    print(f"[INFO] Total unique: {len(merged)} (PubMed={len(pubmed_records)} + S2={len(s2_records)})",
          file=sys.stderr)

    # ── Output ──
    if args.text or args.brief:
        print(f"\n{'='*60}")
        print(f"Query: {args.query}")
        print(f"PubMed query: {pubmed_query}")
        print(f"Results: {len(merged)} unique (PubMed={len(pubmed_records)} S2={len(s2_records)})")
        print(f"{'='*60}\n")

        if not merged:
            print("No results found. Suggestions:")
            print("  - Shorten the query (5-8 words work best)")
            print("  - Try --no-vet-filter to broaden scope")
            print("  - Try different keyword combinations")
        else:
            for i, p in enumerate(merged, 1):
                pmid = p.get('pmid', 'N/A')
                au = p.get('first_author', '?')
                yr = p.get('year', '?')
                jrnl = p.get('journal', '?')
                title = p.get('title', '?')
                src = p.get('source', '?')
                doi = p.get('doi', '')
                cites = p.get('citations', '')
                pub_types = p.get('pub_types', [])

                types_str = ', '.join(pub_types[:4]) if pub_types else ''
                if types_str:
                    types_str = f' [{types_str}]'

                print(f"{i}. PMID:{pmid} | {au} ({yr}) | {jrnl}")
                print(f"   {title}")
                if doi:
                    print(f"   DOI: {doi}", end='')
                    if cites:
                        print(f" | Citations: {cites}", end='')
                    print()
                if types_str:
                    print(f"   Types:{types_str}")
                if not args.brief:
                    abstract = p.get('abstract', '')
                    if abstract:
                        print(f"   Abstract: {abstract[:300]}{'...' if len(abstract)>300 else ''}")
                print()

        print(f"{'='*60}")
        print(f"Total: {len(merged)} papers | PubMed: {len(pubmed_records)} | S2: {len(s2_records)}")
        print(f"{'='*60}")
    else:
        output = {
            "query": args.query,
            "pubmed_query": pubmed_query,
            "years_back": args.years,
            "total_results": len(merged),
            "results": merged,
        }
        json_str = json.dumps(output, ensure_ascii=False, indent=2)
        sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
        print(json_str)


if __name__ == "__main__":
    main()
