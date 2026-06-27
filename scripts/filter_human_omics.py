"""Re-rank the already-fetched 5-country dataset wider, then filter to HUMAN-data omics/Bio-ML.
No network — reads data_demo_multi/jobs.parquet. Tighter human-vs-plant/animal classifier.
"""
from __future__ import annotations
import json
import pandas as pd
from lcp.config import load_config
from lcp import rank_jobs as rj, runlog

cfg = load_config("config/demo_omics.yaml")
cfg.raw["meta"]["data_dir"] = "data_demo_multi"
cfg.raw["observability"]["run_log_dir"] = "data_demo_multi/runs"
cfg.raw["state"]["sqlite_path"] = "data_demo_multi/state.sqlite"
cfg.raw["ranking"]["shortlist_size"] = 200          # widen: score most role-matching jobs
cfg.rubric["jobs"]["location"]["mode"] = "anywhere_eu"
rj.rank_jobs(cfg, runlog.RunLogger(cfg.run_log_dir))

df = pd.read_parquet("data_demo_multi/jobs.parquet").set_index("job_id")
sl = json.load(open("data_demo_multi/shortlist.json"))

OMICS = ("omic","genom","transcriptom","proteom","metabolom","epigenom","single-cell","single cell",
         "sequencing"," ngs","rna-seq","scrna","multi-omic","bioinformatic","computational biolog",
         "variant","gwas","systems biolog","biomarker","immuno-onc","cfdna","methylation")
# Plant/animal/ecology → NOT human. If any of these appears, it's out (unless clearly human-clinical).
NONHUMAN = ("plant","crop","agri","livestock","cattle","dairy","poultry","seafood","fish ","aquacult",
            "bird","wildlife","veterinary","botanic","forest","insect","thrips","arabidopsis","maize",
            "wheat","callus","horticult","climate change","ecosystem","ecolog","soil","animal breeding",
            "marine","zebrafish","drosophila","yeast")
# Strong human-clinical signals (generic 'disease'/'health' excluded — plants have those too).
HUMAN = ("human","patient","clinical","cancer","tumour","tumor","oncolog","biomedical","biobank",
         "cohort","hospital","umc ","clinic","alzheimer","parkinson","diabet","cardiovascular",
         "immunolog","neurodegener","rare disease","precision medicine","genomic medicine","blood",
         "ipsc","organoid","single-cell rna","gwas","psychiat","autoimmun","leukemia","melanoma")

rows = []
for e in sl:
    jid = e["job_id"]; r = df.loc[jid] if jid in df.index else {}
    title = (e.get("title") or "")
    text = (title + " " + str((r.get("description") if jid in df.index else "") or "")).lower()
    omics = bool([k for k in OMICS if k in text])
    nonhuman = bool([k for k in NONHUMAN if k in text])
    human = bool([k for k in HUMAN if k in text])
    # human-data = a clear human-clinical signal AND not a plant/animal/ecology study
    human_data = human and not nonhuman
    rows.append(dict(score=round(e["score"],2), human_data=human_data, omics_relevant=omics,
                     country=(r.get("location") if jid in df.index else ""),
                     company=e.get("company"), title=title,
                     date_posted=(str(r.get("date_posted")) if jid in df.index else ""),
                     source=(r.get("source") if jid in df.index else ""),
                     job_url=(r.get("job_url") if jid in df.index else ""),
                     reasons="; ".join(e.get("reasons",[]))))

alld = pd.DataFrame(rows)
ho = alld[(alld.human_data) & (alld.omics_relevant)].drop_duplicates(
    subset=["company","title"]).sort_values("score", ascending=False)
ho.to_csv("data_demo_multi/shortlist_human_omics.csv", index=False)
alld.sort_values("score", ascending=False).to_csv("data_demo_multi/shortlist_all.csv", index=False)
print(f"scored={len(alld)}  HUMAN+omics (deduped)={len(ho)}")
for _, x in ho.iterrows():
    print(f"{x.score:.2f} | {str(x.country)[:24]:24} | {(x.company or '?')[:26]:26} | {(x.title or '')[:50]}")
