# Job Sources

This document describes the job sources supported by the pipeline: the primary
JobSpy boards and the supplemental source registry (`lcp/sources.py`).

---

## Primary sources (JobSpy)

Controlled by `jobs.site_names` in `config/config.yaml`.

| Board | Key | Coverage | Notes |
|---|---|---|---|
| LinkedIn | `linkedin` | Global | Best for NL; requires residential proxy at volume |
| Indeed | `indeed` | NL + global | Largest NL index; `country_indeed: Netherlands` |
| Glassdoor | `glassdoor` | Global | Good salary data |
| Google Jobs | `google` | Global | Aggregates many boards |
| Zip Recruiter | `zip_recruiter` | US-primary | Less relevant for NL |

---

## Supplemental sources (SOURCE_REGISTRY)

Controlled by `jobs.sources.<name>.enabled` in `config/config.yaml`.
All default to `false`.  Enable per-source as needed.

Each adapter: self-gates on its enabled flag, degrades gracefully on errors
(returns `[]` + logs `fetch_error` with `error_type` only — never raw exception
strings that could contain secrets or PII).

---

### Adzuna

| Property | Value |
|---|---|
| Config key | `jobs.sources.adzuna` |
| Requires key | Yes (`ADZUNA_APP_ID` + `ADZUNA_APP_KEY` in `.env`) |
| Free tier | Yes — register at https://developer.adzuna.com (100 req/day free) |
| Coverage | NL, UK, DE, FR, AU + others (see Adzuna country list) |
| Keywords | Uses `jobs.search_terms` |

To enable:

```yaml
jobs:
  sources:
    adzuna:
      enabled: true
      country: "nl"      # or "gb", "de", etc.
```

Add to `.env`:

```
ADZUNA_APP_ID=your_app_id_here
ADZUNA_APP_KEY=your_app_key_here
```

SEC-1: The Adzuna URL embeds `app_id`/`app_key` as query parameters.  The adapter
never logs `str(exc)` — only `error_type=<ClassName>`.

---

### Arbetsformedlingen (JobTech / Platsbanken)

| Property | Value |
|---|---|
| Config key | `jobs.sources.arbetsformedlingen` |
| Requires key | No |
| Free tier | Fully free, no registration |
| Coverage | Sweden (all Swedish job listings via Platsbanken) |
| Endpoint | `https://jobsearch.api.jobtechdev.se/search` |
| Keywords | `jobs.sources.arbetsformedlingen.keywords` (falls back to `jobs.search_terms`) |

Confirmed working as of 2026-06-27.  Response shape: `hits[]` with `id`,
`headline`, `employer.name`, `workplace_address.{municipality, region}`,
`webpage_url`, `publication_date`, `description.text`.

To enable:

```yaml
jobs:
  sources:
    arbetsformedlingen:
      enabled: true
      keywords: ["data engineer", "machine learning engineer"]
      limit: 100
```

No `.env` changes needed.

---

### EURAXESS

| Property | Value |
|---|---|
| Config key | `jobs.sources.euraxess` |
| Requires key | No |
| Free tier | N/A |
| Coverage | EU-wide academic and research positions |
| Status | **No public API available (as of 2026-06-27)** |

**Investigation result**: All programmatic access to `euraxess.ec.europa.eu` is
blocked by the site's WAF / CloudFront rules.  Every probed path (`/api/jobs`,
`/api/jobs/search`, `/europass/rest/jobs/search`, `/jobs/search`) returns
HTTP 403 "Disallowed by robots.txt".  No documented public REST or RSS endpoint
exists.

The adapter is wired and config-toggleable.  When `enabled: true`, it logs a
`source_skip` event with `reason: no_public_api` and returns `[]`.  Enable it
here once an official API becomes available — no changes to `fetch_jobs.py` needed.

```yaml
jobs:
  sources:
    euraxess:
      enabled: false   # no-op until public API confirmed
```

---

### AcademicTransfer

| Property | Value |
|---|---|
| Config key | `jobs.sources.academictransfer` |
| Requires key | No |
| Free tier | N/A |
| Coverage | NL academic jobs (Dutch universities, research institutes, NWO, etc.) |
| Status | **No public API available (as of 2026-06-27)** |

**Investigation result**: `academictransfer.com` is a Vue.js SPA.  All probed
API paths returned HTTP 404: `/api/jobs/?format=json`, `/en/jobs.rss/`,
`/nl/jobs.rss/`, `https://api.academictransfer.com/v1/jobs`.  No documented
public REST or RSS endpoint exists.

The adapter is wired and config-toggleable.  When `enabled: true`, it logs a
`source_skip` event with `reason: no_public_api` and returns `[]`.

```yaml
jobs:
  sources:
    academictransfer:
      enabled: false   # no-op until public API confirmed
```

---

## Adding a new source

1. Implement an adapter function in `src/lcp/sources.py` with signature:
   ```python
   def _fetch_mysource(
       cfg: Config,
       logger: RunLogger,
       *,
       _client: Any = None,
   ) -> list[JobPost]:
   ```
2. Register it in `SOURCE_REGISTRY` at the bottom of `sources.py`.
3. Add a `jobs.sources.mysource:` block to `config/config.example.yaml`.
4. Write tests in `tests/test_sources.py` (disabled→[], normalization, error→[]).
5. Document it here.

Rules all adapters must follow:
- Gate on `cfg.get("jobs.sources.<name>.enabled", False)` — return `[]` if false.
- Never log `str(exc)` — log `error_type=type(exc).__name__` only (SEC-1).
- `job_id = f"<source>:<stable-id>"` (use URL hash if no stable ID).
- Return `[]` on any network/parse failure (degrade gracefully).
- Accept `_client: Any = None` (defaults to `requests`) for test isolation.
