"""把 data/ 主数据构建为 docs/data/ 站点数据：core（轻量列表）+ abstracts（懒加载）+ meta。"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/data"
OUT.mkdir(parents=True, exist_ok=True)

papers = json.loads((ROOT / "data/papers.json").read_text())

core, abstracts = [], {}
for p in papers:
    core.append({
        "id": p["id"], "doi": p.get("doi"),
        "ti": p.get("title_en") or "", "tz": p.get("title_zh"),
        "au": [a["name"] for a in p.get("authors", [])],
        "ai": [a.get("oa_id") for a in p.get("authors", [])],
        "y": p.get("year"), "j": p.get("journal"),
        "c": p.get("cited_by_count", 0),
        "b": p.get("branches", []), "tg": p.get("tags", []),
        "fs": p.get("first_seen"), "sup": bool(p.get("superseded")),
        "cc": p.get("coarse_card"),
    })
    if p.get("abstract_en"):
        abstracts[p["id"]] = p["abstract_en"]

updates = sorted((ROOT / "data/updates").glob("*.json")) if (ROOT / "data/updates").exists() else []
latest = json.loads(updates[-1].read_text()) if updates else None

# 库内引用边（树叶连线 & 分支间引用流的数据）
ids = {p["id"] for p in papers}
edges = [[p["id"], d] for p in papers for d in p.get("refs_in_library", []) if d in ids]

(OUT / "core.json").write_text(json.dumps(core, ensure_ascii=False, separators=(",", ":")))
(OUT / "abstracts.json").write_text(json.dumps(abstracts, ensure_ascii=False, separators=(",", ":")))
(OUT / "edges.json").write_text(json.dumps(edges, ensure_ascii=False, separators=(",", ":")))
for name in ["branches.json", "tags.json", "watchlist.json"]:
    (OUT / name).write_text((ROOT / "data" / name).read_text())
(OUT / "meta.json").write_text(json.dumps({
    "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "total": len(core),
    "latest_update": latest,
}, ensure_ascii=False))
print(f"site data: {len(core)} papers, {len(abstracts)} abstracts")
