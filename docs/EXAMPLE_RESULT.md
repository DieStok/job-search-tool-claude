# Example final result — "deep learning bioinformatics / AI for Biology"

A real run of the pipeline on 2026-06-27, Amsterdam. **The jobs half is fully live** (real
JobSpy scrape on own IP). **The people half is the real scoring + drafting engine** run on a
realistic Amsterdam UMC staff set — the *live* people layer runs under your own LinkedIn session
in Claude Desktop (see "Run the live people layer yourself" below); it is not scraped unattended
here, by design (account safety).

Demo config: `config/demo_biodl.yaml` · profile: `config/profile.yaml` (a stand-in bio/DL
researcher — replace with yours) · rubric: `config/rubric.yaml` (bio/DL-tuned).

## Funnel
| Stage | Count | Notes |
|---|---|---|
| jobs fetched (LIVE) | **46** | JobSpy, Indeed + LinkedIn, NL, own IP |
| shortlisted (LIVE) | **15** | bio/DL rubric scoring |
| company picked | 1 | Amsterdam UMC (top-warmth match for the demo profile) |
| people scored (real engine) | 4 | realistic Amsterdam UMC staff |
| people to meet | 4 | warmth ≥ 0.20, with cited reasons |
| draft | 1 | for the warmest person |

## 1. Real shortlisted jobs (top of 15, live)
| score | company | title |
|---|---|---|
| 0.89 | VARRLYN | Data Scientist AI |
| 0.87 | myTomorrows | Applied AI Engineer |
| 0.83 | SINCERIUS | Data Scientist |
| 0.83 | **Amsterdam UMC** | Data Engineer Human Genetics |
| 0.81 | Booking.com | Machine Learning Scientist II – Travel LLMs |
| 0.77 | Elsevier | Data Scientist |
| 0.71 | Vesteda | Data Scientist |
| … | (15 total) | … |

(Full data: `data_demo/shortlist.json`, `data_demo/jobs.parquet`.)

## 2. People worth a coffee (real warmth engine, Amsterdam UMC)
| warmth | person | why (cited shared-ground signals) |
|---|---|---|
| **0.93** | Dr. Lotte van Dijk — Senior Research Scientist, Computational Genomics | shared school: University of Amsterdam · shared employer: Amsterdam UMC · 1st-degree connection · role: deep learning, genomics, python · city: Amsterdam · recently joined |
| 0.90 | Tom de Vries — Data Engineer, Human Genetics | shared school: UvA · shared employer: Hartwig Medical Foundation · 1st-degree · role: genomics, python · Amsterdam · recently joined |
| 0.70 | Sven Bakker — ML Engineer, Medical Imaging AI | shared school: VU Amsterdam · shared employer: Amsterdam UMC · role: ML, pytorch · Amsterdam |
| 0.38 | Prof. Maria Rossi — Group Leader, AI for Drug Discovery | shared employer: Amsterdam UMC · role: machine learning · Amsterdam |

(Full data: `data_demo/people_to_meet.json`. Names are illustrative; the warmth math + reasons are the real engine vs `profile.yaml`.)

## 3. Drafted coffee-chat ask (real composer, warmest person)
**Channel:** LinkedIn DM · **51 words** · **signal used:** shared school (UvA) · **sent: false** (draft-only)

> Hi Lotte — I came across your profile and noticed University of Amsterdam. I'm genuinely
> curious how you got into your work at Amsterdam UMC and what it's like there. Would you be
> open to a short 20 minutes chat sometime? Happy to work around your calendar — no prep needed.

Curiosity framing, bounded ask, references the specific shared signal, no pitch — per the
research-backed rubric (`eval/outreach_rubric.md`). You'd review + send it (or have Claude
refine it first).

## Two real bugs this live run caught (now fixed + regression-tested)
1. **rank crashed on missing `date_posted`** — live jobs often have `NaT`; the recency scorer
   did `date − NaT`. Fixed (`_recency_score` guards with `pd.isna`); test `test_recency_handles_missing_date_nat`.
2. **"Hi Dr. —"** — an honorific was used as the first name. Fixed (`_first_name` strips
   Dr./Prof./Ir./…); test `test_honorific_not_used_as_first_name`.

## Run the live people layer yourself (the safe, intended mode)
The people layer is designed to run under **your own** LinkedIn session, confirmation-gated, in
Claude Desktop — not as an unattended scrape of your main account. After `./install.sh claude-desktop`:

1. Add **`stickerdaniel/linkedin-mcp-server`** with your LinkedIn cookie (it reads your session;
   for Firefox, pass the `li_at` cookie — see `docs/CLAUDE_DESKTOP.md`).
2. Ask Claude: *"From my shortlist, take Amsterdam UMC and Booking.com, find people there I share
   a school or past employer with, score warmth, and draft a coffee-chat message to the warmest —
   don't send."* Claude calls `run_staffspy`/`linkedin-mcp` (gated), then `score_people` +
   `draft_outreach` (the same engine shown above) on the *real* people.

Reproduce the deterministic half now:
```bash
.venv/bin/lcp jobs fetch --config config/demo_biodl.yaml
.venv/bin/lcp jobs rank  --config config/demo_biodl.yaml
```
