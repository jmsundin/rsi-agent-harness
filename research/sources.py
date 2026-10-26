"""Paper sources: Europe PMC and arXiv. Free, keyless, no scraping.

Returns lightweight records with an abstract (and full text when open access on Europe PMC)
so the claim checker has a passage to quote from.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass
class Paper:
    id: str
    title: str
    year: str
    source: str        # europepmc | arxiv
    abstract: str
    url: str


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ratchet/0.1 (research harness)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def europe_pmc(query: str, n: int = 8) -> list[Paper]:
    q = urllib.parse.quote(query)
    url = (f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={q}"
           f"&format=json&pageSize={n}&resultType=core")
    data = json.loads(_get(url))
    out = []
    for r in data.get("resultList", {}).get("result", []):
        pid = r.get("pmcid") or r.get("pmid") or r.get("id", "")
        out.append(Paper(id=f"europepmc:{pid}", title=r.get("title", ""), year=str(r.get("pubYear", "")),
                         source="europepmc", abstract=r.get("abstractText", "") or "",
                         url=f"https://europepmc.org/abstract/MED/{r.get('pmid', '')}"))
    return out


def europe_pmc_fulltext(pmcid: str) -> str:
    """Open-access full text as plain paragraphs; empty string if unavailable."""
    pmcid = pmcid.replace("europepmc:", "")
    if not pmcid.startswith("PMC"):
        return ""
    try:
        xml = _get(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML")
    except Exception:
        return ""
    root = ET.fromstring(xml)
    paras = [" ".join(p.itertext()).strip() for p in root.iter("p")]
    return "\n\n".join(p for p in paras if len(p) > 40)


def arxiv(query: str, n: int = 8) -> list[Paper]:
    q = urllib.parse.quote(query)
    url = f"http://export.arxiv.org/api/query?search_query=all:{q}&start=0&max_results={n}"
    root = ET.fromstring(_get(url))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in root.findall("a:entry", ns):
        aid = (e.findtext("a:id", default="", namespaces=ns) or "").rsplit("/", 1)[-1]
        out.append(Paper(id=f"arxiv:{aid}", title=re.sub(r"\s+", " ", e.findtext("a:title", default="", namespaces=ns)).strip(),
                         year=(e.findtext("a:published", default="", namespaces=ns) or "")[:4], source="arxiv",
                         abstract=re.sub(r"\s+", " ", e.findtext("a:summary", default="", namespaces=ns)).strip(),
                         url=f"https://arxiv.org/abs/{aid}"))
    return out


def search(query: str, n: int = 8) -> list[Paper]:
    papers: list[Paper] = []
    for fn in (europe_pmc, arxiv):
        try:
            papers.extend(fn(query, n))
        except Exception:
            continue
    seen, out = set(), []
    for p in papers:
        if p.title.lower() not in seen and p.abstract:
            seen.add(p.title.lower())
            out.append(p)
    return out
