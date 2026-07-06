"""手动补漏工具：按 DOI 或题目把指定论文加进 data/papers.json。
用法：python scripts/add_by_doi.py "doi:10.1086/705716" "Robots and Jobs: Evidence from US Labor Markets"
     python scripts/add_by_doi.py --queue   # 处理 data/manual_queue.txt（每行一条，成功后移除该行）
- doi: 前缀走精确取回；否则按题目搜索取第一条
- 已在池内则跳过；新增走 v3 分类；refs_in_library 留空（下次全量补抓时回填）
"""
import json, os, sys, time
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from classify import classify
from fetch_weekly import restore_abstract, to_paper, MAILTO

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.openalex.org/works"
API_KEY = os.environ.get("OPENALEX_API_KEY") or os.environ.get("OPENALEX_APIKEY")

def _params(extra):
    p = dict(extra, mailto=MAILTO)
    if API_KEY:
        p["api_key"] = API_KEY
    return p

def main(queries):
    queue_mode = queries == ["--queue"]
    queue_f = ROOT / "data/manual_queue.txt"
    if queue_mode:
        if not queue_f.exists():
            print("队列为空"); return
        queries = [l.strip() for l in queue_f.read_text().splitlines() if l.strip() and not l.startswith("#")]
    papers = json.loads((ROOT / "data/papers.json").read_text())
    known = {p["id"] for p in papers} | {p["doi"] for p in papers if p.get("doi")}
    today = date.today().isoformat()
    added, done = 0, []
    for q in queries:
        try:
            if q.lower().startswith("doi:"):
                r = requests.get(f"{API}/https://doi.org/{q[4:]}", params=_params({}), timeout=60)
                r.raise_for_status()
                w = r.json()
            else:
                r = requests.get(API, params=_params({"filter": f"title.search:{q}", "per-page": 5}), timeout=60)
                r.raise_for_status()
                res = r.json().get("results", [])
                if not res:
                    print(f"✗ 未找到: {q}"); done.append(q); continue
                w = res[0]
        except Exception as e:
            print(f"✗ 请求失败: {q} ({e})"); continue
        w["abstract_inverted_index"] = w.get("abstract_inverted_index")
        venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "其他"
        p = to_paper(w, venue, ["manual_add"], today)
        if p["id"] in known or (p["doi"] and p["doi"] in known):
            print(f"· 已在池内: {p['title_en'][:50]}"); continue
        p["branches"], p["tags"] = classify(p["title_en"], p["abstract_en"], p["journal"], p["type"])
        papers.append(p); known.add(p["id"]); added += 1; done.append(q)
        print(f"✓ 已加入: {p['title_en'][:60]} | {venue} {p['year']} | 分支 {p['branches']}")
        time.sleep(0.3)
    if added:
        (ROOT / "data/papers.json").write_text(json.dumps(papers, ensure_ascii=False, indent=1))
    if queue_mode and done:
        rest = [l for l in queue_f.read_text().splitlines() if l.strip() not in done]
        queue_f.write_text("\n".join(rest) + ("\n" if rest else ""))
    print(f"共新增 {added} 篇")

if __name__ == "__main__":
    main(sys.argv[1:])
