"""One small reader ("adapter") per college website.
Each college has: URL (the page that lists notices) and parse(page_html) -> list of
{"title", "description", "posted", "url"}   ("posted" = "YYYY-MM-DDTHH:MM:SS" or None if the site shows no date).
Everything here uses only Python's built-in libraries, so nothing needs installing."""
import re, html
from html.parser import HTMLParser
from datetime import datetime
from urllib.parse import urljoin

# ───────────────────────── tiny HTML reader (so we never depend on exact quote styles / spacing) ─────────────────────────
VOID = {"br", "img", "input", "meta", "link", "hr", "source", "area", "base", "col", "embed", "wbr", "track", "param"}
SKIP = {"script", "style", "svg", "noscript", "template"}
IMPLIED = {"li": {"ul", "ol"}, "tr": {"table", "tbody", "thead", "tfoot"}, "td": {"tr", "table"}, "th": {"tr", "table"},
           "p": {"div", "td", "li", "body"}, "option": {"select"}}

class Node:
    __slots__ = ("tag", "attrs", "kids", "parent")
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.kids, self.parent = tag, dict(attrs or {}), [], parent
    def classes(self): return (self.attrs.get("class") or "").split()
    def has_class(self, c): return c in self.classes()
    def texts(self):
        """every piece of visible text below this node, in order (scripts/styles skipped)"""
        for k in self.kids:
            if isinstance(k, str): yield k
            elif k.tag not in SKIP: yield from k.texts()
    def text(self): return clean(" ".join(self.texts()))
    def walk(self):
        for k in self.kids:
            if isinstance(k, Node):
                yield k
                yield from k.walk()
    def find_all(self, tag=None, cls=None, pred=None):
        for n in self.walk():
            if tag and n.tag != tag: continue
            if cls and not n.has_class(cls): continue
            if pred and not pred(n): continue
            yield n
    def find(self, *a, **k): return next(self.find_all(*a, **k), None)
    def href(self): return (self.attrs.get("href") or "").strip()

class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root"); self.stack = [self.root]
    def handle_starttag(self, tag, attrs):
        if tag in IMPLIED:
            for n in reversed(self.stack):
                if n.tag in IMPLIED[tag]: break
                if n.tag == tag:
                    del self.stack[self.stack.index(n):]; break
        node = Node(tag, [(k, v or "") for k, v in attrs], self.stack[-1])
        self.stack[-1].kids.append(node)
        if tag not in VOID: self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        node = Node(tag, [(k, v or "") for k, v in attrs], self.stack[-1]); self.stack[-1].kids.append(node)
    def handle_endtag(self, tag):
        if tag in VOID: return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]; return
    def handle_data(self, data): self.stack[-1].kids.append(data)

def parse_html(page):
    b = _Builder(); b.feed(page); b.close(); return b.root

def clean(x): return re.sub(r"\s+", " ", html.unescape(x or "")).strip()

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
def mon(s): return MONTHS.get((s or "")[:3].lower())
def iso(y, m, d, hh=0, mm=0):
    try: return datetime(int(y), int(m), int(d), hh, mm).isoformat()
    except (TypeError, ValueError): return None
def fullyear(y):
    y = int(y); return y + 2000 if y < 100 else y
def absu(base, href): return urljoin(base, href)

# ───────────────────────── SGGSCC (already live, kept exactly as before) ─────────────────────────
class SGGSCC:
    URL = "https://www.sggscc.ac.in/notices"
    ROW = re.compile(r'<tr>\s*<td data-title="Title">(.*?)</td>\s*<td data-title="Description"[^>]*>(.*?)</td>\s*'
                     r'<td data-title="Posted On">(.*?)</td>\s*<td data-title="Details">(.*?)</td>\s*</tr>', re.S)
    @staticmethod
    def parse(page):
        out = []
        for title, desc, posted, details in SGGSCC.ROW.findall(page):
            links = re.findall(r'href="([^"]+)"', details)
            try: when = datetime.strptime(clean(re.sub(r"<[^>]+>", " ", posted)), "%d %b %Y, %I:%M %p")
            except ValueError: continue
            d = clean(re.sub(r"<[^>]+>", " ", desc))
            out.append({"title": clean(re.sub(r"<[^>]+>", " ", title)), "description": "" if d.lower() == "refer to attachment" else d,
                        "posted": when.isoformat(), "url": links[0] if links else SGGSCC.URL})
        return out

