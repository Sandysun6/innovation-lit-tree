# 创新经济学文献树 innovation-lit-tree

每周自动追踪创新经济学新论文（NBER WP + 18 本 top/field 期刊），树状可视化 + 全量检索。

**🌐 网页：https://sandysun6.github.io/innovation-lit-tree/**

## 结构

- `data/papers.json` — 主数据（唯一真相源，schema 见主项目 `04_数据schema与分支v3.md`）
- `data/branches.json` / `tags.json` / `watchlist.json` — 15 分支、主题标签、学者监视清单
- `data/updates/` — 每周增量记录
- `scripts/` — 抓取（`fetch_weekly.py`）、分类（`classify.py`，v3 权威版）、站点构建、邮件摘要
- `.github/workflows/weekly.yml` — 每周一 09:00（北京）自动：抓取→分类→构建→commit→邮件
- `docs/` — GitHub Pages 站点（单文件应用 + 生成的数据）

## 邮件摘要（可选）

仓库 Settings → Secrets and variables → Actions 添加：`MAIL_USER`（163 邮箱）、`MAIL_PASS`（授权码）、`MAIL_TO`（收件人，逗号分隔）。缺省则跳过邮件，不影响其他步骤。

## 本地手动运行

```bash
pip install requests
python scripts/fetch_weekly.py     # 抓增量
python scripts/build_site_data.py  # 重建站点数据
```

## 阅读标记说明

网页上的「要精读/扫过/存档」标记只存在**你自己浏览器的 localStorage**，不上传、访客不可见；表格页有「导出标记」按钮可做本地备份。
