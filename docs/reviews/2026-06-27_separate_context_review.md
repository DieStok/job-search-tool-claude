# Separate-Context Code Review — linkedin-coffee-pipeline
**Date:** 2026-06-27  
**Reviewer:** code-reviewer agent (fresh context, did not build this repo)  
**Verdict: APPROVE-WITH-NITS**  
**Blocking issues: 0 | Security/near-blocking: 1 | Minor issues: 5**

---

## Executive summary

The pipeline passes all 14 scorers and 108 tests green. Every critical invariant checked
adversarially holds: confirmation gates cannot be bypassed, outreach `sent` is always False,
compliance red lines are enforced in code (personal email → linkedin_dm block works), proxy
invariant holds (StaffSpy never receives a proxy), ranking and scoring are deterministic, all
modules are wired into the CLI and MCP server, and the observability funnel emits and reads
correctly. The one real security issue is a run-time API-key leak into the run-log (Adzuna
keys embedded in a URL, then `str(exc)` logged on failure) that is inconsistent with the
careful pattern applied everywhere else in the codebase. It does not expose keys to git but
does write them to a local log file that users may share when debugging.

---

## 1. AC conformance

All gates exit 0:
- `python eval/run_eval.py` — 14/14 scorers PASS
- `python -m pytest -q` — 108 passed
- `python scripts/gates/gate_eval_plan_exists.py docs/GOAL.md` — PASS
- `python scripts/gates/gate_ledger_exists.py docs/LEDGER.md` — PASS
- `python scripts/check_config_covers_open_questions.py config/config.example.yaml` — PASS (14 OQs covered)

Per-AC spot-check results:

| AC | Verdict | Evidence |
|---|---|---|
| AC-001 config options+baselines | PASS | 14 OQs confirmed; each has ≥2 options and one active baseline |
| AC-002 typed contracts | PASS | JobPost/ShortlistEntry/Staff/PersonToMeet/ContactInfo/OutreachDraft in contracts.py; round-trip tests pass |
| AC-003 state dedup | PASS | seen_jobs/companies_enumerated/people_contacted; idempotent upserts verified |
| AC-010 proxy options+check | PASS | NoneBackend/InProcessBackend/WebshareBackend behind ProxyBackend protocol; scrapoxy/free_pool stub to NoneBackend (documented) |
| AC-011 fetch jobs+dedup | PASS | per-board isolation; board failure degrades gracefully |
| AC-012 rank deterministic | PASS | sort key `(-score, job_id)` — fully deterministic for fixed input (verified independently) |
| AC-020 staff own-IP+ceiling | PASS | no proxy kwargs passed to LinkedInSession; ceiling enforced before and after call |
| AC-021 warmth+reasons | PASS | every PersonToMeet carries non-empty `why[]`; sort key `(-warmth_score, profile_url)` |
| AC-022 enrich waterfall | PARTIAL — see §4 | Apollo+Prospeo are real; kaspr is silently skipped (no implementation) |
| AC-030 MCP tools+gating | PASS | 8 tools registered; GATED={"run_staffspy","enrich_person"}; selfcheck exits 0 |
| AC-031 outreach draft-only | PASS | `sent` always False; no send code path exists anywhere in the codebase |
| AC-040 installer | PASS | `--dry-run` exits 0; existing configs left untouched; idempotent |
| AC-041 Claude Desktop wiring | PASS | wire_claude_desktop.py backs up first, preserves existing keys, valid JSON |
| AC-042 compliance doc | PASS | docs/COMPLIANCE.md is substantive, cites two legal gates (GDPR/ePrivacy), matches code red lines |
| AC-043 scheduling | PASS | launchd plist exists; `schedule_macos.sh --dry-run` exits 0 |

---

## 2. Confirmation gating (CRITICAL) — PASS

`impl_run_staffspy` and `impl_enrich_person` in `src/lcp/mcp_server.py` both open with:

```python
if not confirm:
    return {"status": "confirmation_required", "message": CONFIRM_MSG.format(...)}
```

The default value of `confirm` in both the `impl_*` helpers and the `@mcp.tool()` wrappers
is `False` (`run_staffspy(company: str, confirm: bool = False)`). Adversarial test confirmed:
calling with no kwarg, with `confirm=False`, and with an omitted argument all return
`"confirmation_required"` and never call `_stage`. There is no alternate route to these
functions; `build_server()` is the only place the closures are created and they all delegate
to the `impl_*` functions.

