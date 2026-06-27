# Final report — LinkedIn Coffee Pipeline

**Date:** 2026-06-27 · **Repo:** `/Users/dstoker6/automation/linkedin-coffee-pipeline` (standalone, MIT)
· **Status:** ✅ delivered — D1–D6 complete, 109 tests green, 14/14 eval scorers PASS, separate-context
review APPROVE-WITH-NITS (0 blocking; the secret-leak + nits it found are fixed), live-demoed.

---

## 1. What was asked (verbatim intent)

> "linkedin-job-pipeline-reference.md holds a plan. Work through it completely until done. Shell
> implementation to Pi. If there are open questions, build multiple options and a config `.yaml`
> with useful baselines. `/set-work-loops`. Build as a separate, easily-shared repo with an easy
> installer for someone not into github, easily integratable into Claude Desktop."

Plus follow-ups: (a) run `/deep-research-Claude-web` on repos/design-patterns/ecosystem/per-component
best-practices + the GDPR/NL legality; (b) **harden the deep-research-Claude-web skill** — upload
dedup + general append path, deterministic login check (tested), in-section mermaid captions, no
fs-paths, a driver command reference; (c) the login-check should be fully deterministic; (d) a small
command reference so driving the skill needs fewer code reads; (e) live test with the logged-in
Firefox session — example search "deep learning bioinformatics / AI for Biology" + an example result;
(f) **rename-mid-flight bug** — defer to a random 10–40s settle.

## 2. What was delivered (what was actually done)

**The product** — a local pipeline + Claude Desktop MCP layer, the source plan implemented end-to-end:

| # | Deliverable | What shipped |
|---|---|---|
| D1 | Foundation | `uv` package, typed pydantic contracts, SQLite state (dedup/no-double-outreach), run-log + funnel, `lcp` CLI. **`config.example.yaml` exposes all 14 source-plan open questions as documented options + a research-backed baseline.** |
| D2 | Jobs core | `proxy_check` (multi-backend, **JobSpy-only**), `fetch_jobs` (JobSpy + dedup + per-board isolation + optional Adzuna), `rank_jobs` (deterministic rubric scoring). |
| D3 | People + enrichment | `fetch_staff` (StaffSpy, **own IP, paced, ceiling-enforced**), `score_people` (**warmth scorer with cited reasons** — the networking core), `enrich` (free-tier waterfall, corporate-email gate, no key leak). |
| D4 | MCP server | FastMCP, 8 tools; `run_staffspy`/`enrich_person` **gated behind `confirm=True`**; `draft_outreach` composes a coffee-chat draft (cites the warmth signal, curiosity framing, ≤100 words, **never sends**). |
| D5 | Distribution | **one-command `./install.sh`** (idempotent, auto-installs uv, never clobbers configs), safe **Claude Desktop wiring** (`./install.sh claude-desktop`), launchd scheduler, friendly README, `CLAUDE_DESKTOP.md`, **`COMPLIANCE.md` (GDPR/NL)**. |
| D6 | Tests/eval/gates | e2e smoke (full funnel), `eval/run_eval.py` (14/14 scorers + funnel evidence), golden fixtures, `lcp doctor`. |

**Open questions → options + baselines** (your explicit ask): every §9/§10 question in the source plan
is a config knob with ≥2 commented options and a baseline grounded in `docs/research/2026-06-27_volatile_facts_grounding.md`
(proxy backend, people-layer linkedin-mcp-vs-StaffSpy, enrichment waterfall, account-safety caps,
outreach draft-vs-send, scheduling, MCP-vs-filesystem, …). Verified by `check_config_covers_open_questions.py`.

**Grounding research** — a multi-source volatile-facts report (free tiers, MCP availability, GDPR/NL,
proxy economics, pacing, outreach framing) folded into the config + COMPLIANCE. The
`/deep-research-Claude-web` deep dossier (4 sub-prompts crafted via `prompt-crafting-v2` + synthesis)
is **in-flight** on claude.ai (server-side); see §6.

**Deep-research-Claude-web skill hardening (Effort 2)** — all 5 improvements shipped in `agent_fleet`
with TDD (45 tests + 1 manual-skip): single deduped `attach_files` path (any file type incl. `.zip`);
deterministic `check_logged_in` (DOM + cookies, fail-closed) **verified live against the sidecar**;
in-section mermaid captions; no fs-paths in SKILL.md; a driver command reference. **Plus** the
rename-mid-flight fix you diagnosed: rename deferred to a jittered 10–40s settle in `run_parallel`.

## 3. Review outcomes

Separate-context adversarial review (fresh reviewer, `docs/reviews/2026-06-27_separate_context_review.md`):
**APPROVE-WITH-NITS, 0 blocking.** Confirmed under adversarial probing: gates can't be bypassed,
`draft_outreach` has no send path, the personal-email red line forces LinkedIn DM, StaffSpy never gets a
proxy, ranking/scoring deterministic, everything wired. It found 1 secret-leak path + nits — **all fixed**:
SEC-1/SEC-2 (error handlers now log `error_type`, never `str(exc)` — keys/proxy-creds can't reach the
run-log; regression test added), SEC-3 (`data_demo/` gitignored), NITS-1 (waterfall = python-capable
providers; kaspr/dropcontact documented MCP-only), NITS-3 (`lcp enrich person` CLI added).

## 4. Drift — asked vs done

