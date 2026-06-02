import json
import os
from datetime import datetime
from scraper import scrape_all
from ai_analyzer import process_all
from config import OUTPUT_DIR


def generate_html(jobs, output_path):
    """生成卡片式招聘页面 - PC多列/手机单列 + 网站筛选"""
    # 收集所有来源网站
    sites = sorted(set(j.get("source_site", "未知") for j in jobs))
    site_counts = {}
    for j in jobs:
        s = j.get("source_site", "未知")
        site_counts[s] = site_counts.get(s, 0) + 1

    site_btns = f'<button class="site-btn active" onclick="filterSite(\'all\')">全部 ({len(jobs)})</button>'
    for site in sites:
        site_btns += f'<button class="site-btn" onclick="filterSite(\'{site}\')">{site} ({site_counts[site]})</button>'

    cards = ""
    for i, job in enumerate(jobs):
        ext = job.get("extracted", {})
        title = job.get("title", "")
        date = job.get("date", "")
        url = job.get("source_url", "")
        source_site = job.get("source_site", "未知")

        # 核心字段
        apply_link = ext.get("links", [""])[0] if ext.get("links") else ""
        target = ext.get("target", "")
        location = ext.get("location", "")
        majors = ext.get("majors", "")
        deadline = ext.get("deadline", "")
        positions = ext.get("positions", "")
        apply_method = ext.get("apply_method", "")
        emails = ext.get("emails", [])
        contact = ext.get("contact", "")

        # 核心信息行
        info_rows = ""
        for label, val in [("招聘对象", target), ("招聘专业", majors), ("工作地点", location), ("截止时间", deadline)]:
            if val:
                info_rows += f'<div class="m-row"><span class="m-rl">{label}</span><span class="m-rv">{val}</span></div>'

        # 岗位信息
        pos_html = ""
        if positions:
            safe_pos = positions.replace("<", "&lt;").replace(">", "&gt;")
            pos_html = f'<div class="m-block"><span class="m-bl">岗位信息</span>{safe_pos}</div>'

        # 投递方式
        apply_html = ""
        if apply_method:
            safe_apply = apply_method.replace("<", "&lt;").replace(">", "&gt;")[:200]
            apply_html = f'<div class="m-block"><span class="m-bl">投递方式</span>{safe_apply}</div>'

        # 联系方式
        contact_html = ""
        if contact or emails:
            contact_val = contact or ", ".join(emails[:2])
            contact_html = f'<div class="m-row"><span class="m-rl">联系方式</span><span class="m-rv">{contact_val}</span></div>'

        # 搜索
        search_text = f"{title} {source_site} {target} {location} {majors} {positions}"

        m_apply = ""
        if apply_link:
            m_apply = f'<a href="{apply_link}" target="_blank" class="m-btn">立即投递</a>'

        cards += f'''
    <div class="m-card" data-search="{search_text}" data-site="{source_site}">
      <div class="m-card-head">
        <span class="m-date">{date}</span>
        <span class="m-site">{source_site}</span>
      </div>
      <a class="m-card-title" href="{url}" target="_blank">{title}</a>
      {f'<div class="m-info-rows">{info_rows}</div>' if info_rows else ''}
      {pos_html}
      {apply_html}
      {contact_html}
      <div class="m-card-foot">
        {m_apply}
        <a href="{url}" target="_blank" class="m-link">查看原文</a>
      </div>
    </div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>招聘信息总览</title>
<style>
:root {{
  --bg: #f5f5f7; --surface: #fff; --surface2: #f9f9fb; --surface3: #e8e8ed;
  --text: #1d1d1f; --text2: #6e6e73; --text3: #aeaeb2;
  --blue: #0071e3; --green: #34c759; --orange: #ff9500;
  --border: rgba(0,0,0,.08); --hover: rgba(0,0,0,.03);
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "SF Pro Display", "Helvetica Neue", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--text); -webkit-font-smoothing: antialiased; }}

/* Top Bar */
.topbar {{ position: sticky; top: 0; z-index: 100; background: rgba(255,255,255,.85); backdrop-filter: saturate(180%) blur(20px); border-bottom: 0.5px solid var(--border); padding: 0 32px; height: 52px; display: flex; align-items: center; gap: 20px; }}
.logo {{ font-size: 15px; font-weight: 600; white-space: nowrap; }}
.logo span {{ color: var(--blue); }}
.search-wrap {{ flex: 1; max-width: 360px; position: relative; }}
.search-wrap svg {{ position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text3); }}
.search-wrap input {{ width: 100%; height: 34px; padding: 0 12px 0 36px; background: var(--surface3); border: none; border-radius: 8px; color: var(--text); font-size: 13px; outline: none; }}
.search-wrap input:focus {{ background: #fff; box-shadow: 0 0 0 2px var(--blue); }}
.stats-bar {{ display: flex; gap: 14px; font-size: 12px; color: var(--text2); }}
.stat {{ display: flex; align-items: center; gap: 4px; }}
.dot {{ width: 6px; height: 6px; border-radius: 50%; }}

/* Filter Bar */
.filter-bar {{ padding: 14px 32px 0; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }}
.filter-label {{ font-size: 11px; color: var(--text3); margin-right: 2px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }}
.site-btn {{ padding: 5px 12px; border: none; border-radius: 6px; background: var(--surface2); color: var(--text2); font-size: 12px; font-weight: 500; cursor: pointer; transition: all .15s; font-family: inherit; }}
.site-btn:hover {{ background: var(--surface3); color: var(--text); }}
.site-btn.active {{ background: var(--text); color: #fff; }}

/* Cards Grid */
.cards-wrap {{ padding: 16px 32px 60px; }}
.cards-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }}
.cards-header h2 {{ font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }}
.show-count {{ font-size: 13px; color: var(--text2); }}
.cards-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; }}

/* Card */
.m-card {{ background: var(--surface); border-radius: 12px; padding: 16px 18px; border: 0.5px solid var(--border); display: flex; flex-direction: column; transition: box-shadow .2s, transform .15s; }}
.m-card:hover {{ box-shadow: 0 6px 24px rgba(0,0,0,.06); transform: translateY(-2px); }}
.m-card-head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }}
.m-date {{ font-size: 11px; color: var(--text3); font-variant-numeric: tabular-nums; }}
.m-site {{ font-size: 10px; color: var(--blue); background: rgba(0,113,227,.08); padding: 1px 6px; border-radius: 4px; font-weight: 500; }}
.m-company {{ font-size: 12px; color: var(--blue); font-weight: 600; }}
.m-card-title {{ font-size: 15px; font-weight: 600; line-height: 1.4; margin-bottom: 8px; color: var(--text); text-decoration: none; display: block; }}
.m-card-title:hover {{ color: var(--blue); }}
.m-pos {{ font-size: 12px; color: var(--green); font-weight: 500; margin-bottom: 8px; line-height: 1.5; }}

/* 核心信息行 */
.m-info-rows {{ margin-bottom: 8px; }}
.m-row {{ display: flex; gap: 6px; font-size: 12px; line-height: 1.6; padding: 3px 0; border-bottom: 0.5px solid var(--border); }}
.m-row:last-child {{ border-bottom: none; }}
.m-rl {{ color: var(--text3); flex-shrink: 0; min-width: 56px; }}
.m-rv {{ color: var(--text); word-break: break-all; }}

/* 信息块 */
.m-block {{ font-size: 12px; color: var(--text2); line-height: 1.6; background: var(--surface2); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; white-space: pre-line; word-break: break-all; }}
.m-block .m-bl {{ display: block; font-size: 11px; color: var(--text3); font-weight: 600; margin-bottom: 2px; }}
.m-card-foot {{ display: flex; align-items: center; justify-content: space-between; padding-top: 10px; border-top: 0.5px solid var(--border); margin-top: auto; }}
.m-btn {{ display: inline-flex; align-items: center; padding: 6px 14px; background: var(--blue); color: #fff; border-radius: 6px; text-decoration: none; font-size: 12px; font-weight: 600; }}
.m-btn:hover {{ opacity: .85; }}
.m-method {{ font-size: 11px; color: var(--orange); }}
.m-link {{ font-size: 12px; color: var(--text3); text-decoration: none; }}
.m-link:hover {{ color: var(--text2); }}
.hidden {{ display: none !important; }}

/* Mobile */
@media (max-width: 768px) {{
  .topbar {{ padding: 0 14px; height: 48px; gap: 10px; }}
  .logo {{ font-size: 14px; }}
  .search-wrap {{ max-width: none; }}
  .search-wrap input {{ height: 32px; }}
  .stats-bar {{ display: none; }}
  .filter-bar {{ padding: 10px 14px 0; gap: 5px; }}
  .site-btn {{ padding: 4px 10px; font-size: 11px; }}
  .cards-wrap {{ padding: 10px 14px 30px; }}
  .cards-grid {{ grid-template-columns: 1fr; gap: 10px; }}
  .m-card {{ padding: 14px 14px; }}
  .m-card-title {{ font-size: 14px; }}
  .m-summary {{ font-size: 12px; }}
}}
@media (max-width: 480px) {{
  .filter-bar {{ padding: 10px 10px 0; }}
  .cards-wrap {{ padding: 8px 10px 20px; }}
}}
</style>
</head>
<body>
<div class="topbar">
  <div class="logo"><span>&#9670;</span> 招聘总览</div>
  <div class="search-wrap">
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
    <input type="text" id="search" placeholder="搜索公司、岗位..." oninput="doFilter()">
  </div>
  <div class="stats-bar">
    <div class="stat"><span class="dot" style="background:var(--blue)"></span><span id="s-total">{len(jobs)} 条</span></div>
    <div class="stat"><span class="dot" style="background:var(--green)"></span><span id="s-link">{sum(1 for j in jobs if j.get("extracted", {}).get("links"))} 有链接</span></div>
    <div class="stat"><span class="dot" style="background:var(--orange)"></span><span>{sum(1 for j in jobs if j.get("extracted", {}).get("dates"))} 有日期</span></div>
    <div class="stat"><span class="dot" style="background:#af52de"></span><span>{len(sites)} 个来源</span></div>
  </div>
</div>
<div class="filter-bar">
  <span class="filter-label">来源:</span>
  {site_btns}
</div>
<div class="cards-wrap">
  <div class="cards-header">
    <h2>招聘信息</h2>
    <span class="show-count" id="show-count">显示 {len(jobs)}/{len(jobs)}</span>
  </div>
  <div class="cards-grid" id="grid">
{cards}
  </div>
</div>
<script>
let curSite = "all";
function filterSite(site) {{
  curSite = site;
  document.querySelectorAll(".site-btn").forEach(b => {{
    b.classList.toggle("active", (site === "all" && b.textContent.startsWith("全部")) || b.textContent.startsWith(site));
  }});
  doFilter();
}}
function doFilter() {{
  const q = document.getElementById("search").value.toLowerCase();
  const cards = document.querySelectorAll(".m-card");
  let n = 0;
  cards.forEach(c => {{
    const matchSite = curSite === "all" || c.dataset.site === curSite;
    const matchSearch = !q || c.dataset.search.toLowerCase().includes(q);
    const show = matchSite && matchSearch;
    c.classList.toggle("hidden", !show);
    if (show) n++;
  }});
  document.getElementById("show-count").textContent = `显示 ${{n}}/{len(jobs)}`;
}}
</script>
</body>
</html>'''
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>央企招聘信息总览</title>
<style>
:root {{
  --bg: #f5f5f7; --surface: #ffffff; --surface2: #f9f9fb; --surface3: #e8e8ed;
  --text: #1d1d1f; --text2: #6e6e73; --text3: #aeaeb2;
  --blue: #0071e3; --green: #34c759; --orange: #ff9500; --red: #ff3b30;
  --border: rgba(0,0,0,.08); --hover: rgba(0,0,0,.03);
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "SF Pro Display", "SF Pro Text", "Helvetica Neue", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--text); -webkit-font-smoothing: antialiased; }}

