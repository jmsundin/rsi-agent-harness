"""Generate grader/data/sample_claims.jsonl: a SYNTHETIC claim set for offline runs.

These are invented model-organism and materials findings, not real papers. They exist so the
loop, scorer and gate can be exercised without network access. Replace with SciFact via
`python -m grader.data fetch` for real evaluation.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data" / "sample_claims.jsonl"

# (subject, intervention, outcome) triples; each yields a SUPPORTS, a REFUTES and an NEI claim.
BIO = [
    ("planarian", "blocking the H+,K+-ATPase pump", "anterior regeneration", "head"),
    ("zebrafish larvae", "overexpressing msx1", "fin regeneration rate", "fin"),
    ("C. elegans", "daf-2 knockdown", "median lifespan", "lifespan"),
    ("mouse cardiomyocytes", "transient OSKM induction", "cell-cycle re-entry", "proliferation"),
    ("Drosophila", "dietary rapamycin", "lifespan", "lifespan"),
    ("human fibroblasts", "partial reprogramming for 4 days", "epigenetic age", "age"),
    ("axolotl", "nerve deviation", "accessory limb formation", "limb"),
    ("yeast", "caloric restriction", "replicative lifespan", "lifespan"),
    ("mouse hippocampus", "young plasma infusion", "neurogenesis", "neurogenesis"),
    ("planarian", "gap-junction blockade with octanol", "two-headed phenotype frequency", "head"),
    ("HeLa cells", "senolytic dasatinib plus quercetin", "p16-positive cell fraction", "senescence"),
    ("mouse skeletal muscle", "NAD+ precursor NMN", "mitochondrial respiration", "respiration"),
    ("Xenopus embryos", "depolarizing ivermectin treatment", "ectopic eye induction", "eye"),
    ("mouse kidney", "SGLT2 inhibition", "fibrosis score", "fibrosis"),
    ("rat cortical neurons", "BDNF supplementation", "dendritic spine density", "spines"),
    ("killifish", "gut microbiota transfer from young donors", "median lifespan", "lifespan"),
    ("mouse liver", "senescent cell clearance", "regenerative capacity after hepatectomy", "regen"),
    ("planarian", "RNAi against beta-catenin", "posterior head formation", "head"),
    ("mouse retina", "OSKM in retinal ganglion cells", "axon regeneration after crush", "axon"),
    ("C. elegans", "mitochondrial unfolded protein response activation", "lifespan", "lifespan"),
    ("mouse", "metformin from midlife", "healthspan index", "healthspan"),
    ("human T cells", "telomerase activation", "replicative capacity", "telomere"),
    ("zebrafish heart", "cryoinjury with Notch inhibition", "scar resolution", "scar"),
    ("mouse", "17-alpha-estradiol", "male median lifespan", "lifespan"),
    ("Hydra", "FoxO knockdown", "stem-cell maintenance", "stem"),
    ("mouse oocytes", "NMN supplementation", "spindle integrity", "oocyte"),
    ("Drosophila", "intermittent fasting", "lifespan", "lifespan"),
    ("mouse", "young bone-marrow transplant", "frailty index", "frailty"),
    ("planarian", "ion channel chloride flux manipulation", "anterior-posterior polarity", "polarity"),
    ("human MSCs", "hypoxic preconditioning", "senescence-associated beta-galactosidase", "senescence"),
    ("mouse", "spermidine supplementation", "cardiac function at 24 months", "cardiac"),
    ("C. elegans", "dietary restriction via eat-2", "lifespan", "lifespan"),
    ("mouse skin", "topical rapamycin", "p16 expression", "p16"),
    ("zebrafish", "tert mutation", "gut regeneration", "gut"),
    ("mouse", "alpha-ketoglutarate in food", "lifespan", "lifespan"),
    ("human endothelial cells", "sirtuin-1 activation", "oxidative-stress tolerance", "stress"),
    ("mouse brain", "exercise training", "microglial activation", "microglia"),
    ("Drosophila", "gut-specific FOXO overexpression", "intestinal barrier integrity", "gut"),
    ("mouse", "ketogenic diet", "median lifespan", "lifespan"),
    ("planarian", "sodium-potassium pump inhibition", "tail regeneration", "tail"),
]

MAT = [
    ("lithium-metal cells", "a LiF-rich interphase", "coulombic efficiency", "efficiency"),
    ("perovskite solar cells", "2D/3D heterostructure passivation", "operational stability", "stability"),
    ("solid-state electrolytes", "sulfide doping with chlorine", "ionic conductivity", "conductivity"),
    ("sodium-ion cathodes", "manganese substitution", "capacity retention", "retention"),
    ("silicon anodes", "carbon-shell encapsulation", "cycle life", "cycle"),
    ("MOF membranes", "ligand fluorination", "CO2/N2 selectivity", "selectivity"),
    ("thermoelectric SnSe", "sodium doping", "figure of merit ZT", "zt"),
    ("Nafion membranes", "ceria nanoparticle loading", "radical-induced degradation", "degradation"),
    ("Li-S cathodes", "single-atom cobalt catalysts", "polysulfide shuttling", "shuttle"),
    ("zinc-ion batteries", "electrolyte additive glucose", "dendrite formation", "dendrite"),
]


def abstract_for(subj: str, interv: str, outcome: str, effect: str, n: int, p: float) -> str:
    return (f"Background: The role of {interv} in {outcome} in {subj} is debated. "
            f"Methods: We treated {subj} with {interv} and measured {outcome} across {n} independent replicates. "
            f"Results: {interv.capitalize()} {effect} {outcome} relative to vehicle controls (p = {p}). "
            f"Secondary endpoints were unchanged. Conclusions: In this model, {interv} {effect} {outcome}.")


def nei_abstract(subj: str, interv: str) -> str:
    return (f"Background: {subj.capitalize()} are a widely used model. "
            f"Methods: We characterised baseline transcriptional profiles and tissue morphology in untreated {subj}. "
            f"Results: We report a reference atlas of 1,200 cells and note that {interv} was not tested. "
            f"Conclusions: This resource will enable future interventional studies.")


def main() -> None:
    rng = random.Random(2026)
    rows = []
    cid = 0
    for domain, triples in (("biomed", BIO), ("materials", MAT)):
        for subj, interv, outcome, _ in triples:
            n = rng.choice([4, 6, 8, 12, 20])
            p = rng.choice([0.001, 0.01, 0.03, 0.04])
            up = rng.random() < 0.5
            eff = "increased" if up else "decreased"
            anti = "decreased" if up else "increased"
            abs_text = abstract_for(subj, interv, outcome, eff, n, p)
            title = f"{interv.capitalize()} and {outcome} in {subj}"
            # SUPPORTS
            cid += 1
            rows.append(dict(id=f"syn-{cid}", claim=f"In {subj}, {interv} {eff} {outcome}.", source_id=f"doc-{cid}",
                             source_title=title, source_text=abs_text, gold_label="SUPPORTS", domain=domain))
            # REFUTES
            cid += 1
            rows.append(dict(id=f"syn-{cid}", claim=f"In {subj}, {interv} {anti} {outcome}.", source_id=f"doc-{cid}",
                             source_title=title, source_text=abs_text, gold_label="REFUTES", domain=domain))
            # NOT_ENOUGH_INFO
            cid += 1
            rows.append(dict(id=f"syn-{cid}", claim=f"In {subj}, {interv} {eff} {outcome}.", source_id=f"doc-{cid}",
                             source_title=f"A reference atlas of {subj}", source_text=nei_abstract(subj, interv),
                             gold_label="NOT_ENOUGH_INFO", domain=domain))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} synthetic claims to {OUT}")


if __name__ == "__main__":
    main()
