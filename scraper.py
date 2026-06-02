import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from config import BASE_URL, LIST_URL, HEADERS, SITE_NAME

# Playwright 浏览器复用
_pw_browser = None


def get_browser():
    """获取或创建复用的 Playwright 浏览器"""
    global _pw_browser
    if _pw_browser is None:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        _pw_browser = pw.chromium.launch(headless=True)
    return _pw_browser


def close_browser():
    """关闭复用的浏览器"""
    global _pw_browser
    if _pw_browser:
        _pw_browser.close()
        _pw_browser = None


def get_page(url):
    """获取页面内容"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.encoding = "utf-8"
        return resp.text
    except Exception as e:
        return None


def parse_list_page(html):
    """解析列表页"""
    soup = BeautifulSoup(html, "lxml")
    items = []
    for li in soup.select("div.zp-newsmain ul li"):
        a = li.select_one("a.blue-light")
        span = li.select_one("span.floatright")
        if a and span:
            title = a.get_text(strip=True)
            href = a.get("href", "")
            date = span.get_text(strip=True)
            if "mp.weixin.qq.com" in href:
                link_type = "wechat"
            elif "job.mohrss.gov.cn" in href:
                link_type = "internal"
            else:
                link_type = "other"
            items.append({
                "title": title, "date": date,
                "source_url": href, "link_type": link_type,
                "source_site": SITE_NAME,
            })
    return items


def get_total_pages(html):
    soup = BeautifulSoup(html, "lxml")
    max_page = 1
    for a in soup.select("div.pages a"):
        text = a.get_text(strip=True)
        if text.isdigit():
            max_page = max(max_page, int(text))
    return max_page


def scrape_list():
    """爬取所有列表页"""
    print("[1/3] 爬取列表页...")
    all_items = []
    html = get_page(LIST_URL)
    if not html:
        return all_items
    all_items.extend(parse_list_page(html))
    total_pages = get_total_pages(html)
    print(f"  {total_pages} 页, 第1页 {len(all_items)} 条")

    # 并发爬取剩余页
    if total_pages > 1:
        page_urls = {p: f"{BASE_URL}/index_{p}.jhtml" for p in range(2, total_pages + 1)}
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(get_page, u): p for p, u in page_urls.items()}
            for f in as_completed(futures):
                p = futures[f]
                html = f.result()
                if html:
                    items = parse_list_page(html)
                    all_items.extend(items)
                    print(f"  第{p}页 {len(items)} 条")

    print(f"  共 {len(all_items)} 条")
    return all_items


def scrape_internal_detail(url):
    full_url = urljoin(BASE_URL + "/", url)
    html = get_page(full_url)
    if not html:
        return {"content": "", "images": [], "links": []}
    soup = BeautifulSoup(html, "lxml")
    news_c = soup.select_one("div.news_c")
    content = news_c.get_text(separator="\n", strip=True) if news_c else ""
    images = []
    links = []
    if news_c:
        for img in news_c.select("img"):
            src = img.get("src", "")
            if src:
                images.append(urljoin(full_url, src))
        for a in news_c.select("a[href]"):
            href = a.get("href", "").strip()
            if href and href.startswith("http"):
                links.append(href)
    return {"content": content, "images": images, "links": links}


def scrape_wechat_detail(url):
    """用复用的浏览器爬取微信文章"""
    try:
        browser = get_browser()
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": HEADERS["User-Agent"]})
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        try:
            page.wait_for_selector("#js_content", timeout=8000)
        except:
            pass
        html_content = page.content()
        page.close()

        soup = BeautifulSoup(html_content, "lxml")
        js_content = soup.select_one("#js_content")
        content = js_content.get_text(separator="\n", strip=True) if js_content else ""
        images = []
        links = []
        if js_content:
            for img in js_content.select("img"):
                src = img.get("data-src") or img.get("src", "")
                if src and not src.startswith("data:"):
                    images.append(src)
            for a in js_content.select("a[href]"):
                href = a.get("href", "").strip()
                if href and href.startswith("http"):
                    links.append(href)
        return {"content": content, "images": images, "links": links}
    except Exception as e:
        return {"content": "", "images": []}


def scrape_detail(item):
    url = item["source_url"]
    link_type = item["link_type"]
    if link_type == "internal":
        return scrape_internal_detail(url)
    elif link_type == "wechat":
        return scrape_wechat_detail(url)
    return {"content": "", "images": [], "links": []}


def scrape_all():
    """完整爬取流程 - 并发优化"""
    items = scrape_list()
    if not items:
        print("[错误] 未获取到任何招聘信息")
        return []

    print(f"\n[2/3] 爬取详情页（{len(items)} 条）...")
    start = time.time()

    # 先分类：内部页可并发，微信页用复用浏览器顺序处理
    internal = [(i, item) for i, item in enumerate(items) if item["link_type"] == "internal"]
    wechat = [(i, item) for i, item in enumerate(items) if item["link_type"] == "wechat"]
    other = [(i, item) for i, item in enumerate(items) if item["link_type"] == "other"]

    # 并发爬取内部详情页
    if internal:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(scrape_detail, item): idx for idx, item in internal}
            for f in as_completed(futures):
                idx = futures[f]
                detail = f.result()
                items[idx]["content"] = detail["content"]
                items[idx]["images"] = detail["images"]
                items[idx]["html_links"] = detail.get("links", [])
                print(f"  [{idx+1}] {items[idx]['title'][:25]}... (内部)")

    # 微信文章用复用浏览器（避免反复启动）
    for idx, item in wechat:
        detail = scrape_detail(item)
        items[idx]["content"] = detail["content"]
        items[idx]["images"] = detail["images"]
        items[idx]["html_links"] = detail.get("links", [])
        print(f"  [{idx+1}] {item['title'][:25]}... (微信)")

    close_browser()

    for idx, item in other:
        items[idx]["content"] = ""
        items[idx]["images"] = []
        items[idx]["html_links"] = []

    elapsed = time.time() - start
    print(f"  完成! 耗时 {elapsed:.1f}s")
    return items