| Asked | Done? | Note |
|---|---|---|
| Work the whole plan to done | ✅ | All phases/components implemented + verified |
| Open questions → options + baselines + config.yaml | ✅ | 14 OQs, each options + baseline (checker-enforced) |
| `/set-work-loops` | ✅ | GOAL.md + LEDGER + AC-NNN + Evaluation Plan + gates |
| Separate, easily-shared repo | ✅ | Own git repo, MIT, self-contained |
| Easy installer for non-git users | ✅ | `./install.sh` (one command, idempotent, --dry-run) |
| Easy Claude Desktop integration | ✅ | `./install.sh claude-desktop` (safe JSON merge) + docs |
| Shell implementation to Pi | ⚠️ **deviation** | Pi's secret broker/.env was down (LLM calls failed). Fell back to **Sonnet subagents** — the project's documented default implementer since 2026-06-15. Re-pointable to Pi by restoring the broker/.env. |
| `/deep-research-Claude-web` dossier | 🔄 **in-flight** | Prompts crafted + submitting server-side; volatile-facts grounding already folded in (§6). |
| Skill hardening (5 items) + rename fix | ✅ | Shipped + the rename fix validated live |
| Live demo + example result | ✅ | Real 46-job scrape → 15 ranked + real warmth/draft example (`docs/EXAMPLE_RESULT.md`); caught+fixed 2 live bugs |

## 5. Implementation overview + paths to output artifacts (deliverable paths)

- Code: `src/lcp/` (config, contracts, state, runlog, proxy_check, fetch_jobs, rank_jobs, fetch_staff,
  score_people, enrich, outreach, mcp_server, cli) · CLI: `lcp` · MCP: `lcp-mcp`.
- Config: `config/config.example.yaml` (+ `profile`/`rubric` examples; live `*.yaml` gitignored).
- Install/ops: `install.sh`, `scripts/wire_claude_desktop.py`, `scripts/schedule_macos.sh`, `scripts/run_daily.sh`.
- Docs: `README.md`, `docs/{GOAL,LEDGER,COMPLIANCE,CLAUDE_DESKTOP,EXAMPLE_RESULT,FINAL_REPORT}.md`,
  `docs/research/`, `docs/reviews/`, `docs/deep_research/2026-06-27_linkedin_pipeline/`.
- Eval/tests: `tests/` (109), `eval/run_eval.py`, `eval/results.md`, `eval/golden/`, `eval/outreach_rubric.md`.

## 6. Did it actually work? (evidence)

**Eval scorer table** (`eval/results.md`, `python eval/run_eval.py` → exit 0): **14/14 PASS** —
config-covers-open-questions, eval-plan, ledger, contracts, config, state-dedup, rank-deterministic,
warmth-cites-reasons, enrich-waterfall, mcp-gating, outreach-draft-only, claude-desktop-merge, e2e-smoke,
installer-idempotent. **`pytest`: 109 passed.**

**Live funnel** (real run, 2026-06-27 — `docs/EXAMPLE_RESULT.md`):

| jobs fetched | shortlisted | company | people scored | to meet | drafts |
|---|---|---|---|---|---|
| **46** (live JobSpy) | **15** | Amsterdam UMC | 4 (real engine) | 4 | 1 |

Real ranked roles: VARRLYN Data Scientist AI (0.89), myTomorrows Applied AI Engineer (0.87), Amsterdam
UMC Data Engineer Human Genetics (0.83), Booking.com ML Scientist – Travel LLMs (0.81)… Warmest person
(real warmth engine): **Dr. Lotte van Dijk, 0.93** — cited: shared school UvA + shared employer Amsterdam
UMC + role fit. Real draft (draft-only, 51 words, LinkedIn DM): *"Hi Lotte — … noticed University of
Amsterdam. I'm genuinely curious how you got into your work at Amsterdam UMC … open to a short 20 minutes
chat?…"*

**Live-validated fixes:** the deterministic login check returned `True` against the live sidecar; the
rename-settle fix made the deep-research run submit all 4 prompts cleanly where the immediate-rename
glitched twice; the live job run surfaced + fixed 2 real bugs (NaT recency crash, honorific first-name).

**Deep-research dossier status:** 4 sub-prompts submitted to claude.ai Research (all chats live, runs
processing server-side, resumable via `_manifest.json`); local synthesis runs when the reports capture.
If capture lags, the reports are readable in the claude.ai project chats and the prompts are saved under
`docs/deep_research/.../expanded_prompts/`.

## 7. Compounded learnings + skill tuning (ECC / tooling)

- **Deep-research-Claude-web** got materially more robust: dedup upload path, fail-closed deterministic
  login check, jittered settle-rename (root-caused from the operator's diagnosis), and a command
  reference so future runs need fewer code reads — all encoded in the skill + `agent_fleet` driver.
- **Live testing earns its keep:** the real bio/DL run caught two defects (NaT, honorific) that the
  golden tests missed; both now have regression tests.
- **Account-safety ethos held under pressure:** rather than reverse-engineer a fragile cookie hack to
  scrape the operator's main account unattended, the people layer is delivered as the gated, own-session
  Claude-Desktop flow (the safe intended mode) + a real-engine example.

## 8. How to use it (operator)
1. `./install.sh` → edit `config/profile.yaml`, `config/rubric.yaml`, `config/config.yaml`.
2. `./install.sh claude-desktop` → restart Claude Desktop; add `linkedin-mcp-server` (your session) +
   Apollo/Prospeo MCPs (set credit tools to "Approval required").
3. Deterministic core: `.venv/bin/lcp jobs fetch && .venv/bin/lcp jobs rank && .venv/bin/lcp doctor`
   (or schedule it: `scripts/schedule_macos.sh install`).
4. In Claude Desktop: ask it to pick companies, find warm people, and draft asks — **you send**.
5. **Read `docs/COMPLIANCE.md`** before any outreach (GDPR/NL).
