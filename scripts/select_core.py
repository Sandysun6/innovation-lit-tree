"""精简版"核心模式"选池：从 data/papers.json 择优 ≤300 篇，回写 core/core_reasons 等字段。

口径见项目 plan `quality_reports/plans/2026-07-06_核心模式_精简版文献树.md` 与
`04_数据schema与分支v3.md` 的"核心选池"章节。月度换血只改 data/core_overrides.json。

用法：python scripts/select_core.py   （构建站点数据前先跑一遍）
"""
import json
import math
import collections
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUDGET = 300          # 核心层总预算（硬上限）
NEW_YEAR = 2021       # year >= 此值 记为"新锐可选"
NEW_SEATS = 80        # 新锐保留席
BRANCH_FLOOR = 8      # 每个非空分支的核心保底数
SURVEY_BRANCH = "11"  # 综述与 Handbook 支（综述共引信号来源）
TOP_JOURNALS = {"AER", "QJE", "JPE", "Econometrica", "REStud", "RES",
                "AEJ-Applied", "AEJ-Macro", "AEJ-Policy", "AEJ-Micro",
                "JF", "RFS", "JFE", "JPubE", "JDE"}


def norm_name(n):
    return " ".join((n or "").lower().replace(".", "").split())


def lastfirst(n):
    parts = norm_name(n).split()
    return (parts[-1], parts[0][0]) if parts and parts[0] else ("", "")


def zscores(values):
    """返回一个 id→z 的函数所需的 (mean, std)。"""
    xs = list(values)
    if not xs:
        return 0.0, 1.0
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / len(xs)
    return m, math.sqrt(var) or 1.0


