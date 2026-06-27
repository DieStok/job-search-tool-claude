"""Multi-country live search: human-data omics / Bio-ML roles for a Masters-in-bioinformatics
candidate across NL, DE, CH, BE, SE. Accumulates into one dataset, ranks once, then applies the
Claude-judgment filters: omics-relevant AND working with HUMAN data. Own IP, gentle volume.
"""
from __future__ import annotations
import json
import pandas as pd

from lcp.config import load_config
from lcp import fetch_jobs as fj, rank_jobs as rj, runlog

COUNTRIES = [  # (Indeed country_indeed, LinkedIn location)
    ("Netherlands", "Netherlands"),
    ("Germany", "Germany"),
    ("Switzerland", "Switzerland"),
    ("Belgium", "Belgium"),
    ("Sweden", "Sweden"),
]

cfg = load_config("config/demo_omics.yaml")
cfg.raw["meta"]["data_dir"] = "data_demo_multi"
cfg.raw["state"]["sqlite_path"] = "data_demo_multi/state.sqlite"
cfg.raw["observability"]["run_log_dir"] = "data_demo_multi/runs"
cfg.raw["jobs"]["results_wanted"] = 20            # gentler per-query (5 countries)
cfg.raw["jobs"]["search_terms"] = [
    "PhD bioinformatics", "bioinformatician",
    "machine learning genomics", "data scientist omics", "computational biology",
]
logger = runlog.RunLogger(cfg.run_log_dir)

total = 0
for country_indeed, location in COUNTRIES:
    cfg.raw["jobs"]["country_indeed"] = country_indeed
    cfg.raw["jobs"]["location"] = location
    try:
        n = fj.fetch_jobs(cfg, logger)
        print(f"  {country_indeed}: +{n} new")
        total += n
    except Exception as exc:  # noqa: BLE001
        print(f"  {country_indeed}: FAILED ({type(exc).__name__})")
print(f"fetched {total} new jobs across {len(COUNTRIES)} countries")

# rank once over the accumulated dataset; credit all target-country locations
cfg.rubric["jobs"]["location"]["mode"] = "anywhere_eu"
n_short = rj.rank_jobs(cfg, logger)
print(f"shortlisted {n_short}")

# ---- Claude-judgment filters: omics-relevant AND human-data ----
df = pd.read_parquet("data_demo_multi/jobs.parquet").set_index("job_id")
sl = json.load(open("data_demo_multi/shortlist.json"))
OMICS = ("omic","genom","transcriptom","proteom","metabolom","epigenom","single-cell","single cell",
         "sequencing","ngs","rna-seq","scrna","multi-omic","bioinformatic","computational biolog",
         "variant","gwas","systems biolog","biomarker","immuno-onc")
HUMAN = ("human","patient","clinical","cancer","tumour","tumor","oncolog","disease","biomedical",
         "medical","cohort","biobank","immun","neuro","cardio","rare disease","health","hospital",
         "umc","clinic","psychiat","alzheimer","parkinson","diabet","brain")
NONHUMAN = ("plant","crop","agri","livestock","cattle","dairy","poultry","seafood","fish","aquacult",
            "bird","wildlife","veterinary","botanic"," soil","forest","insect","thrips","arabidopsis",
            "maize","wheat","callus","seed ","horticult","cultivated seafood","animal breeding")

rows = []
for e in sl:
    jid = e["job_id"]; r = df.loc[jid] if jid in df.index else {}
    text = ((e.get("title") or "") + " " + str((r.get("description") if jid in df.index else "") or "")).lower()
    omics = bool([k for k in OMICS if k in text])
    human = bool([k for k in HUMAN if k in text])
    nonhuman = bool([k for k in NONHUMAN if k in text])
    human_data = human and not (nonhuman and not human)  # human signal, not a plant/animal study
    if nonhuman and human:  # mixed — keep only if human is clearly primary (cancer/patient/clinical)
        human_data = any(k in text for k in ("patient","clinical","cancer","tumor","tumour","oncolog","biobank","cohort","disease"))
    rows.append(dict(score=round(e["score"],2), omics_relevant=omics, human_data=human_data,
                     country=(r.get("location") if jid in df.index else ""),
                     company=e.get("company"), title=e.get("title"),
                     date_posted=(str(r.get("date_posted")) if jid in df.index else ""),
                     source=(r.get("source") if jid in df.index else ""),
                     job_url=(r.get("job_url") if jid in df.index else ""),
                     reasons="; ".join(e.get("reasons",[]))))

alldf = pd.DataFrame(rows).sort_values(["score"], ascending=False)
alldf.to_csv("data_demo_multi/shortlist_all.csv", index=False)
human_omics = alldf[(alldf.human_data) & (alldf.omics_relevant)].copy()
human_omics.to_csv("data_demo_multi/shortlist_human_omics.csv", index=False)
print(f"\nshortlist rows={len(alldf)}  human+omics={len(human_omics)}")
print("=== HUMAN-DATA omics/Bio-ML roles ===")
for _, x in human_omics.iterrows():
    print(f"{x.score:.2f} | {str(x.country)[:26]:26} | {(x.company or '?')[:24]:24} | {(x.title or '')[:46]}")