`draft_outreach` has no send path. The `OutreachDraft.sent` field is hardcoded to `False`
in `outreach.py:87`. Overriding `outreach.mode` to `assisted_send` in config does not change
this — verified by injecting the config override. The MCP tool registry has no `send_outreach`
tool. There is no SMTP, smtplib, sendmail, or send_mail reference anywhere in the source tree.

---

## 3. Compliance red lines in code — PASS

**Personal/consumer email block** (`outreach.py:52–54`):
```python
if comp.get("block_personal_domain_cold_email", True) and not has_corp_email:
    channel = "linkedin_dm"
```
Tested adversarially: with `channel_preference=email` and a `@gmail.com` contact having
`is_corporate_email=False`, the draft channel is forced to `linkedin_dm`. PASS.

**`require_human_send` defaults True** (`config.example.yaml:162` and `config.py:81`):
```yaml
compliance:
  require_human_send: true
```
Config validation explicitly checks `if self.get("compliance.require_human_send") is not True`
and adds a problem string. Setting it to `False` was tested and raises a validation problem.
PASS.

**`docs/COMPLIANCE.md`** accurately reflects the code's behavior: two-gate model, corporate vs
personal email table, the same seven config keys (`require_human_send`, `block_personal_domain_cold_email`,
`max_daily_outreach`, `retention_days`, `opt_out_required`, `lia_on_file`,
`channel_preference`) are in both the doc and the example config. PASS.

---

## 4. Secret safety — SECURITY FINDING + MINOR GAPS

### SEC-1 (Near-blocking): Adzuna API keys leak to run-log via `str(exc)`

**File:** `src/lcp/fetch_jobs.py:158–161` and `src/lcp/fetch_jobs.py:197`

The Adzuna API keys are embedded directly in the request URL:
```python
url = (
    f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    f"?app_id={app_id}&app_key={app_key}&..."
)
```
When any network error occurs (connection refused, SSL error, timeout redirect), the exception
string from `requests` includes the URL. The error handler then logs `str(exc)`:
```python
except Exception as exc:
    logger.event("fetch_error", source="adzuna", term=term, error=str(exc))
```
This writes both keys to `data/runs/<ts>.jsonl` in plaintext. The run-log is in `data/`
(gitignored), so keys are not committed to git. However, users who share a run-log for
debugging unwittingly expose their keys.

This is inconsistent with `enrich.py`'s pattern, which deliberately avoids `str(exc)`:
```python
# Deliberately NOT logging str(exc) to avoid leaking auth headers
error_type=type(exc).__name__,
```

**Fix:** Strip keys from the URL before logging, or log only `type(exc).__name__`:
```python
except Exception as exc:
    logger.event("fetch_error", source="adzuna", term=term,
                 error_type=type(exc).__name__)  # never log str(exc) — URL contains keys
```

### SEC-2 (Minor): Proxy credentials could appear in run-log via `str(exc)`

**File:** `src/lcp/fetch_jobs.py:273`

```python
logger.event("fetch_error", board=board, term=term, error=str(exc))
```
If the Webshare backend is configured (`proxies.backend: webshare`), the proxy URL
`http://user:pass@host:port` is passed to JobSpy. A ProxyError or ConnectionError from
`requests` typically includes the proxy URL in `str(exc)`. This leaks credentials to
`data/runs/<ts>.jsonl`. The baseline config is `proxies.backend: none`, so this is only
triggered when a user explicitly configures Webshare.

**Fix:** Apply the same `error_type=type(exc).__name__` pattern.

### SEC-3 (Minor): `data_demo/` not in `.gitignore`

**File:** `.gitignore`

The `.gitignore` covers `data/` and `*.pkl` but NOT `data_demo/`. The directory currently
contains `jobs.parquet`, `staff.parquet`, `people_to_meet.json`, `shortlist.json`,
`state.sqlite`, `jobs.csv` from the live demo run (Amsterdam UMC staff, real job listings).
These are NOT gitignored (verified: `git check-ignore -v data_demo/jobs.parquet` returns
exit 1). Running `git add data_demo/` or `git add .` would commit real demo data including
LinkedIn profile references.

