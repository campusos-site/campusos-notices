"""SGGSCC (https://www.sggscc.ac.in/notices): one server-rendered table, columns Title / Description /
Posted On / Details. One adapter per college; each exposes parse(html) -> list[dict]."""
import re, html
from datetime import datetime

URL = "https://www.sggscc.ac.in/notices"
ROW = re.compile(r'<tr>\s*<td data-title="Title">(.*?)</td>\s*<td data-title="Description"[^>]*>(.*?)</td>\s*'
                 r'<td data-title="Posted On">(.*?)</td>\s*<td data-title="Details">(.*?)</td>\s*</tr>', re.S)

def _clean(x):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x))).strip()

def parse(page):
    out = []
    for title, desc, posted, details in ROW.findall(page):
        links = re.findall(r'href="([^"]+)"', details)
        try:
            when = datetime.strptime(_clean(posted), "%d %b %Y, %I:%M %p")
        except ValueError:
            continue                      # skip rows we can't date rather than guess
        d = _clean(desc)
        out.append({"title": _clean(title), "description": "" if d.lower() == "refer to attachment" else d,
                    "posted": when.isoformat(), "url": links[0] if links else URL})
    return out
