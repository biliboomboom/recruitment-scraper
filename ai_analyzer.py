import re
import base64
import json
import requests
from config import HEADERS

# Docker OCR 服务地址
OCR_API_URL = "http://localhost:8899/ocr"


def ocr_image(image_url):
    """通过 Docker PaddleOCR 3.x 服务识别图片文字"""
    try:
        # 下载图片
        resp = requests.get(image_url, timeout=15, headers={
            "User-Agent": HEADERS["User-Agent"],
            "Referer": "https://mp.weixin.qq.com/"
        })
        resp.raise_for_status()
        b64 = base64.b64encode(resp.content).decode()

        # 调用 Docker OCR 服务
        result = requests.post(OCR_API_URL, json={"image": b64}, timeout=30)
        data = result.json()

        if data.get("count", 0) > 0:
            return "\n".join(data["texts"])
        return ""
    except Exception as e:
        # Docker 服务不可用时，回退到无 OCR 模式
        return ""


def ocr_quality_check(ocr_text):
    """检查 OCR 文字质量，判断是否需要 AI 兜底"""
    if not ocr_text or len(ocr_text.strip()) < 10:
        return False
    # 计算有效字符比例（字母/数字/中文）
    valid = sum(1 for c in ocr_text if c.isalnum() or '一' <= c <= '鿿')
    ratio = valid / max(len(ocr_text), 1)
    return ratio > 0.3  # 有效字符超过 30% 认为质量可接受