/* Top Bar */
.topbar {{ position: sticky; top: 0; z-index: 100; background: rgba(255,255,255,.8); backdrop-filter: saturate(180%) blur(20px); -webkit-backdrop-filter: saturate(180%) blur(20px); border-bottom: 0.5px solid var(--border); padding: 0 32px; height: 52px; display: flex; align-items: center; gap: 20px; }}
.logo {{ font-size: 15px; font-weight: 600; letter-spacing: -0.3px; white-space: nowrap; color: var(--text); }}
.logo span {{ color: var(--blue); }}
.search-wrap {{ flex: 1; max-width: 420px; position: relative; }}
.search-wrap svg {{ position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--text3); }}
.search-wrap input {{ width: 100%; height: 34px; padding: 0 12px 0 36px; background: var(--surface3); border: none; border-radius: 8px; color: var(--text); font-size: 13px; outline: none; transition: background .2s, box-shadow .2s; }}
.search-wrap input:focus {{ background: #fff; box-shadow: 0 0 0 2px var(--blue); }}
.search-wrap input::placeholder {{ color: var(--text3); }}
.stats-bar {{ display: flex; gap: 16px; font-size: 12px; color: var(--text2); }}
.stat {{ display: flex; align-items: center; gap: 4px; }}
.stat-dot {{ width: 6px; height: 6px; border-radius: 50%; }}
.stat-dot.blue {{ background: var(--blue); }}
.stat-dot.green {{ background: var(--green); }}
.stat-dot.orange {{ background: var(--orange); }}

.hidden {{ display: none !important; }}

/* ========= Cards Layout (all screen sizes) ========= */
.table-wrap {{ display: none !important; }}
.m-cards {{ display: block; padding: 0 32px 60px; }}

/* Desktop grid */
@media (min-width: 1200px) {{
  .m-cards {{ padding: 0 48px 60px; }}
  .topbar {{ padding: 0 48px; }}
  .m-cards-inner {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }}
}}
@media (min-width: 1600px) {{
  .m-cards-inner {{ grid-template-columns: repeat(3, 1fr); }}
}}

/* Tablet */
@media (max-width: 1024px) {{
  .topbar {{ padding: 0 20px; }}
  .m-cards {{ padding: 0 20px 40px; }}
}}

/* Mobile */
@media (max-width: 768px) {{
  .m-cards {{ padding: 0 14px 30px; }}
  .m-cards-inner {{ display: flex; flex-direction: column; gap: 10px; }}
  .topbar {{ padding: 0 14px; height: 48px; gap: 10px; }}
  .logo {{ font-size: 14px; }}
  .search-wrap {{ max-width: none; }}
  .search-wrap input {{ height: 32px; font-size: 13px; }}
  .stats-bar {{ gap: 10px; font-size: 11px; }}
}}

/* Card base */
.m-card {{ background: var(--surface); border-radius: 12px; padding: 16px 18px; border: 0.5px solid var(--border); transition: box-shadow .2s, transform .15s; cursor: default; display: flex; flex-direction: column; gap: 0; }}
.m-card:hover {{ box-shadow: 0 4px 20px rgba(0,0,0,.06); transform: translateY(-1px); }}
.m-card-head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.m-date {{ font-size: 11px; color: var(--text3); font-variant-numeric: tabular-nums; }}
.m-company {{ font-size: 12px; color: var(--blue); font-weight: 600; }}
.m-card-title {{ font-size: 15px; font-weight: 600; line-height: 1.4; margin-bottom: 8px; color: var(--text); }}
.m-card-title a {{ color: inherit; text-decoration: none; }}
.m-card-title a:hover {{ color: var(--blue); }}
.m-pos {{ font-size: 12px; color: var(--green); font-weight: 500; margin-bottom: 8px; line-height: 1.5; }}
.m-info {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }}
.m-tag {{ display: inline-flex; align-items: center; gap: 4px; background: var(--surface2); border: 0.5px solid var(--border); border-radius: 6px; padding: 4px 8px; font-size: 11px; color: var(--text); line-height: 1.4; }}
.m-tag-label {{ color: var(--text3); }}
.m-summary {{ font-size: 13px; color: var(--text2); line-height: 1.6; margin-bottom: 10px; }}
.m-card-foot {{ display: flex; align-items: center; justify-content: space-between; padding-top: 10px; border-top: 0.5px solid var(--border); margin-top: auto; }}
.m-btn {{ display: inline-flex; align-items: center; padding: 7px 16px; background: var(--blue); color: #fff; border-radius: 8px; text-decoration: none; font-size: 13px; font-weight: 600; transition: opacity .15s; }}
.m-btn:hover {{ opacity: .85; }}
.m-method {{ font-size: 11px; color: var(--orange); line-height: 1.4; }}
.m-link {{ font-size: 12px; color: var(--text3); text-decoration: none; transition: color .15s; }}
.m-link:hover {{ color: var(--text2); }}
}}
</style>
</head>
<body>
<div class="topbar">
  <div class="logo"><span>&#9670;</span> 招聘总览</div>
  <div class="search-wrap">
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
    <input type="text" id="search" placeholder="搜索公司、岗位..." oninput="doFilter()">
  </div>
  <div class="stats-bar">
    <div class="stat"><span class="dot" style="background:var(--blue)"></span><span id="s-total">{len(jobs)} 条</span></div>
    <div class="stat"><span class="dot" style="background:var(--green)"></span><span id="s-link">{sum(1 for j in jobs if j.get("extracted", {}).get("links"))} 有链接</span></div>
    <div class="stat"><span class="dot" style="background:var(--orange)"></span><span>{sum(1 for j in jobs if j.get("extracted", {}).get("dates"))} 有日期</span></div>
    <div class="stat"><span class="dot" style="background:#af52de"></span><span>{len(sites)} 个来源</span></div>
  </div>
