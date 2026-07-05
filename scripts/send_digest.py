"""每周 digest 邮件（163 SMTP）。环境变量：MAIL_USER / MAIL_PASS(授权码) / MAIL_TO(逗号分隔)。
无新增或缺配置时静默跳过（exit 0），不让 workflow 失败。"""
import json, os, smtplib, sys
from email.header import Header
from email.mime.text import MIMEText
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

user, pwd, to = os.getenv("MAIL_USER"), os.getenv("MAIL_PASS"), os.getenv("MAIL_TO")
if not (user and pwd and to):
    print("邮件未配置，跳过"); sys.exit(0)

updates = sorted((ROOT / "data/updates").glob("*.json"))
if not updates:
    print("无更新记录，跳过"); sys.exit(0)
latest = json.loads(updates[-1].read_text())
if not latest.get("new_ids"):
    print("本周无新增，跳过"); sys.exit(0)

papers = {p["id"]: p for p in json.loads((ROOT / "data/papers.json").read_text())}
BRANCHES = {b["code"]: b["name"] for b in json.loads((ROOT / "data/branches.json").read_text())}

rows = []
for pid in latest["new_ids"]:
    p = papers.get(pid)
    if not p:
        continue
    link = f'https://doi.org/{p["doi"]}' if p.get("doi") else f'https://openalex.org/{pid}'
    br = "、".join(BRANCHES.get(c, c) for c in p.get("branches", [])) or "待归类"
    au = "; ".join(a["name"] for a in p.get("authors", [])[:4])
    rows.append(f'<tr><td><a href="{link}">{p["title_en"]}</a></td>'
                f'<td>{au}</td><td>{p.get("journal","")}</td><td>{br}</td></tr>')

html = (f'<p>本周新增 <b>{latest["new_count"]}</b> 篇（自 {latest["since"]}）。'
        f'完整可视化：<a href="https://sandysun6.github.io/innovation-lit-tree/">文献树网页</a></p>'
        f'<table border="1" cellpadding="6" style="border-collapse:collapse;font-size:14px">'
        f'<tr><th>题目</th><th>作者</th><th>来源</th><th>分支</th></tr>{"".join(rows)}</table>')

msg = MIMEText(html, "html", "utf-8")
msg["Subject"] = Header(f'创新文献周报 {latest["date"]} · 新增 {latest["new_count"]} 篇', "utf-8")
msg["From"] = user
msg["To"] = to
with smtplib.SMTP_SSL("smtp.163.com", 465, timeout=60) as s:
    s.login(user, pwd)
    s.sendmail(user, [t.strip() for t in to.split(",")], msg.as_string())
print("digest 已发送")