# ───────────────────────── DDUC ─────────────────────────
class DDUC:
    URL = "https://ddu-college.du.ac.in/information/all-notices"
    @staticmethod
    def parse(page):
        out = []
        for a in parse_html(page).find_all("a", pred=lambda n: "website-data/notices/" in n.href()):
            t = a.text(); m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t)
            if not m: continue
            title = clean(t[m.end():])
            if title: out.append({"title": title, "description": "", "posted": iso(*m.groups()), "url": absu(DDUC.URL, a.href())})
        return out

# ───────────────────────── SRCC ─────────────────────────
class SRCC:
    URL = "https://www.srcc.edu/announcements"
    @staticmethod
    def parse(page):
        out = []
        for blk in parse_html(page).find_all(cls="tab-pane01"):
            t = blk.find(cls="announcementtime"); lst = blk.find(cls="annoncementList"); a = lst.find("a") if lst else None
            if not (t and a): continue
            m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", t.text())
            if not m or not mon(m.group(2)): continue
            out.append({"title": a.text(), "description": "", "posted": iso(m.group(3), mon(m.group(2)), m.group(1)), "url": absu(SRCC.URL, a.href())})
        return out

# ───────────────────────── Daulat Ram ─────────────────────────
class DRC:
    URL = "https://www.dr.du.ac.in/notifications-for-student"
    @staticmethod
    def parse(page):
        out = []
        for tr in parse_html(page).find_all("tr"):
            t = tr.find("td", cls="views-field-field-title-notice"); f = tr.find("td", cls="views-field-field-upload-pdf"); d = tr.find("td", cls="views-field-field-upload-date")
            if not (t and d): continue
            m = re.search(r"(\d{1,2})-(\d{1,2})-(\d{4})", d.text()); a = f.find("a") if f else None
            if not m: continue
            out.append({"title": t.text(), "description": "", "posted": iso(m.group(3), m.group(2), m.group(1)),
                        "url": absu(DRC.URL, a.href()) if a and a.href() else DRC.URL})
        return out

# ───────────────────────── Gargi / SGTB Khalsa / Hansraj  (same website maker: "card-date-col" date boxes) ─────────────────────────
def card_date(box):
    """date box holds a day number and 'Mon, YY' in either order, e.g. '12' + 'Oct, 26'  or  'Sep, 26' + '18'"""
    day = my = None
    for piece in (clean(x) for x in box.texts()):
        if not piece: continue
        m = re.fullmatch(r"([A-Za-z]{3,9})\.?,?\s*(\d{2,4})", piece)
        if m and mon(m.group(1)): my = (mon(m.group(1)), fullyear(m.group(2))); continue
        if re.fullmatch(r"\d{1,2}", piece): day = int(piece)
    return iso(my[1], my[0], day) if (my and day) else None

def card_rows(page, base):
    out = []
    for box in parse_html(page).find_all(cls="card-date-col"):
        row = box.parent
        while row and row.tag not in ("tr", "li"): row = row.parent
        if not row: continue
        a = row.find("a", pred=lambda n: n.href() and not n.href().startswith(("#", "javascript")))
        if row.tag == "tr":
            tds = [k for k in row.kids if isinstance(k, Node) and k.tag == "td"]
            title = next((td.text() for td in tds if not td.find(cls="card-date-col") and not td.find("a") and td.text()), "")
        else:
            det = row.find(cls="card-detail-col")
            if not det: continue                                   # the little "Latest Updates" side box repeats the same notices
            ta = det.find("a", pred=lambda n: n.text() and not n.find("img"))
            title = ta.text() if ta else det.text(); a = ta or a
        when = card_date(box)
        if title and when: out.append({"title": title, "description": "", "posted": when, "url": absu(base, a.href()) if a else base})
    return out

class Gargi:
    URL = "https://www.gargicollege.in/notice/students"
    parse = staticmethod(lambda page: card_rows(page, Gargi.URL))
class SGTBK:
    URL = "https://sgtbkhalsadu.ac.in/notice/students"
    parse = staticmethod(lambda page: card_rows(page, SGTBK.URL))