</div>
<div class="filter-bar">
  <span class="filter-label">来源:</span>
  {site_btns}
</div>
<div class="cards-wrap">
  <div class="cards-header">
    <h2>招聘信息</h2>
    <span class="show-count" id="show-count">显示 {len(jobs)}/{len(jobs)}</span>
  </div>
  <div class="cards-grid" id="grid">
{cards}
  </div>
</div>
<script>
let curSite = "all";
function filterSite(site) {{
  curSite = site;
  document.querySelectorAll(".site-btn").forEach(b => {{
    b.classList.toggle("active", (site === "all" && b.textContent.startsWith("全部")) || b.textContent.startsWith(site));
  }});
  doFilter();
}}
function doFilter() {{
  const q = document.getElementById("search").value.toLowerCase();
  const cards = document.querySelectorAll(".m-card");
  let n = 0;
  cards.forEach(c => {{
    const matchSite = curSite === "all" || c.dataset.site === curSite;
    const matchSearch = !q || c.dataset.search.toLowerCase().includes(q);
    const show = matchSite && matchSearch;
    c.classList.toggle("hidden", !show);
    if (show) n++;
  }});
  document.getElementById("show-count").textContent = `显示 ${{n}}/{len(jobs)}`;
}}
</script>
</body>
</html>'''
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    print("=" * 50)
    print("  央企招聘信息爬虫")
    print("  目标: http://job.mohrss.gov.cn/qyzp/index.jhtml")
    print("=" * 50)

    # 1. 爬取
    jobs = scrape_all()
    if not jobs:
        print("\n爬取失败，无数据")
        return

    # 2. 数据提取（纯 OCR + 正则，无 AI）
    jobs = process_all(jobs)

    # 3. 输出
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    output_file = os.path.join(OUTPUT_DIR, f"jobs_{today}.json")

    result = {
        "scrape_time": datetime.now().isoformat(),
        "source": "http://job.mohrss.gov.cn/qyzp/index.jhtml",
        "total": len(jobs),
        "jobs": jobs,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 生成 HTML 页面
    html_file = os.path.join(OUTPUT_DIR, f"jobs_{today}.html")
    generate_html(jobs, html_file)

    print(f"\n{'=' * 50}")
    print(f"  完成！共 {len(jobs)} 条招聘信息")
    print(f"  JSON: {output_file}")
    print(f"  HTML: {html_file}")
    print(f"{'=' * 50}")

    # 打印摘要
    print("\n[摘要] 招聘信息摘要:")
    print("-" * 50)
    for i, job in enumerate(jobs):
        summary = ""
        if job.get("ai_summary") and job["ai_summary"].get("summary"):
            summary = job["ai_summary"]["summary"]
        apply_info = ""
        if job.get("ai_summary"):
            if job["ai_summary"].get("apply_link"):
                apply_info = f" | 投递: {job['ai_summary']['apply_link']}"
            elif job["ai_summary"].get("apply_method"):
                apply_info = f" | {job['ai_summary']['apply_method']}"
        title = job['title'].encode('gbk', errors='replace').decode('gbk')
        print(f"  {i+1}. [{job['date']}] {title}")
        if summary:
            safe = summary.encode('gbk', errors='replace').decode('gbk')
            safe2 = apply_info.encode('gbk', errors='replace').decode('gbk')
            print(f"     {safe}{safe2}")
    print("-" * 50)


if __name__ == "__main__":
    main()