def ai_vision_extract(image_url):
    """用多模态 AI 从图片中提取招聘信息（OCR 失败时的兜底）"""
    from config import AI_VISION_API_KEY, AI_VISION_BASE_URL, AI_VISION_MODEL
    if not AI_VISION_API_KEY:
        return ""

    try:
        # 下载图片转 base64
        resp = requests.get(image_url, timeout=15, headers={
            "User-Agent": HEADERS["User-Agent"],
            "Referer": "https://mp.weixin.qq.com/"
        })
        resp.raise_for_status()
        b64 = base64.b64encode(resp.content).decode()

        # 检测图片类型
        content_type = resp.headers.get("content-type", "image/jpeg")
        if "png" in content_type:
            mime = "image/png"
        elif "gif" in content_type:
            mime = "image/gif"
        else:
            mime = "image/jpeg"

        # 调用视觉 API（OpenAI 兼容格式）
        prompt = """请从这张招聘图片中提取以下信息。只提取图片中明确可见的文字，不要猜测或补充。

如果有某个信息，输出完整内容；如果没有，输出 null。

请严格按以下 JSON 格式输出，不要输出其他内容：
{
  "links": ["投递链接或招聘平台URL，只输出完整的https链接"],
  "location": "工作地点",
  "majors": "招聘专业/学历要求",
  "target": "招聘对象（如：2026届应届毕业生）",
  "positions": "招聘岗位名称",
  "deadline": "截止时间",
  "apply_method": "报名/投递方式说明",
  "emails": ["联系邮箱"],
  "contact": "联系电话或联系人",
  "raw_text": "图片中所有可见文字的完整摘录（前500字）"
}"""

        payload = {
            "model": AI_VISION_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{b64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000,
            "temperature": 0.1
        }

        result = requests.post(
            f"{AI_VISION_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {AI_VISION_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )
        data = result.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # 尝试解析 JSON
        # 兼容 AI 可能输出 markdown 代码块的情况
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        parsed = json.loads(content)

        # 组装成文本返回（复用现有正则提取逻辑）
        parts = []
        if parsed.get("raw_text"):
            parts.append(parsed["raw_text"])
        if parsed.get("links"):
            parts.extend(parsed["links"])
        if parsed.get("location"):
            parts.append(f"工作地点：{parsed['location']}")
        if parsed.get("majors"):
            parts.append(f"招聘专业：{parsed['majors']}")
        if parsed.get("target"):
            parts.append(f"招聘对象：{parsed['target']}")
        if parsed.get("positions"):
            parts.append(f"招聘岗位：{parsed['positions']}")
        if parsed.get("deadline"):
            parts.append(f"截止时间：{parsed['deadline']}")
        if parsed.get("apply_method"):
            parts.append(f"投递方式：{parsed['apply_method']}")
        if parsed.get("emails"):
            parts.extend(parsed["emails"])
        if parsed.get("contact"):
            parts.append(f"联系方式：{parsed['contact']}")

        return "\n".join(parts) if parts else ""

    except Exception as e:
        return ""


def extract_links(text):
    """从文本中提取所有 URL（智能合并 OCR 断行）"""
    if not text:
        return []
    lines = text.split("\n")
    urls = []

    for i, line in enumerate(lines):
        # 匹配当前行中的 URL
        pattern = r'https?://[^\s<>"\')\]，。、；]+'
        for u in re.findall(pattern, line):
            u = u.rstrip(".,;。、；")
            # 检查下一行是否是 URL 的延续（路径部分）
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # 下一行不以 http 开头，且看起来像路径/参数
                if (next_line and
                    not next_line.startswith("http") and
                    not next_line.startswith("www") and
                    re.match(r'^[a-zA-Z0-9_/?.=&%-]+$', next_line) and
                    len(next_line) > 3):
                    u = u.rstrip("/") + "/" + next_line
            if u not in urls and len(u) > 10:
                urls.append(u)

    # 也从合并文本中提取（兜底）
    merged = text.replace("\r\n", " ").replace("\n", " ")
    for u in re.findall(r'https?://[^\s<>"\')\]，。、；]+', merged):
        u = u.rstrip(".,;。、；").replace(" ", "")
        if u not in urls and len(u) > 10:
            urls.append(u)

    # 修复：如果一个短 URL 是另一个长 URL 的前缀，去掉短的
    # 例如 "https://zhaopin.cgdg" 和 "https://zhaopin.cgdg.com" 同时存在时
    fixed = []
    common_tlds = {'com', 'cn', 'net', 'org', 'edu', 'gov', 'cc', 'co', 'io', 'me', 'top', 'xyz'}
    for u in urls:
        # 检查是否有更长的 URL 以当前 URL + .xxx 结尾（前缀去重）
        is_prefix = False
        for other in urls:
            if other != u and other.startswith(u) and len(other) > len(u):
                suffix = other[len(u):]
                if re.match(r'^\.[a-zA-Z]{2,}', suffix):
                    is_prefix = True
                    break
        if is_prefix:
            continue
        # 检查 URL 的 TLD 是否合法
        from urllib.parse import urlparse
        parsed = urlparse(u)
        host = parsed.netloc
        if host:
            parts = host.split('.')
            if len(parts) >= 2:
                tld = parts[-1].lower()
                # 如果 TLD 不是常见后缀（OCR 截断），跳过这个 URL
                if tld not in common_tlds:
                    continue
                fixed.append(u)
            else:
                fixed.append(u)
        else:
            fixed.append(u)

    return fixed


def extract_emails(text):
    """从文本中精确提取所有邮箱"""
    if not text:
        return []
    return list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)))


def extract_dates(text):
    """从文本中提取日期"""
    if not text:
        return []
    patterns = [
        r'20\d{2}[年\-/.]\d{1,2}[月\-/.]\d{1,2}[日号]?',
        r'20\d{2}[年\-/.]\d{1,2}[月]',
        r'\d{1,2}[月\-/.]\d{1,2}[日号]',
    ]
    dates = []
    for p in patterns:
        dates.extend(re.findall(p, text))
    return list(dict.fromkeys(dates))  # 去重保序


def extract_phones(text):
    """从文本中提取电话"""
    if not text:
        return []
    return re.findall(r'1[3-9]\d{9}', text)


