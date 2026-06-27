"""DEMO ONLY — minimal authorized live people fetch using the operator's Firefox LinkedIn session.

Builds a requests session from the Firefox li_at + JSESSIONID cookies, runs StaffSpy for ONE
company at low volume (5 profiles), writes data_demo/staff_live.parquet. Never logs cookie values.
Falls back cleanly (prints FALLBACK) if cookies/login/captcha block it.
"""
from __future__ import annotations
import glob, pickle, shutil, sqlite3, sys, tempfile, os
from pathlib import Path

import requests

COMPANY = sys.argv[1] if len(sys.argv) > 1 else "Amsterdam UMC"
MAX = 5
OUT = Path("data_demo/staff_live.parquet")
SESS = Path("data_demo/session.pkl")
OUT.parent.mkdir(parents=True, exist_ok=True)


def read_ff_cookies() -> dict:
    home = Path.home()
    dbs = glob.glob(str(home / "Library/Application Support/Firefox/Profiles/*/cookies.sqlite"))
    for db in dbs:
        tmp = Path(tempfile.gettempdir()) / "ff_cookies_demo.sqlite"
        try:
            shutil.copy2(db, tmp)
            con = sqlite3.connect(str(tmp)); con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT name,value FROM moz_cookies WHERE host LIKE '%linkedin.com' "
                "AND name IN ('li_at','JSESSIONID')").fetchall()
            con.close()
            ck = {r["name"]: r["value"] for r in rows}
            if "li_at" in ck:
                return ck
        except Exception:
            continue
        finally:
            try: tmp.unlink()
            except Exception: pass
    return {}


def build_session(ck: dict) -> requests.Session:
    s = requests.Session()
    for name, val in ck.items():
        for dom in (".linkedin.com", ".www.linkedin.com"):
            s.cookies.set(name, val, domain=dom, path="/")
    s.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"})
    return s


def main() -> int:
    ck = read_ff_cookies()
    if "li_at" not in ck or "JSESSIONID" not in ck:
        print(f"FALLBACK: missing cookies (have: {sorted(ck)} — need li_at + JSESSIONID)")
        return 2
    print(f"cookies OK (li_at + JSESSIONID present); building session for company={COMPANY!r}")
    pickle.dump(build_session(ck), open(SESS, "wb"))
    try:
        from staffspy import LinkedInAccount
        acct = LinkedInAccount(session_file=str(SESS), log_level=1)
        df = acct.scrape_staff(company_name=COMPANY, extra_profile_data=True, max_results=MAX)
    except Exception as exc:
        print(f"FALLBACK: live fetch failed ({type(exc).__name__}: {str(exc)[:160]})")
        return 3
    if df is None or len(df) == 0:
        print("FALLBACK: 0 staff returned (company match or session issue)")
        return 4
    df.to_parquet(OUT, index=False)
    print(f"LIVE OK: {len(df)} staff -> {OUT}")
    print("columns:", list(df.columns)[:20])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
