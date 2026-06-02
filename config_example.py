# 招聘信息爬虫配置
# 复制此文件为 config.py 并填入你的配置

# 目标网站
BASE_URL = "http://job.mohrss.gov.cn/qyzp"
LIST_URL = f"{BASE_URL}/index.jhtml"
SITE_NAME = "央企招聘"

# 请求配置
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
REQUEST_DELAY = 1

# AI 视觉 API 配置（用于 OCR 失败时的图片识别兜底）
AI_VISION_API_KEY = ""  # 填入你的 API key
AI_VISION_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
AI_VISION_MODEL = "mimo-v2-omni"

# 输出配置
OUTPUT_DIR = "output"