def fuzzy_find_urls(ocr_text):
    """从 OCR 乱码文本中模糊匹配 URL"""
    if not ocr_text:
        return []
    urls = []
    common_tlds = {'com', 'cn', 'net', 'org', 'edu', 'gov', 'cc', 'co', 'io', 'me', 'top', 'xyz'}
    known_domains = [
        r'igu[o0]?p[i1l]n',
        r'zha[o0]?p[i1l]n',
        r'hot[jJ]o[bB]',
        r'camp[uU][sS]',
        r'cec\.c[oO][mM]',
        r'pipech[i1l]n[aA]',
        r'crtc[\-\.]hr',
        r'cs[aA][i1l]r',
    ]
    text = ocr_text.lower().replace(" ", "")
    # 找域名模式（支持多级域名如 .com.cn）
    domain_pattern = r'[a-zA-Z0-9]{2,20}[\.。][a-zA-Z]{2,6}(?:\.[a-zA-Z]{2,4})?'
    for raw in re.findall(domain_pattern, text):
        raw_clean = raw.replace("。", ".")
        # 验证 TLD 是否合法
        parts = raw_clean.split('.')
        if len(parts) < 2 or parts[-1] not in common_tlds:
            continue
        for pattern in known_domains:
            if re.search(pattern, raw_clean, re.IGNORECASE):
                url = raw_clean if raw_clean.startswith("http") else "https://" + raw_clean
                urls.append(url)
                break
    # 模糊找 http
    for u in re.findall(r'(?:ht|htt|http|htts)[sS]?[:／.][／/][^\s]{5,60}', ocr_text):
        u = u.replace("／", "/").replace("：", ":")
        # 验证 TLD
        from urllib.parse import urlparse
        try:
            parsed = urlparse(u)
            tld = parsed.netloc.split('.')[-1].lower() if '.' in parsed.netloc else ''
            if tld and tld not in common_tlds:
                continue
        except Exception:
            continue
        if u not in urls:
            urls.append(u)
    return urls


