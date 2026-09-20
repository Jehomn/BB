#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch actual PDF files for selected PMIDs, with honest failure reporting.

Priority chain (each step verified by the %PDF- magic bytes, never by HTTP status):
  1. PMC OA           — needs a non-headless browser; the /pdf/ endpoint serves a
                        proof-of-work challenge page first (see NOTES below)
  2. Publisher page   — read the access badge (Free access / Open access /
                        Restricted access); download only when the publisher
                        itself offers it
  3. Europe PMC       — fullTextXML exists but is NOT a PDF source; recorded only
                        so the caller knows where the text came from
  4. Repository       — green OA copies (institutional repositories)

NOTES — three failure modes that are NOT "no PDF exists":
  * PMC returns an 1817-byte page titled "Preparing to download ...".
    That is a PoW challenge, solvable in ~13 ms, not a block. Headless browsers
    get nothing useful; use headless=False and read the PDF out of the frame.
  * Publisher download links (e.g. AVMA) return a ~1.4 KB SPA shell that loads
    the real file via JavaScript. Click it in a browser and catch the download
    event instead of fetching the URL over HTTP.
  * DSpace/ZORA bitstream endpoints may reject programmatic access entirely while
    the record page loads fine. Record that honestly; do not claim "no OA copy".

Usage:
  python fetch_pdf.py --pmids "39536456,30595108" --outdir "G:/path/原文"
  python fetch_pdf.py --pmids "..." --outdir "..." --headed