`data_demo/session.pkl` is protected by the `*.pkl` rule, but the other artifacts are not.

**Fix:** Add `data_demo/` to `.gitignore`:
```
data_demo/
!data_demo/.gitkeep
```

---

## 5. Proxy invariant — PASS

`src/lcp/fetch_staff.py` contains only two references to "proxy" and both are comments:
- L4: `StaffSpy runs on the operator's OWN IP. NEVER accepts or constructs a proxy.`
- L317-318: `# Never pass a proxy to LinkedInSession (hard rule; checked by tests).`

The `session_kwargs` dict built on L320 contains only `session_file`, optionally
`captcha_solver` and `solver_api_key`. No `proxy` or `proxies` key is ever added.
The test `tests/test_fetch_staff.py` asserts no proxy kwargs are present. PASS.

---

## 6. Determinism — PASS

**`rank_jobs`:** Sort key at `rank_jobs.py:263`:
```python
entries.sort(key=lambda e: (-e.score, e.job_id))
```
Scores are rounded to 6 decimal places, job_id is a stable string key. Independently
verified: two runs on identical input produce identical order.

**`score_people`:** Sort key at `score_people.py:243`:
```python
scored.sort(key=lambda p: (-p.warmth_score, p.profile_url))
```
`warmth_score` is rounded to 6 decimal places, `profile_url` is a stable string.

**Recency scorer with NaT/missing dates** (`rank_jobs.py:95–99`):
```python
try:
    if date_posted is None or pd.isna(date_posted):
        return 0.0, None
except (TypeError, ValueError):
    return 0.0, None
```
Tested with `None`, `pd.NaT`, and `float('nan')` — all return `(0.0, None)` without raising.
The live-demo regression is confirmed fixed. PASS.

---

## 7. "Wired not built" — PASS with one CLI docstring gap

**CLI wiring:** All stage modules (`fetch_jobs`, `rank_jobs`, `proxy_check`, `fetch_staff`,
`score_people`) are called via `_call_stage()` in `src/lcp/cli.py`. The `enrich` module is
wired into the MCP server (`mcp_server.py:91`), not the CLI. This is correct per the
deliverables (D4 owns enrichment exposure), but the CLI module-level docstring at
`cli.py:13` lists:
```
enrich.enrich_person(cfg, profile_url, logger) -> ContactInfo
```
implying a CLI command that doesn't exist. Users looking for `lcp enrich person` will find
nothing. The AC-022 verification gate (`pytest tests/test_enrich.py`) passes without a CLI
command, so this is not a gate failure — just a misleading docstring.

**MCP server entrypoint:** `wire_claude_desktop.py:37` generates:
```python
"command": str(py),
"args": ["-m", "lcp.mcp_server"],
```
`pyproject.toml` also registers `lcp-mcp = "lcp.mcp_server:main"`. Both point to the real
`main()` function. The `--selfcheck` path confirms tool registration. PASS.

---

## 8. Observability — PASS

Every stage calls `logger.event(stage, count_out=N, ...)`. The `runlog.funnel()` function
reads the latest `.jsonl` and maps stage names to funnel slots:
```python
key = {
    "fetch_jobs": "jobs_fetched", "rank_jobs": "shortlisted",
    "fetch_staff": "people", "score_people": "people_to_meet",
    "draft_outreach": "drafts",
}
```
Independently verified: emitting 5 events and reading funnel() returns correct counts.
`lcp doctor` calls `runlog.funnel()` and prints it. `docs/EXAMPLE_RESULT.md` shows a real
funnel table (46 jobs → 15 shortlisted → 1 company → 4 people → 4 to meet → 1 draft).
PASS.

---

## 9. Additional findings (nits)

### NITS-1: `kaspr` in example waterfall has no provider implementation

**File:** `config/config.example.yaml:123` and `src/lcp/enrich.py:272–278`

The example config waterfall is `[apollo, prospeo, kaspr, hunter]`. The `_REGISTRY` in
`enrich.py` contains `apollo`, `hunter`, `prospeo`, `null` — no `kaspr`. When the waterfall
is built, `kaspr` triggers `_LOG.warning("Unknown enrichment provider 'kaspr' — skipped")`.
Operators switching to `enrichment.mode: python` (instead of the `mcp` baseline) expecting
Kaspr to work will be silently disappointed. Since the baseline mode is `mcp`, this doesn't
affect normal operation, but it is a misleading config default.