class Hansraj:
    URL = "https://www.hansrajcollege.ac.in/announcements/general"
    parse = staticmethod(lambda page: card_rows(page, Hansraj.URL))

# ───────────────────────── Miranda House ─────────────────────────
class Miranda:
    URL = "https://www.mirandahouse.ac.in/notice.php?type=GENERAL"
    @staticmethod
    def parse(page):
        out = []; root = parse_html(page)
        table = root.find("table", pred=lambda n: n.attrs.get("id") == "table2") or root
        for tr in table.find_all("tr"):
            tds = [k for k in tr.kids if isinstance(k, Node) and k.tag == "td"]
            if len(tds) < 3: continue
            m = re.search(r"(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})", tds[2].text())
            if not (m and mon(m.group(2))): continue
            a = tr.find("a", pred=lambda n: n.href())
            out.append({"title": tds[1].text(), "description": "", "posted": iso(m.group(3), mon(m.group(2)), m.group(1)),
                        "url": absu(Miranda.URL, a.href()) if a else Miranda.URL})
        return out

# ───────────────────────── Kirori Mal ─────────────────────────
class KMC:
    URL = "https://kmc.du.ac.in/news/notices"
    @staticmethod
    def parse(page):
        out = []
        for tr in parse_html(page).find_all("tr"):
            tm = tr.find("time"); t = tr.find("td", cls="st__t"); ta = t.find("a") if t else None
            if not (tm and ta): continue
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", tm.attrs.get("datetime", ""))
            if not m: continue
            files = [a.href() for a in tr.find_all("a", cls="st__ib") if "download" not in a.classes() and not a.has_class("st__ib--dl")]
            link = files[0] if len(files) == 1 else ta.href()          # one attachment -> open it directly, else the notice page
            out.append({"title": ta.text(), "description": "", "posted": iso(*m.groups()), "url": absu(KMC.URL, link)})
        return out

# ───────────────────────── Sri Venkateswara  (site shows no dates) ─────────────────────────
class Venky:
    URL = "https://www.svc.ac.in/notices/students"
    @staticmethod
    def parse(page):
        out = []; root = parse_html(page)
        table = root.find("table", pred=lambda n: n.attrs.get("id") == "noticeTable") or root
        for tr in table.find_all("tr"):
            t = tr.find(cls="listing-title"); a = tr.find("a", pred=lambda n: n.href())
            if t and t.text(): out.append({"title": t.text(), "description": "", "posted": None, "url": absu(Venky.URL, a.href()) if a else Venky.URL})
        return out

# ───────────────────────── Ramjas  (site shows no dates; newest first) ─────────────────────────
class Ramjas:
    URL = "https://ramjas.du.ac.in/college/web/index.php?r=students-zone/students-notice"
    @staticmethod
    def parse(page):
        out = []
        for ul in parse_html(page).find_all("ul", cls="list-group"):
            if "notice board" not in ul.text().lower()[:40]: continue
            for li in ul.find_all("li"):
                a = li.find("a", pred=lambda n: n.href())
                if li.has_class("active") or not a or not a.text(): continue
                out.append({"title": a.text(), "description": "", "posted": None, "url": absu(Ramjas.URL, a.href())})
                if len(out) >= 80: return out
            if out: break
        return out

# ───────────────────────── DCAC ─────────────────────────
class DCAC:
    URL = "https://dcac.du.ac.in/home/notification/notice"
    @staticmethod
    def parse(page):
        out = []
        for li in parse_html(page).find_all("li", pred=lambda n: n.find(cls="post-date") and n.find("h3")):
            a = li.find("h3").find("a"); m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s*(\d{4})", li.find(cls="post-date").text())
            if not (a and m and mon(m.group(1))): continue
            out.append({"title": a.text(), "description": "", "posted": iso(m.group(3), mon(m.group(1)), m.group(2)), "url": absu(DCAC.URL, a.href())})
        return out

# id (folder name on the website) -> adapter
COLLEGES = {"sggscc": SGGSCC, "dduc": DDUC, "srcc": SRCC, "drc": DRC, "gargi": Gargi, "sgtbk": SGTBK, "hansraj": Hansraj,
            "mirandahouse": Miranda, "kmc": KMC, "venky": Venky, "ramjas": Ramjas, "dcac": DCAC}