"""

import argparse
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
UNPAYWALL = "https://api.unpaywall.org/v2"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# Access badges as they literally appear on publisher pages.
ACCESS_BADGES = [
    ("free", re.compile(r"\bfree access\b", re.I)),
    ("open", re.compile(r"\bopen access\b", re.I)),
    ("restricted", re.compile(r"\brestricted access\b", re.I)),
]


# ────────────────────────── HTTP helpers ──────────────────────────

def http_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def http_text(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def is_pdf(body: bytes) -> bool:
    """The ONLY trustworthy success test."""
    return body[:5] == b"%PDF-"


def diagnose(body: bytes) -> str:
    """Say what we actually got, instead of guessing."""
    if is_pdf(body):
        return "PDF"
    head = body[:2500].decode("utf-8", errors="replace")
    n = len(body)
    if "Preparing to download" in head:
        return f"PMC-PoW-challenge ({n}B) — solvable, needs a browser"
    if "not a bot" in head or "anubis" in head.lower():
        return f"Anubis-challenge ({n}B) — bot wall on this endpoint"
    if "Just a moment" in head or "cf-browser-verification" in head or "安全验证" in head:
        return f"Cloudflare-challenge ({n}B)"
    if re.search(r"<title>\s*[a-z0-9_.-]+\s*</title>", head) and n < 2500:
        return f"SPA-shell ({n}B) — JS loads the real file; click it in a browser"
    if "<html" in head.lower():
        # Show enough of the body to identify it — guessing here is what caused
        # a wrong "unavailable" verdict before.
        snip = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", head)).strip()[:140]
        return f"HTML-page ({n}B): {snip}"
    return f"unknown ({n}B)"


# ────────────────────────── Metadata sources ──────────────────────────

def epmc_record(pmid):
    """Europe PMC core record — the authoritative fulltext-availability fields."""
    url = (f"{EPMC}/search?query=EXT_ID:{pmid}&resultType=core&format=json")
    try:
        r = http_json(url).get("resultList", {}).get("result", [{}])[0]
        return {
            "pmcid": r.get("pmcid"),
            "inEPMC": r.get("inEPMC") == "Y",
            "isOpenAccess": r.get("isOpenAccess") == "Y",
            "hasPDF": r.get("hasPDF") == "Y",
            "doi": r.get("doi"),
            "title": r.get("title"),
        }
    except Exception as e:
        print(f"  [EPMC error] {e}", file=sys.stderr)
        return {}


def unpaywall(doi, email):
    """Best-effort OA location lookup. Metadata is a HINT, never a verdict."""
    if not doi:
        return {}
    try:
        q = urllib.parse.urlencode({"email": email}) if email else ""
        d = http_json(f"{UNPAYWALL}/v2/{urllib.parse.quote(doi)}?{q}")
        best = d.get("best_oa_location") or {}
        return {
            "is_oa": d.get("is_oa"),
            "oa_status": d.get("oa_status"),
            "pdf_url": best.get("url_for_pdf"),
            "n_locations": len(d.get("oa_locations") or []),
        }
    except Exception as e:
        print(f"  [Unpaywall error] {e}", file=sys.stderr)
        return {}


# ────────────────────────── Download strategies ──────────────────────────

def pmc_pdf_url(pmcid):
    """Resolve the real PMC PDF path by reading the article page."""
    art = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
    try:
        html = http_text(art, timeout=60)
    except Exception as e:
        print(f"  [PMC article page error] {e}", file=sys.stderr)
        return None
    m = re.findall(r'href="(pdf/[^"]+\.pdf)"', html)
    if m:
        return art + m[0]
    m = re.findall(r'href="(/articles/[^"]+/pdf/[^"]+\.pdf)"', html)
    if m:
        return "https://pmc.ncbi.nlm.nih.gov" + m[0]
    return None


def try_pmc_browser(pmcid, dest, headed=True):
    """
    PMC serves a PoW challenge page, then the PDF inside Chrome's viewer frame.
    Reading the frame from a non-headless browser is what actually works.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "playwright not installed"

    art = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
    pdf_url = pmc_pdf_url(pmcid)
    if not pdf_url:
        return None, "no /pdf/ link on article page"

    extract = """async (u) => {
      const r = await fetch(u, {credentials:'include'});
      const b = new Uint8Array(await r.arrayBuffer());
      let s=''; const c=8192;
      for (let i=0;i<b.length;i+=c) s += String.fromCharCode.apply(null, b.subarray(i,i+c));
      return JSON.stringify({len:b.length, sig:String.fromCharCode.apply(null,b.subarray(0,5)), b64:btoa(s)});
    }"""
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=not headed,
                               args=["--disable-blink-features=AutomationControlled"])
        ctx = br.new_context(accept_downloads=True, viewport={"width": 1280, "height": 900})
        if not headed:
            ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        pg = ctx.new_page()
        try:
            # (a) Load the article page first — this establishes the session and
            #     lets PMC hand out its PoW challenge.
            pg.goto(art, wait_until="domcontentloaded", timeout=90000)
            try:
                pg.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            pg.wait_for_timeout(2500)

            # (b) Touch the PDF URL so the PoW solver runs for that path. It may
            #     bounce back to the article page; that is expected, not a failure.
            try:
                pg.goto(pdf_url, wait_until="domcontentloaded", timeout=90000)
                pg.wait_for_timeout(4000)
                pg.goto(art, wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(1500)
            except Exception:
                pass

            # (c) The payload lives inside the PDF viewer's frame — fetch it
            #     from there. Reading the top-level page returns Chrome's
            #     536-byte extension shell, and `ctx.request` gets served the
            #     challenge page; the frame is the one that works.
            last = "no PDF frame appeared"
            for _ in range(25):          # up to ~50 s
                pg.wait_for_timeout(2000)
                hit = None
                for f in pg.frames:
                    fu = f.url or ""
                    if fu == "about:blank" or fu == pg.url:
                        continue
                    if ".pdf" not in fu:
                        continue
                    try:
                        d = json.loads(f.evaluate(extract, fu))
                    except Exception:
                        continue
                    if d["sig"].startswith("%PDF"):
                        import base64
                        with open(dest, "wb") as fh:
                            fh.write(base64.b64decode(d["b64"]))
                        return os.path.getsize(dest), None
                    last = diagnose(d["sig"].encode())
                if hit:
                    break
            return None, f"PMC did not serve a PDF ({last})"
        finally:
            br.close()


def try_publisher_browser(pmid, dest, headed=True, email=""):
    """
    Open the publisher page, read the access badge, and — only if the publisher
    offers the file — catch the real download via the browser.
    Metadata (Unpaywall/OpenAlex) is consulted for the URL, NEVER for the verdict:
    AVMA marks articles "Free access" while Unpaywall reports is_oa=false.
    """
    rec = epmc_record(pmid)
    doi = rec.get("doi")
    if not doi:
        return None, "no DOI", None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "playwright not installed", None

    badge_seen = None
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=not headed,
                               args=["--disable-blink-features=AutomationControlled"])
        ctx = br.new_context(accept_downloads=True, viewport={"width": 1400, "height": 950})
        pg = ctx.new_page()
        try:
            pg.goto(f"https://doi.org/{doi}", wait_until="domcontentloaded", timeout=90000)
            try:
                pg.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            pg.wait_for_timeout(3500)

            body = pg.evaluate("() => document.body ? document.body.innerText : ''")
            for name, pat in ACCESS_BADGES:
                if pat.search(body):
                    badge_seen = name
                    break

            # Every "download the PDF" affordance on the page.
            cands = pg.eval_on_selector_all(
                "a,button",
                """els => els.map(e => ({
                     txt: (e.innerText || '').trim().slice(0, 40),
                     href: e.href || ''
                   })).filter(o => /download\\s*pdf/i.test(o.txt)
                                || /downloadpdf/i.test(o.href)
                                || /\\/pdf\\//i.test(o.href))""")
            if not cands:
                return None, f"no PDF affordance on page (badge={badge_seen})", badge_seen

            sel = 'a[href*="downloadpdf"], a[href*="/pdf/"]'
            with pg.expect_download(timeout=90000) as dl:
                pg.click(sel)
            d = dl.value
            d.save_as(dest)
            with open(dest, "rb") as fh:
                head = fh.read(5)
            if is_pdf(head):
                return os.path.getsize(dest), None, badge_seen
            os.remove(dest)
            return None, "downloaded file is not a PDF", badge_seen
        except Exception as e:
            return None, f"{type(e).__name__}: {str(e)[:110]} (badge={badge_seen})", badge_seen
        finally:
            br.close()