def main():
    papers = json.loads((ROOT / "data/papers.json").read_text())
    ov_path = ROOT / "data/core_overrides.json"
    ov = json.loads(ov_path.read_text()) if ov_path.exists() else {"pin": [], "exclude": [], "note": {}}
    pin, exclude = set(ov.get("pin", [])), set(ov.get("exclude", []))

    active = [p for p in papers if not p.get("superseded")]
    byid = {p["id"]: p for p in active}
    ids = set(byid)

    # ---- 信号：库内入度 + 综述共引 ----
    indeg = collections.Counter()
    svcite = collections.Counter()
    svset = {p["id"] for p in active if SURVEY_BRANCH in (p.get("branches") or [])}
    for p in active:
        is_sv = p["id"] in svset
        for r in (p.get("refs_in_library") or []):
            if r in ids:
                indeg[r] += 1
                if is_sv:
                    svcite[r] += 1

    # ---- 信号：桥梁 betweenness（无向库内图，k 采样）+ 邻居跨分支数 ----
    betw = collections.defaultdict(float)
    nbrbranch = collections.defaultdict(set)
    try:
        import networkx as nx
        G = nx.Graph()
        G.add_nodes_from(ids)
        for p in active:
            for r in (p.get("refs_in_library") or []):
                if r in ids:
                    G.add_edge(p["id"], r)
                    for b in (byid[r].get("branches") or []):
                        nbrbranch[p["id"]].add(b)
                    for b in (p.get("branches") or []):
                        nbrbranch[r].add(b)
        k = min(400, G.number_of_nodes())
        betw = nx.betweenness_centrality(G, k=k, seed=42, normalized=True)
    except Exception as e:  # networkx 缺失时降级：用邻居跨分支数当桥梁代理
        print(f"[warn] betweenness 降级（{e}）：改用邻居跨分支数代理")
        for p in active:
            for r in (p.get("refs_in_library") or []):
                if r in ids:
                    for b in (byid[r].get("branches") or []):
                        nbrbranch[p["id"]].add(b)
                    for b in (p.get("branches") or []):
                        nbrbranch[r].add(b)
        for i in ids:
            betw[i] = len(nbrbranch[i])

    # ---- 信号：同龄引用分位 ----
    cohort = collections.defaultdict(list)
    for p in active:
        cohort[p.get("year")].append(p.get("cited_by_count") or 0)
    for y in cohort:
        cohort[y].sort()
    def cohort_pct(p):
        arr = cohort[p.get("year")]
        if not arr:
            return 0.0
        c = p.get("cited_by_count") or 0
        import bisect
        return bisect.bisect_right(arr, c) / len(arr)

    # ---- 信号：watchlist 作者 ----
    wl = json.loads((ROOT / "data/watchlist.json").read_text())
    wlkeys = {lastfirst(w["name"]) for w in wl}
    wlname_by_key = {lastfirst(w["name"]): w["name"] for w in wl}
    def wl_hit(p):
        for a in p.get("authors", []):
            k = lastfirst(a.get("name", ""))
            if k in wlkeys:
                return wlname_by_key[k]
        return None

    # ---- 复合分（经典/权威主轴）----
    im, isd = zscores(indeg.values())
    sm, ssd = zscores(svcite.values())
    bm, bsd = zscores(betw.values())
    cm, csd = zscores([math.log1p(p.get("cited_by_count") or 0) for p in active])
    def composite(p):
        i = (indeg[p["id"]] - im) / isd
        s = (svcite[p["id"]] - sm) / ssd
        b = (betw[p["id"]] - bm) / bsd
        c = (math.log1p(p.get("cited_by_count") or 0) - cm) / csd
        return 2 * i + 2 * s + 1 * b + 0.5 * c

    def newscore(p):
        return (cohort_pct(p) + 0.5 * (p.get("journal") in TOP_JOURNALS)
                + 0.5 * (wl_hit(p) is not None) + 0.3 * min(svcite[p["id"]], 3)
                + 0.2 * math.log1p(indeg[p["id"]]))

    # ============ 择优（保证 ≤BUDGET 且配额）============
    core = {}          # id -> set(reason strings)
    def add(pid, reason):
        if pid in exclude:
            return
        core.setdefault(pid, set()).add(reason)

    # 1) 手动置顶
    for pid in pin:
        if pid in byid:
            add(pid, "手动置顶")

    # 2) 新锐 80 席
    recent = [p for p in active if (p.get("year") or 0) >= NEW_YEAR
              and p["id"] not in core and p["id"] not in exclude]
    recent.sort(key=newscore, reverse=True)
    for p in recent[:NEW_SEATS]:
        tags = []
        if p.get("journal") in TOP_JOURNALS:
            tags.append("顶刊新作")
        if cohort_pct(p) >= 0.9:
            tags.append(f"同龄前{round((1-cohort_pct(p))*100)}%")
        w = wl_hit(p)
        if w:
            tags.append("监视名单")
        add(p["id"], "新锐·" + "/".join(tags) if tags else "新锐·潜力新文")

    # 3) 分支保底
    for b in sorted({b for p in active for b in (p.get("branches") or [])}):
        members = [pid for pid in core if b in (byid[pid].get("branches") or [])]
        if len(members) >= BRANCH_FLOOR:
            continue
        pool = sorted([p for p in active if b in (p.get("branches") or [])
                       and p["id"] not in core and p["id"] not in exclude],
                      key=composite, reverse=True)
        for p in pool[:BRANCH_FLOOR - len(members)]:
            add(p["id"], f"分支支柱（{b}支）")

    # 4) 补满预算
    rest = sorted([p for p in active if p["id"] not in core and p["id"] not in exclude],
                  key=composite, reverse=True)
    for p in rest:
        if len(core) >= BUDGET:
            break
        add(p["id"], "领域权威")

    # 5) 追加可读理由（对所有入选者）+ ★镇树之宝
    for pid in core:
        p = byid[pid]
        if svcite[pid] >= 3:
            core[pid].add(f"★镇树之宝（{svcite[pid]}篇综述引用）")
        elif svcite[pid] >= 2:
            core[pid].add(f"综述必读（{svcite[pid]}篇综述引用）")
        if indeg[pid] >= 20:
            core[pid].add(f"领域权威（库内被引{indeg[pid]}次）")
        if len(nbrbranch[pid]) >= 4 and betw[pid] >= sorted(betw.values())[-100]:
            names = "·".join(sorted(nbrbranch[pid]))
            core[pid].add(f"跨支桥梁（连接{names}）")
        w = wl_hit(p)
        if w:
            core[pid].add(f"监视名单作者（{w}）")

    # 去掉"领域权威"占位（若已有更具体理由）
    for pid in core:
        if len(core[pid]) > 1:
            core[pid].discard("领域权威")

    # ---- 排名（按复合分）----
    ranked = sorted(core, key=lambda i: composite(byid[i]), reverse=True)
    rank = {pid: r + 1 for r, pid in enumerate(ranked)}

    # ---- 回写 papers.json ----
    STAR = "★镇树之宝"
    for p in papers:
        pid = p["id"]
        if pid in core:
            reasons = sorted(core[pid], key=lambda s: (not s.startswith("★"), s))
            p["core"] = True
            p["core_rank"] = rank[pid]
            p["core_reasons"] = reasons
            p["core_new"] = any(r.startswith("新锐") for r in reasons)
            p["core_star"] = any(r.startswith("★") for r in reasons)
            p["core_score"] = round(composite(byid[pid]), 3)
        else:
            for f in ("core", "core_rank", "core_reasons", "core_new", "core_star", "core_score"):
                p.pop(f, None)
    (ROOT / "data/papers.json").write_text(json.dumps(papers, ensure_ascii=False, indent=1))

    # ---- 快照 + diff ----
    hist_dir = ROOT / "data/core_history"
    hist_dir.mkdir(exist_ok=True)
    today = date.today().isoformat()
    snap = {pid: sorted(core[pid]) for pid in core}
    prev_files = sorted(hist_dir.glob("*.json"))
    prev = json.loads(prev_files[-1].read_text()) if prev_files else {}
    added = set(snap) - set(prev)
    dropped = set(prev) - set(snap)
    (hist_dir / f"{today}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1))

    # ---- 报告 ----
    bt = collections.Counter()
    for pid in core:
        for b in (byid[pid].get("branches") or []):
            bt[b] += 1
    n_new = sum(1 for pid in core if any(r.startswith("新锐") for r in core[pid]))
    n_star = sum(1 for pid in core if any(r.startswith("★") for r in core[pid]))
    print(f"核心层：{len(core)} 篇（预算 {BUDGET}）｜新锐席 {n_new} ｜★镇树之宝 {n_star}")
    print("分支分布：", {b: bt[b] for b in sorted(bt)})
    floor_bad = [b for b in sorted(bt) if bt[b] < BRANCH_FLOOR]
    print("保底未达标分支：", floor_bad or "无（全部≥%d）" % BRANCH_FLOOR)
    if prev:
        print(f"较上次快照：新进 {len(added)}，掉出 {len(dropped)}")
    return core, byid, rank, composite


if __name__ == "__main__":
    main()
