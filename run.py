"""python3 run.py                       fetch every college in colleges.py, write data/<id>.json
   python3 run.py --from-file dduc page.html     offline test with a saved page
Safe by design: if a college's page can't be read (or looks broken) its old JSON is kept, the other colleges still update,
and the problem is listed as a warning in the run log and in data/_status.json."""
import json, sys, os, re, hashlib, ssl, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from colleges import COLLEGES

KEEP = 20                                   # <<< how many newest notices are kept per college (change this number if you want more or fewer)
MIN_ROWS = 5                                # fewer than this = the page layout probably changed
LEGACY_ID_BY_URL = {"sggscc"}               # ids made from the link only (keeps old ids stable); others use link + title
UA = "CampusOS-notices/1.0 (student notices reader; +https://github.com/campusos-site/campusos-notices)"
IST = timezone(timedelta(hours=5, minutes=30))
TAGS = [("Exams", r"exam|practical|viva|date ?sheet|assessment|re-?appear|admit card"), ("Results", r"result|marksheet|revaluation"),
        ("Admissions", r"admission|cut ?-?off|merit|seat|registration|counselling|enrol"), ("Fees", r"\bfee|scholarship|refund|payment"),
        ("Holidays", r"holiday|closed|vacation|will remain close"), ("Events", r"workshop|seminar|fest|competition|lecture|webinar|orientation|event"),
        ("Placements", r"placement|recruit|internship|job")]

def tag(title):
    return [n for n, rx in TAGS if re.search(rx, title, re.I)] or ["General"]

FETCH_TIMEOUT = int(os.environ.get("FETCH_TIMEOUT", "20"))   # seconds to wait for a college website before giving up

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    last = None
    for attempt in range(2):
        for ctx in (None, ssl._create_unverified_context()):      # some college sites have an incomplete certificate chain
            try:
                with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT, context=ctx) as r:
                    raw = r.read()
                    return raw.decode(r.headers.get_content_charset() or "utf-8", "ignore")
            except urllib.error.URLError as e:
                last = e
                if ctx is None and isinstance(getattr(e, "reason", None), ssl.SSLError): continue
                break
            except Exception as e:
                last = e; break
        time.sleep(3)
    raise RuntimeError(f"could not fetch {url}: {last}")

def build(cid, page, adapter, prev):
    rows = adapter.parse(page)
    if len(rows) < MIN_ROWS:
        raise RuntimeError(f"only {len(rows)} notices read - the college page layout probably changed, keeping old data")
    old_dateless = {n["id"]: n["posted"] for n in prev.get("notices", []) if n.get("dated") is False}
    now = datetime.now(IST).replace(tzinfo=None).isoformat(timespec="minutes")
    seen, out = set(), []
    for r in rows:
        key = r["url"] if cid in LEGACY_ID_BY_URL else r["url"] + "|" + r["title"]
        r["id"] = hashlib.sha1(key.encode()).hexdigest()[:12]
        if r["id"] in seen: continue
        seen.add(r["id"])
        if not r.get("posted"):                          # site shows no date: remember when WE first saw it
            r["posted"] = old_dateless.get(r["id"], now); r["dated"] = False
        r["tags"] = tag(r["title"])
        out.append(r)
    out.sort(key=lambda r: r["posted"], reverse=True)    # stable: same-day notices keep the website's own order
    return {"college": cid, "source": adapter.URL, "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "notices": out[:KEEP]}

def load_json(path, default):
    try: return json.load(open(path, encoding="utf8"))
    except Exception: return default

if __name__ == "__main__":
    args = sys.argv[1:]
    os.makedirs("data", exist_ok=True)
    jobs = {}
    if args[:1] == ["--from-file"]:
        jobs[args[1]] = open(args[2], encoding="utf8", errors="ignore").read()
    else:
        jobs = {cid: None for cid in COLLEGES}
    failing, ok = {}, []
    pages, errors = dict(jobs), {}
    todo = [cid for cid, pg in jobs.items() if pg is None]
    if todo:                                                           # different websites, so fetching together is polite
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {cid: ex.submit(fetch, COLLEGES[cid].URL) for cid in todo}
            for cid, f in futs.items():
                try: pages[cid] = f.result()
                except BaseException as e: errors[cid] = e
    for cid in jobs:
        path = f"data/{cid}.json"
        try:
            if cid in errors: raise errors[cid]
            prev = load_json(path, {"notices": []})
            data = build(cid, pages[cid], COLLEGES[cid], prev)
            new_ids = {x["id"] for x in data["notices"]} - {x["id"] for x in prev["notices"]}
            json.dump(data, open(path, "w", encoding="utf8"), indent=1, ensure_ascii=False)
            ok.append(cid); print(f"{cid}: {len(data['notices'])} stored, {len(new_ids)} new")
        except BaseException as e:
            failing[cid] = str(e)[:300]; print(f"{cid}: FAILED - {e}"); print(f"::warning::{cid} notices not updated: {str(e)[:200]}")
    status = {"failing": failing, "ok": sorted(ok)}
    if load_json("data/_status.json", None) != status:             # only rewritten when something changes
        json.dump(status, open("data/_status.json", "w", encoding="utf8"), indent=1)
    sys.exit(1 if (failing and not ok) else 0)