# ────────────────────────── Orchestration ──────────────────────────

def sanitize(s, n=60):
    s = re.sub(r"[^A-Za-z0-9]+", "_", (s or "").strip())
    return s.strip("_")[:n] or "untitled"


def fetch_one(pmid, outdir, email, headed):
    print(f"\n=== PMID {pmid} ===", file=sys.stderr)
    rec = epmc_record(pmid)
    doi = rec.get("doi") or ""
    up = unpaywall(doi, email)

    # Metadata is reported, never trusted as a verdict.
    print(f"  EPMC : pmcid={rec.get('pmcid')} inEPMC={rec.get('inEPMC')} "
          f"isOA={rec.get('isOpenAccess')} hasPDF={rec.get('hasPDF')}", file=sys.stderr)
    print(f"  Unpaywall: is_oa={up.get('is_oa')} status={up.get('oa_status')} "
          f"locations={up.get('n_locations')}  <- hint only", file=sys.stderr)

    dest = os.path.join(outdir, f"{pmid}_{sanitize(rec.get('title'))}.pdf")
    result = {"pmid": pmid, "doi": doi, "title": rec.get("title"),
              "epmc": rec, "unpaywall": up,
              "path": None, "size": None, "source": None, "reason": None,
              "badge": None}

    # 1) PMC OA
    if rec.get("pmcid") and rec.get("hasPDF"):
        size, err = try_pmc_browser(rec["pmcid"], dest, headed=headed)
        if size:
            result.update(path=dest, size=size, source="PMC")
            print(f"  OK   PMC -> {size} bytes", file=sys.stderr)
            return result
        print(f"  PMC  failed: {err}", file=sys.stderr)
        result["reason"] = f"PMC: {err}"

    # 2) Publisher page (badge-driven, not metadata-driven)
    size, err, badge = try_publisher_browser(pmid, dest, headed=headed, email=email)
    result["badge"] = badge
    if size:
        result.update(path=dest, size=size, source=f"publisher ({badge})")
        print(f"  OK   publisher badge={badge} -> {size} bytes", file=sys.stderr)
        return result
    print(f"  publisher: {err}", file=sys.stderr)
    if not result["reason"]:
        result["reason"] = f"publisher: {err}"

    # No file. State which of the two situations it is — do not conflate them.
    if up.get("is_oa") is False and up.get("n_locations") == 0 and badge in (None, "restricted"):
        result["reason"] = "no open copy found (publisher restricted; Unpaywall 0 locations)"
    print(f"  FAIL {result['reason']}", file=sys.stderr)
    return result


def main():
    ap = argparse.ArgumentParser(description="Fetch real PDFs for PMIDs")
    ap.add_argument("--pmids", required=True, help="Comma-separated PMIDs")
    ap.add_argument("--outdir", required=True, help="Directory for the PDFs")
    ap.add_argument("--email", default="", help="Email for Unpaywall polite pool")
    ap.add_argument("--headed", action="store_true", default=True,
                    help="Run a visible browser (required for PMC PoW; default on)")
    ap.add_argument("--headless", dest="headed", action="store_false",
                    help="Force headless (PMC will fail; use only for debugging)")
    ap.add_argument("--manifest", default=None, help="Write a JSON manifest here")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    pmids = [p.strip() for p in args.pmids.split(",") if p.strip()]
    results = [fetch_one(p, args.outdir, args.email, args.headed) for p in pmids]

    got = [r for r in results if r["path"]]
    print(f"\n[DONE] {len(got)}/{len(results)} PDFs saved to {args.outdir}", file=sys.stderr)
    for r in results:
        tag = "OK  " if r["path"] else "MISS"
        print(f"  {tag} {r['pmid']}  {r.get('size') or ''}  {r['reason'] or r['source']}",
              file=sys.stderr)

    if args.manifest:
        with io.open(args.manifest, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)
        print(f"  manifest -> {args.manifest}", file=sys.stderr)


if __name__ == "__main__":
    main()
