"""每周增量抓取：OpenAlex 20 源（Technovation 除外）× 全量关键词 + watchlist 学者。
- 断点状态在 data/state.json；新增写入 data/papers.json 并生成 data/updates/YYYY-MM-DD.json
- API 礼貌：~4 req/s，429 退避一次后保存进度退出（下周自然补上）
"""
import json, os, re, sys, time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from classify import classify

ROOT = Path(__file__).resolve().parent.parent
MAILTO = "haonanyan360@gmail.com"
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY") or os.environ.get("OPENALEX_APIKEY")
API = "https://api.openalex.org/works"

SOURCES = [
    ("NBER WP", "locations.source.id", "S2809516038"),
    ("AER", "primary_location.source.issn", "0002-8282"),
    ("QJE", "primary_location.source.issn", "0033-5533"),
    ("JPE", "primary_location.source.issn", "0022-3808"),
    ("Econometrica", "primary_location.source.issn", "0012-9682"),
    ("RES", "primary_location.source.issn", "0034-6527"),
    ("JEL", "primary_location.source.issn", "0022-0515"),
    ("JEP", "primary_location.source.issn", "0895-3309"),
    ("ReStat", "primary_location.source.issn", "0034-6535"),
    ("AEJ-Applied", "primary_location.source.issn", "1945-7782"),
    ("AEJ-Macro", "primary_location.source.issn", "1945-7707"),
    ("AEJ-Micro", "primary_location.source.issn", "1945-7669"),
    ("AEJ-Policy", "primary_location.source.issn", "1945-7731"),
    ("JIE", "primary_location.source.issn", "0022-1996"),
    ("JFE", "primary_location.source.issn", "0304-405X"),
    ("RFS", "primary_location.source.issn", "0893-9454"),
    ("JEEA", "primary_location.source.issn", "1542-4766"),
    ("JEG", "primary_location.source.issn", "1468-2702"),
    ("RJE", "primary_location.source.issn", "0741-6261"),
]

KEYWORDS = [
    "innovation", "patent", "R&D",
    "creative destruction", "endogenous growth", "technological change",
    "technology adoption", "technology diffusion", "knowledge spillover",
    "intellectual property", "venture capital", "entrepreneurship",
    "inventor", "automation", "skill-biased", "industrial policy",
    "science funding", "scientific research", "green innovation",
    "clean technology", "directed technical change", "pharmaceutical",
    "drug development", "artificial intelligence", "machine learning",
    "digital platform", "productivity growth", "knowledge production",
    "invention", "startup",
]


def restore_abstract(inv):
    if not inv:
        return None
    pos = [(i, w) for w, idxs in inv.items() for i in idxs]
    return " ".join(w for _, w in sorted(pos)) or None


def get(params, retried=False):
    params = dict(params, mailto=MAILTO)
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY
    r = requests.get(API, params=params, timeout=60)
    if r.status_code == 429:
        if retried:
            raise RuntimeError("openalex-budget")
        time.sleep(min(int(r.headers.get("retry-after", 60)), 120))
        return get(params, retried=True)
    r.raise_for_status()
    time.sleep(0.25)
    return r.json()


def to_paper(w, journal, channels, today):
    oid = w["id"].rsplit("/", 1)[-1]
    doi = (w.get("doi") or "").replace("https://doi.org/", "").lower() or None
    return {
        "id": oid, "doi": doi,
        "title_en": w.get("display_name") or w.get("title") or "",
        "title_zh": None,
        "authors": [{"name": a["author"].get("display_name", ""),
                     "oa_id": (a["author"].get("id") or "").rsplit("/", 1)[-1] or None}
                    for a in w.get("authorships", [])],
        "year": w.get("publication_year"),
        "date": w.get("publication_date"),
        "journal": journal,
        "type": w.get("type"),
        "cited_by_count": w.get("cited_by_count", 0),
        "abstract_en": restore_abstract(w.get("abstract_inverted_index")),
        "abstract_src": "openalex" if w.get("abstract_inverted_index") else None,
        "branches": [], "tags": [],
        "source_channels": channels,
        "first_seen": today,
        "refs_in_library": [],
        "wp_of": None, "published_as": None, "superseded": False,
        "exists_in_zotero": "[新增]", "tier": None, "coarse_card": None,
    }


def main():
    today = date.today().isoformat()
    papers = json.loads((ROOT / "data/papers.json").read_text())
    known_ids = {p["id"] for p in papers}
    known_dois = {p["doi"] for p in papers if p.get("doi")}
    state_f = ROOT / "data/state.json"
    state = json.loads(state_f.read_text()) if state_f.exists() else {}
    since = state.get("last_run", (date.today() - timedelta(days=8)).isoformat())

    select = ("id,doi,title,display_name,authorships,publication_year,publication_date,"
              "type,cited_by_count,abstract_inverted_index,language")
    new = {}
    budget_hit = False
    try:
        for journal, fkey, fval in SOURCES:
            for kw in KEYWORDS:
                filt = f'{fkey}:{fval},from_publication_date:{since},title_and_abstract.search:"{kw}"'
                cursor = "*"
                while cursor:
                    js = get({"filter": filt, "per-page": 200, "cursor": cursor, "select": select})
                    for w in js.get("results", []):
                        p = to_paper(w, journal, [f"kw:{kw}"], today)
                        if p["id"] in known_ids or (p["doi"] and p["doi"] in known_dois):
                            continue
                        if p["id"] in new:
                            new[p["id"]]["source_channels"].append(f"kw:{kw}")
                        else:
                            new[p["id"]] = p
                    cursor = js.get("meta", {}).get("next_cursor")
        # watchlist 学者雷达（不限期刊）
        wl = json.loads((ROOT / "data/watchlist.json").read_text())
        for a in wl:
            if not a.get("oa_id"):
                continue
            filt = f'author.id:{a["oa_id"]},from_publication_date:{since}'
            js = get({"filter": filt, "per-page": 100, "select": select})
            for w in js.get("results", []):
                src = f'watchlist:{a["name"]}'
                venue = "预印/其他"
                p = to_paper(w, venue, [src], today)
                if p["id"] in known_ids or (p["doi"] and p["doi"] in known_dois):
                    continue
                if p["id"] in new:
                    new[p["id"]]["source_channels"].append(src)
                else:
                    new[p["id"]] = p
    except RuntimeError as e:
        if "openalex-budget" in str(e):
            budget_hit = True  # 保存已抓部分，下周自然补上
        else:
            raise

    for p in new.values():
        p["branches"], p["tags"] = classify(p["title_en"], p["abstract_en"], p["journal"], p["type"])

    papers.extend(new.values())
    (ROOT / "data/papers.json").write_text(json.dumps(papers, ensure_ascii=False, indent=1))
    upd_dir = ROOT / "data/updates"
    upd_dir.mkdir(exist_ok=True)
    (upd_dir / f"{today}.json").write_text(json.dumps({
        "date": today, "since": since, "new_count": len(new),
        "new_ids": sorted(new), "budget_hit": budget_hit,
    }, ensure_ascii=False, indent=1))
    if not budget_hit:
        state["last_run"] = today
        state_f.write_text(json.dumps(state))
    print(f"新增 {len(new)} 篇（since {since}）budget_hit={budget_hit}")


if __name__ == "__main__":
    main()
