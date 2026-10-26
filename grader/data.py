"""Claim data: SciFact when available, a bundled synthetic sample otherwise.

SciFact (Wadden et al., 2020) pairs expert-written scientific claims with abstracts that
SUPPORT or REFUTE them. Download with `python -m grader.data fetch`; the tarball URL is in
SCIFACT_URL. Until then, the bundled sample in grader/data/sample_claims.jsonl lets every
part of the system run. The sample is synthetic and clearly labelled as such.

Splits are made once, with fixed seeds, and written to grader/data/splits.json so that
train / heldout / ood never drift between generations.
"""
from __future__ import annotations

import io
import json
import random
import sys
import tarfile
import urllib.request
from pathlib import Path

from core.schema import Claim

DATA_DIR = Path(__file__).resolve().parent / "data"
SCIFACT_DIR = DATA_DIR / "scifact"
SCIFACT_URL = "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz"
SPLITS_PATH = DATA_DIR / "splits.json"
SAMPLE_PATH = DATA_DIR / "sample_claims.jsonl"

SPLIT_SIZES = {"train": 60, "heldout": 40, "ood": 20}
SEEDS = {"train": 11, "heldout": 23, "ood": 37}


def fetch_scifact() -> None:
    SCIFACT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"downloading {SCIFACT_URL} ...")
    with urllib.request.urlopen(SCIFACT_URL, timeout=120) as r:
        buf = io.BytesIO(r.read())
    with tarfile.open(fileobj=buf, mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.name.endswith((".jsonl",)) and m.isfile():
                m.name = Path(m.name).name
                tf.extract(m, SCIFACT_DIR)
    print("extracted:", sorted(p.name for p in SCIFACT_DIR.glob("*.jsonl")))


def _load_scifact() -> list[Claim]:
    corpus_p = SCIFACT_DIR / "corpus.jsonl"
    claims_p = SCIFACT_DIR / "claims_train.jsonl"
    if not (corpus_p.exists() and claims_p.exists()):
        return []
    corpus = {}
    for line in corpus_p.read_text().splitlines():
        d = json.loads(line)
        corpus[str(d["doc_id"])] = d
    out: list[Claim] = []
    for line in claims_p.read_text().splitlines():
        d = json.loads(line)
        ev = d.get("evidence") or {}
        if ev:
            for doc_id, items in ev.items():
                doc = corpus.get(str(doc_id))
                if not doc:
                    continue
                label = items[0]["label"]
                gold = "SUPPORTS" if label == "SUPPORT" else "REFUTES"
                out.append(Claim(id=f"sf-{d['id']}-{doc_id}", claim=d["claim"], source_id=str(doc_id),
                                 source_title=doc["title"], source_text=" ".join(doc["abstract"]),
                                 gold_label=gold, domain="biomed"))
        else:
            # NOT_ENOUGH_INFO: pair with a cited doc that holds no evidence for the claim.
            for doc_id in d.get("cited_doc_ids", [])[:1]:
                doc = corpus.get(str(doc_id))
                if not doc:
                    continue
                out.append(Claim(id=f"sf-{d['id']}-{doc_id}", claim=d["claim"], source_id=str(doc_id),
                                 source_title=doc["title"], source_text=" ".join(doc["abstract"]),
                                 gold_label="NOT_ENOUGH_INFO", domain="biomed"))
    return out


def _load_sample() -> list[Claim]:
    out = []
    for line in SAMPLE_PATH.read_text().splitlines():
        if line.strip():
            out.append(Claim(**json.loads(line)))
    return out


def all_claims() -> list[Claim]:
    claims = _load_scifact()
    if not claims:
        claims = _load_sample()
    return claims


def make_splits(force: bool = False) -> dict[str, list[str]]:
    """Deterministic, label-stratified splits. OOD = the 'other domain' slice when present."""
    if SPLITS_PATH.exists() and not force:
        return json.loads(SPLITS_PATH.read_text())
    claims = all_claims()
    by_domain: dict[str, list[Claim]] = {}
    for c in claims:
        by_domain.setdefault(c.domain, []).append(c)
    main_domain = max(by_domain, key=lambda k: len(by_domain[k]))
    pool = by_domain[main_domain]
    other = [c for k, v in by_domain.items() if k != main_domain for c in v]

    def stratified(cs: list[Claim], n: int, seed: int) -> list[Claim]:
        rng = random.Random(seed)
        by_label: dict[str, list[Claim]] = {}
        for c in cs:
            by_label.setdefault(c.gold_label, []).append(c)
        picked: list[Claim] = []
        labels = sorted(by_label)
        i = 0
        while len(picked) < min(n, len(cs)):
            lab = labels[i % len(labels)]
            if by_label[lab]:
                picked.append(by_label[lab].pop(rng.randrange(len(by_label[lab]))))
            i += 1
            if all(not v for v in by_label.values()):
                break
        return picked

    remaining = list(pool)
    splits: dict[str, list[str]] = {}
    for name in ("train", "heldout"):
        chosen = stratified(remaining, SPLIT_SIZES[name], SEEDS[name])
        ids = {c.id for c in chosen}
        remaining = [c for c in remaining if c.id not in ids]
        splits[name] = [c.id for c in chosen]
    ood_pool = other if other else remaining
    splits["ood"] = [c.id for c in stratified(ood_pool, SPLIT_SIZES["ood"], SEEDS["ood"])]
    SPLITS_PATH.write_text(json.dumps(splits, indent=2))
    return splits


def load_split(name: str) -> list[Claim]:
    splits = make_splits()
    index = {c.id: c for c in all_claims()}
    out = []
    for cid in splits[name]:
        c = index[cid]
        c.split = name
        out.append(c)
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "info"
    if cmd == "fetch":
        fetch_scifact()
        make_splits(force=True)
    elif cmd == "splits":
        make_splits(force=True)
    s = make_splits()
    src = "scifact" if _load_scifact() else "bundled synthetic sample"
    print(f"source: {src}; claims: {len(all_claims())}; splits:", {k: len(v) for k, v in s.items()})
