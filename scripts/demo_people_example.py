"""DEMO — run the REAL warmth-scoring + outreach engine on a realistic Amsterdam UMC staff set.

The staff rows are illustrative (synthetic names; live people-scraping runs under YOUR own
session via linkedin-mcp in Claude Desktop). Everything else — the warmth scorer, the cited
reasons, the draft composer — is the real production code, run against the demo profile.yaml.
"""
from __future__ import annotations
import json
from pathlib import Path

import pandas as pd

from lcp.config import load_config
from lcp import score_people as sp
from lcp.outreach import draft_outreach

CFG = load_config("config/demo_biodl.yaml")
DATA = CFG.data_dir
DATA.mkdir(parents=True, exist_ok=True)

# Realistic (illustrative) Amsterdam UMC bio/DL staff. Warmth comes from overlap with the
# demo profile (Amsterdam UMC employer; UvA / VU Amsterdam; bio/DL skills; Amsterdam).
staff = [
    dict(company="Amsterdam UMC", name="Dr. Lotte van Dijk",
         title="Senior Research Scientist, Computational Genomics", profile_url="https://www.linkedin.com/in/lotte-vandijk-demo/",
         location="Amsterdam, Netherlands",
         education=[{"school": "University of Amsterdam", "degree": "PhD", "field": "Bioinformatics"}],
         experiences=[{"company": "Amsterdam UMC", "title": "Senior Research Scientist", "years": "2024-present"}],
         skills=["deep learning", "genomics", "python"], email=None, contactable=True, source="demo"),
    dict(company="Amsterdam UMC", name="Sven Bakker",
         title="ML Engineer, Medical Imaging AI", profile_url="https://www.linkedin.com/in/sven-bakker-demo/",
         location="Amsterdam, Netherlands",
         education=[{"school": "Vrije Universiteit Amsterdam", "degree": "MSc", "field": "AI"}],
         experiences=[{"company": "Amsterdam UMC", "title": "ML Engineer", "years": "2023-present"}],
         skills=["pytorch", "machine learning", "medical imaging"], email=None, contactable=False, source="demo"),
    dict(company="Amsterdam UMC", name="Prof. Maria Rossi",
         title="Group Leader, AI for Drug Discovery", profile_url="https://www.linkedin.com/in/maria-rossi-demo/",
         location="Amsterdam, Netherlands",
         education=[{"school": "ETH Zurich", "degree": "PhD", "field": "Chemistry"}],
         experiences=[{"company": "Amsterdam UMC", "title": "Group Leader", "years": "2019-present"}],
         skills=["drug discovery", "machine learning"], email=None, contactable=False, source="demo"),
    dict(company="Amsterdam UMC", name="Tom de Vries",
         title="Data Engineer, Human Genetics", profile_url="https://www.linkedin.com/in/tom-devries-demo/",
         location="Amsterdam, Netherlands",
         education=[{"school": "University of Amsterdam", "degree": "MSc", "field": "Computer Science"}],
         experiences=[{"company": "Hartwig Medical Foundation", "title": "Bioinformatician", "years": "2021-2024"},
                      {"company": "Amsterdam UMC", "title": "Data Engineer", "years": "2024-present"}],
         skills=["python", "genomics", "data engineering"], email=None, contactable=True, source="demo"),
]
pd.DataFrame(staff).to_parquet(DATA / "staff.parquet", index=False)

# REAL engine: warmth scoring -> people_to_meet.json
from lcp import runlog
logger = runlog.RunLogger(CFG.run_log_dir)
n = sp.score_people(CFG, logger)
people = json.load(open(DATA / "people_to_meet.json"))
print(f"people_to_meet: {n}")
for p in people:
    print(f"  warmth={p['warmth_score']:.2f}  {p['name']}  ::  {', '.join(p['why'])}")

# REAL engine: draft outreach for the warmest person
if people:
    draft = draft_outreach(CFG, people[0], logger)
    print("\n--- DRAFT (warmest person) ---")
    print(f"channel: {draft.channel} | words: {draft.word_count} | signal: {draft.warmth_signal_used} | sent: {draft.sent}")
    print(draft.body)
    json.dump(draft.model_dump(), open(DATA / "draft_top.json", "w"), indent=2, default=str)