def detect_qr_codes(image_url):
    """从图片中检测 QR 码"""
    try:
        import cv2
        import numpy as np
        from pyzbar.pyzbar import decode
        resp = requests.get(image_url, timeout=15, headers={
            "User-Agent": HEADERS["User-Agent"],
            "Referer": "https://mp.weixin.qq.com/"
        })
        resp.raise_for_status()
        img = cv2.imdecode(np.frombuffer(resp.content, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return []
        results = decode(img)
        urls = []
        for r in results:
            data = r.data.decode("utf-8", errors="ignore").strip()
            if data.startswith("http"):
                urls.append(data)
        return urls
    except Exception:
        return []


def scrape_qr_landing(url):
    """爬取 QR 码跳转的页面原始内容"""
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        resp.encoding = "utf-8"
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "lxml")
        # 提取页面所有文本
        text = soup.get_text(separator="\n", strip=True)
        # 提取所有链接
        links = [a.get("href", "") for a in soup.select("a[href]")]
        links = [l for l in links if l.startswith("http")]
        return {"text": text[:8000], "links": links[:20]}
    except Exception:
        return {"text": "", "links": []}


def is_noise(text):
    """判断文本是否为噪音"""
    if not text or len(text) < 4:
        return True
    # 纯标点/符号
    if re.match(r'^[\s\W]+$', text):
        return True
    # 大部分是特殊字符
    alpha_ratio = sum(1 for c in text if c.isalnum()) / max(len(text), 1)
    if alpha_ratio < 0.3:
        return True
    # 常见噪音模式
    noise_patterns = [
        r'^(点击|长按|识别|扫描|二维码|关注|阅读原文|阅读全文)',
        r'^(责任编辑|执行主编|校对|来源|来源丨)',
        r'^(—|—{2,}|={2,}|\*{2,}|#{2,})',
        r'^\d+$',  # 纯数字
        r'^[a-zA-Z]{1,3}$',  # 短字母
        r'^(更多|精彩|近期|热门|视频号|公众号)',
    ]
    for p in noise_patterns:
        if re.match(p, text.strip()):
            return True
    return False


def clean_ocr_text(text):
    """清理 OCR 文字，去掉噪音行"""
    if not text:
        return ""
    lines = text.split("\n")
    clean = []
    for line in lines:
        line = line.strip()
        if not is_noise(line):
            clean.append(line)
    return "\n".join(clean)


def extract_between(text, start_kw, end_kws, max_len=200):
    """提取两个关键词之间的内容"""
    for sk in start_kw:
        idx = text.find(sk)
        if idx == -1:
            continue
        start = idx + len(sk)
        end = len(text)
        for ek in end_kws:
            e = text.find(ek, start)
            if e != -1 and e < end:
                end = e
        result = text[start:end].strip()
        # 清理
        result = re.sub(r'\s+', ' ', result)
        if len(result) > max_len:
            result = result[:max_len]
        if result and len(result) > 2:
            return result
    return ""


def extract_job_info(text, title=""):
    """从文本中精准提取招聘核心信息"""
    if not text:
        return {}
    info = {}

    # === 1. 投递链接 ===
    links = extract_links(text)
    skip_domains = ["baidu.com", "zaih.com", "jquery", "hm.baidu.com"]
    links = [l for l in links if not any(d in l.lower() for d in skip_domains)]
    if links:
        info["links"] = links[:10]

    # === 2. 投递邮箱 ===
    emails = extract_emails(text)
    if emails:
        info["emails"] = list(dict.fromkeys(emails))[:3]

    # === 3. 截止时间 ===
    deadline = ""
    deadline_patterns = [
        r'截止[时日期]*[：:\s]*(.*?)(?:[。\n]|$)',
        r'报名截止[：:\s]*(.*?)(?:[。\n]|$)',
        r'申请截止[：:\s]*(.*?)(?:[。\n]|$)',
        r'招聘截止[：:\s]*(.*?)(?:[。\n]|$)',
        r' deadline[：:\s]*(.*?)(?:[。\n]|$)',
        # OCR 可能把截止时间和日期分在不同行
        r'截止[时日期]*[：:\-\s]*\s*(20\d{2}[年\-/.]\d{1,2}[月\-/.]\d{1,2}[日号]?\s*\d{0,2}:?\d{0,2})',
    ]
    for p in deadline_patterns:
        m = re.search(p, text, re.IGNORECASE | re.DOTALL)
        if m:
            deadline = m.group(1).strip()[:50]
            deadline = re.sub(r'\s+', ' ', deadline)
            break
    if not deadline:
        dates = extract_dates(text)
        if dates:
            deadline = dates[-1]  # 取最后一个日期（通常是截止日期）
    if deadline:
        info["deadline"] = deadline

    # === 4. 工作地点 ===
    location = ""
    loc_patterns = [
        r'(?:工作地点|工作地|工作地址|地点|base|驻地)[：:\s]*(.*?)(?:[。\n；;]|$)',
        r'(?:工作[地点城市区域])[：:\s]*(.*?)(?:[。\n；;]|$)',
    ]
    for p in loc_patterns:
        m = re.search(p, text)
        if m:
            location = m.group(1).strip()[:60]
            break
    if not location:
        # 常见城市名匹配
        city_match = re.findall(r'(?:北京|上海|广州|深圳|杭州|南京|成都|武汉|西安|重庆|天津|苏州|长沙|郑州|青岛|大连|厦门|宁波|无锡|佛山|东莞|珠海|昆明|贵阳|合肥|福州|济南|哈尔滨|沈阳|长春|太原|石家庄|南昌|南宁|兰州|银川|西宁|呼和浩特|拉萨|乌鲁木齐|海口|三亚)[市]?', text)
        if city_match:
            location = "、".join(list(dict.fromkeys(city_match))[:5])
    if location:
        info["location"] = location

    # === 5. 招聘专业/学历 ===
    major = ""
    major_patterns = [
        r'(?:招聘专业|专业要求|专业背景|所需专业|专业)[：:\s]*(.*?)(?:[。\n；;]|$)',
        r'(?:学历要求|学历)[：:\s]*(.*?)(?:[。\n；;]|$)',
    ]
    for p in major_patterns:
        m = re.search(p, text)
        if m:
            val = m.group(1).strip()[:80]
            if val:
                major = val
                break
    if major:
        info["majors"] = major

    # === 6. 招聘对象 ===
    target = ""
    target_patterns = [
        # 匹配"招聘对象"后跟内容（支持跨行，支持 OCR 把：识别为一）
        (r'(?:招聘对象|招聘范围|面向对象)[：:\-\s]*(.*?)(?:[。\n；;]|招聘岗位|招聘专业|岗位信息|基本条件|任职|$)', re.DOTALL),
        (r'(?:应聘条件|报名条件)[：:\-\s]*(.*?)(?:[。\n；;]|招聘岗位|招聘专业|岗位信息|$)', re.DOTALL),
        (r'(?:20\d{2}届[应往]?届毕业生)', 0),
        (r'(?:应届[毕业]?生|往届[毕业]?生|社会人员|在校生)', 0),
    ]
    for p, flags in target_patterns:
        m = re.search(p, text, flags)
        if m:
            val = m.group(1).strip() if m.lastindex else m.group(0).strip()
            val = val[:100]
            # 清理换行和多余空格
            val = re.sub(r'\s+', ' ', val)
            if len(val) > 3:
                target = val
                break
    if not target:
        # 从标题推断：如果标题含"届"字，提取为目标
        m = re.search(r'(20\d{2}届[应往]?届?毕业生?)', title)
        if m:
            target = m.group(1)
    if target:
        info["target"] = target

    # === 7. 岗位信息 ===
    positions = ""
    pos_patterns = [
        r'(?:招聘岗位|岗位名称|岗位信息|岗位)[：:\s]*(.*?)(?:[。\n]|(?:任职|岗位职责|岗位要求))',
        r'(?:拟[招聘录][用聘]).*?(?:岗位|职位)[：:\s]*(.*?)(?:[。\n]|$)',
    ]
    for p in pos_patterns:
        m = re.search(p, text, re.DOTALL)
        if m:
            val = m.group(1).strip()[:200]
            if val:
                positions = val
                break
    if positions:
        info["positions"] = positions

    # === 8. 投递方式 ===
    apply_method = ""
    apply_patterns = [
        r'(?:报名方式|应聘方式|投递方式|简历投递|如何报名|申请方式)[：:\-\s]*(.*?)(?:[。\n]|(?:联系|邮箱|电话))',
        r'(?:请将简历|请发[送]简历|发送简历|投递简历)[：:\-\s]*(.*?)(?:[。\n]|$)',
        r'(?:报名通道|投递通道|网申地址|网申链接|招聘平台)[：:\-\s]*(.*?)(?:[。\n]|$)',
        r'(?:扫码投递|扫描二维码投递|扫描[下方二维码]|长按识别|扫码直达)',
    ]
    for p in apply_patterns:
        m = re.search(p, text, re.DOTALL)
        if m:
            val = m.group(0).strip()[:200]
            val = re.sub(r'\s+', ' ', val)
            if val:
                apply_method = val
                break
    if apply_method:
        info["apply_method"] = apply_method

    # === 9. 联系电话 ===
    phones = extract_phones(text)

    # === 10. 联系方式 ===
    contact = ""
    contact_patterns = [
        r'(?:联系电话|咨询电话|电话)[：:\s]*(.*?)(?:[。\n；;]|$)',
        r'(?:联系人)[：:\s]*(.*?)(?:[。\n；;]|$)',
    ]
    for p in contact_patterns:
        m = re.search(p, text)
        if m:
            val = m.group(1).strip()[:50]
            if val:
                contact = val
                break
    if not contact and phones:
        contact = phones[0]
    if contact:
        info["contact"] = contact

    return info


def process_job(job):
    """处理单条招聘信息 - 折中模式：OCR + AI 兜底"""
    content = job.get("content", "")
    all_text = content
    images = job.get("images", [])
    html_links = job.get("html_links", [])
    result = {
        "raw_content": content,
        "ocr_texts": [],
        "qr_links": [],
        "ai_texts": [],
        "extracted": {},
    }

    # 1. 从原文提取结构化数据
    result["extracted"] = extract_job_info(content, title=job.get("title", ""))

    # 1.5 合并 HTML 中的链接
    if html_links:
        skip_domains = ["baidu.com", "zaih.com", "jquery", "hm.baidu.com"]
        skip_patterns = ["appmsgalbum", "mp/appmsgalbum"]
        filtered = [l for l in html_links
                    if not any(d in l.lower() for d in skip_domains)
                    and not any(p in l for p in skip_patterns)]
        if filtered:
            if "links" not in result["extracted"]:
                result["extracted"]["links"] = []
            result["extracted"]["links"] = filtered + result["extracted"]["links"]

    # 2. 处理每张图片
    for img_url in images:
        if "gif" in img_url.lower():
            continue

        # QR 码检测
        qr_urls = detect_qr_codes(img_url)
        if qr_urls:
            result["qr_links"].extend(qr_urls)
            if "links" not in result["extracted"]:
                result["extracted"]["links"] = []
            result["extracted"]["links"] = qr_urls + result["extracted"]["links"]

        # OCR 提取文字（清理噪音）
        ocr_text = ocr_image(img_url)
        if ocr_text:
            cleaned = clean_ocr_text(ocr_text)
            if cleaned:
                result["ocr_texts"].append(cleaned)
                all_text += "\n" + cleaned

        # AI 兜底：OCR 质量不够时用视觉模型
        if not ocr_quality_check(ocr_text):
            ai_text = ai_vision_extract(img_url)
            if ai_text:
                result["ai_texts"].append(ai_text)
                all_text += "\n" + ai_text

    # 3. 从 OCR 文字中提取结构化数据
    ocr_combined = "\n".join(result["ocr_texts"])
    ocr_info = extract_job_info(ocr_combined)
    for k, v in ocr_info.items():
        if k not in result["extracted"]:
            result["extracted"][k] = v
        elif isinstance(v, list):
            result["extracted"][k] = result["extracted"].get(k, []) + v

    # 3.5 模糊匹配 OCR 乱码中的 URL
    fuzzy_urls = fuzzy_find_urls(ocr_combined)
    if fuzzy_urls:
        if "links" not in result["extracted"]:
            result["extracted"]["links"] = []
        result["extracted"]["links"] = fuzzy_urls + result["extracted"]["links"]

    # 3.6 从 AI 视觉文字中提取结构化数据
    if result["ai_texts"]:
        ai_combined = "\n".join(result["ai_texts"])
        ai_info = extract_job_info(ai_combined)
        for k, v in ai_info.items():
            if k not in result["extracted"] or not result["extracted"][k]:
                result["extracted"][k] = v
            elif isinstance(v, list):
                existing = result["extracted"].get(k, [])
                result["extracted"][k] = existing + [x for x in v if x not in existing]

    # 4. QR 码跳转页面
    if result["qr_links"]:
        landing = scrape_qr_landing(result["qr_links"][0])
        if landing["text"]:
            result["landing_text"] = landing["text"]
            landing_info = extract_job_info(landing["text"])
            for k, v in landing_info.items():
                if k not in result["extracted"]:
                    result["extracted"][k] = v
                elif isinstance(v, list):
                    result["extracted"][k] = result["extracted"].get(k, []) + v
            # 合并链接
            if landing["links"]:
                result["extracted"]["links"] = result["extracted"].get("links", []) + landing["links"]

    # 5. 汇总所有文本（用于展示）
    result["full_text"] = all_text

    # 6. 链接智能排序 + 去重 + 过滤无效链接
    all_links = result["extracted"].get("links", [])
    if all_links:
        # 过滤掉合集页、非投递链接
        all_links = [l for l in all_links if 'appmsgalbum' not in l]

        def link_priority(url):
            u = url.lower()
            # 最高：招聘平台链接
            if any(kw in u for kw in ['recruit', 'apply', 'hire', 'campus', 'zhaopin', 'job', 'toudi', 'hr.']):
                return 0
            if any(kw in u for kw in ['/recruit', '/apply', '/campus', '/hire', '/toudi']):
                return 0
            # 中：非微信链接
            if 'weixin.qq.com' not in u and 'mp.weixin' not in u:
                return 1
            # 低：微信链接
            return 2
        all_links.sort(key=link_priority)
        from urllib.parse import urlparse
        seen_domains = set()
        deduped = []
        for l in all_links:
            domain = urlparse(l).netloc.lower()
            if domain not in seen_domains:
                seen_domains.add(domain)
                deduped.append(l)
        result["extracted"]["links"] = deduped[:5]

    return result


def process_all(jobs):
    """处理所有招聘信息"""
    print(f"\n[3/3] 数据提取（{len(jobs)} 条）...")
    for i, job in enumerate(jobs):
        print(f"  [{i+1}/{len(jobs)}] {job['title'][:30]}...")
        extracted = process_job(job)
        job["extracted"] = extracted["extracted"]
        job["ocr_texts"] = extracted["ocr_texts"]
        job["ai_texts"] = extracted.get("ai_texts", [])
        job["full_text"] = extracted["full_text"]
        if "landing_text" in extracted:
            job["landing_text"] = extracted["landing_text"]
    return jobs
