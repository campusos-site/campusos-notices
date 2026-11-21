"""python3 run.py                 fetch every college in COLLEGES, write data/<id>.json
   python3 run.py --from-file sggscc samples/sggscc_notices_page.html   (offline test)
Safe by design: if a parse returns 0 rows or looks broken, the old JSON is kept and the run fails loudly."""
import json, sys, os, re, hashlib, importlib, urllib.request
from datetime import datetime, timezone

COLLEGES = {"sggscc": "sggscc"}       # add: "hansraj": "hansraj", ...
KEEP = 60                                       # newest notices stored per college
UA = "CampusOS-notices/1.0 (student project; contact: campusos.site@gmail.com)"
TAGS = [("Exams", r"exam|practical|viva|date ?sheet|assessment|re-?appear"), ("Results", r"result|marksheet|revaluation"),
        ("Admissions", r"admission|cut ?-?off|merit|seat|registration|counselling|enrol"), ("Fees", r"\bfee|scholarship|refund|payment"),
        ("Holidays", r"holiday|closed|vacation"), ("Events", r"workshop|seminar|fest|competition|lecture|webinar|orientation|event"),
        ("Placements", r"placement|recruit|internship|job")]

def tag(title):
    return [n for n, rx in TAGS if re.search(rx, title, re.I)] or ["General"]

def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read().decode("utf8", "ignore")

def build(cid, page, mod):
    rows = sorted(mod.parse(page), key=lambda r: r["posted"], reverse=True)
    if len(rows) < 5: raise SystemExit(f"{cid}: only {len(rows)} notices parsed - layout probably changed, keeping old data")
    for r in rows:
        r["id"] = hashlib.sha1(r["url"].encode()).hexdigest()[:12]
        r["tags"] = tag(r["title"])
    return {"college": cid, "source": mod.URL, "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "notices": rows[:KEEP]}

if __name__ == "__main__":
    args = sys.argv[1:]
    os.makedirs("data", exist_ok=True)
    if args[:1] == ["--from-file"]:
        cid, path = args[1], args[2]
        jobs = {cid: (importlib.import_module(COLLEGES[cid]), open(path, encoding="utf8", errors="ignore").read())}
    else:
        jobs = {}
        for cid, m in COLLEGES.items():
            mod = importlib.import_module(m); jobs[cid] = (mod, None)
    failed = []
    for cid, (mod, page) in jobs.items():
        try:
            data = build(cid, page if page is not None else fetch(mod.URL), mod)
            old = f"data/{cid}.json"
            prev = json.load(open(old)) if os.path.exists(old) else {"notices": []}
            new_ids = {n["id"] for n in data["notices"]} - {n["id"] for n in prev["notices"]}
            json.dump(data, open(old, "w", encoding="utf8"), indent=1, ensure_ascii=False)
            print(f"{cid}: {len(data['notices'])} stored, {len(new_ids)} new")
        except BaseException as e:
            failed.append(cid); print(f"{cid}: FAILED - {e}")
    sys.exit(1 if failed else 0)