**Fix:** Either add a stub `KasprProvider` with a clear "use via MCP, not python waterfall"
note, or remove `kaspr` from the python-mode waterfall and document in the config comment
that Kaspr is MCP-only.

### NITS-2: `HunterProvider` is always a no-op even with a valid key

**File:** `src/lcp/enrich.py:205–215`

`HunterProvider.lookup()` always returns `None` once the key is present, with the comment
"return None and let Apollo/Prospeo handle LinkedIn-URL → email." This is documented
behaviour, but the waterfall advertises Hunter and users won't receive an error. The
no-op is harmless, but listing a provider that silently never hits is confusing.

### NITS-3: Missing `lcp enrich person` CLI subcommand (AC-022 action discrepancy)

**File:** `src/lcp/cli.py` (no `enrich_app`)

GOAL.md AC-022 describes the action as `lcp enrich person` but no such subcommand is
implemented. The `enrich_person` stage is only accessible via the MCP server's gated
`enrich_person` tool. The AC-022 verification gate (pytest) passes because enrichment is
fully covered in tests. Still, any user reading the GOAL and trying `lcp enrich person`
will get `Error: No such command 'enrich'`.

### NITS-4: No test covers the Adzuna key-in-URL log scenario

**File:** `tests/test_fetch_jobs.py` (gap)

`test_enrich.py` has `test_key_not_logged` that sets real env vars and asserts they don't
appear in the run-log. No equivalent test exists for the Adzuna fetcher. This allowed
SEC-1 to exist without a failing test.

---

## 10. Summary table

| Area | Verdict | Severity | File:line |
|---|---|---|---|
| All 14 scorers + 108 tests | PASS | — | — |
| Confirmation gates (run_staffspy, enrich_person) | PASS | — | mcp_server.py:79,87 |
| draft_outreach never sends | PASS | — | outreach.py:87 |
| Compliance: personal email → linkedin_dm | PASS | — | outreach.py:52-54 |
| require_human_send defaults True + validated | PASS | — | config.py:81, config.example.yaml:162 |
| StaffSpy proxy invariant | PASS | — | fetch_staff.py:317-318 |
| Rank/score determinism + NaT regression | PASS | — | rank_jobs.py:263, score_people.py:243 |
| Modules wired into CLI + MCP | PASS | — | cli.py, mcp_server.py |
| Observability funnel | PASS | — | runlog.py:59-81 |
| Adzuna keys leak to run-log via str(exc) | SEC-1 | Near-blocking | fetch_jobs.py:197 |
| Proxy creds leak to run-log via str(exc) | SEC-2 | Minor | fetch_jobs.py:273 |
| data_demo/ not gitignored | SEC-3 | Minor | .gitignore |
| kaspr in waterfall, no implementation | NITS-1 | Nit | config.example.yaml:123, enrich.py |
| HunterProvider always no-op | NITS-2 | Nit | enrich.py:205-215 |
| Missing lcp enrich CLI command | NITS-3 | Nit | cli.py |
| No test for Adzuna key-in-log | NITS-4 | Nit | tests/test_fetch_jobs.py |

---

## Top 3 things to fix

1. **SEC-1 (fetch_jobs.py:197)** — Stop logging `str(exc)` for the Adzuna error handler.
   The fix is one line: replace `error=str(exc)` with `error_type=type(exc).__name__`.
   This matches the pattern already used in `enrich.py` and eliminates the key-in-logfile
   exposure.

2. **SEC-3 (.gitignore)** — Add `data_demo/` (with `!data_demo/.gitkeep`) to `.gitignore`.
   The directory contains live-demo parquet/json from the Amsterdam UMC run and is currently
   unprotected from accidental `git add .`. One line fix.

3. **NITS-1 (config.example.yaml:123, enrich.py)** — Either implement a stub
   `KasprProvider` with a clear "MCP-only" comment, or remove `kaspr` from the python-mode
   waterfall in the example config. Silently skipping a listed provider in the config creates
   false expectations for users who switch to `enrichment.mode: python`.
