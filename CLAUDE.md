# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

招聘信息爬虫项目，爬取央企招聘网站（job.mohrss.gov.cn）的招聘信息，提取结构化数据，输出 HTML 卡片页面。纯提取模式（无 AI API 依赖），数据 100% 来自原文。

## 运行命令

```bash
# 完整运行（爬取 + OCR + 提取 + 生成HTML）
python main.py

# 仅爬取（不分析）
python -c "from scraper import scrape_all; items = scrape_all()"

# 仅生成HTML（从已有JSON）
python -c "import json; from main import generate_html; items=json.load(open('output/jobs_YYYYMMDD.json','r',encoding='utf-8'))['jobs']; generate_html(items,'output/test.html')"
```

**前置条件**：Docker OCR 服务必须运行（端口 8899）

```bash
# 启动 OCR 服务
docker start ocr-api

# 如果容器不存在，重建
cd ocr_server && docker build -t paddleocr-server . && docker run -d --name ocr-api -p 8899:5000 paddleocr-server
```

## 架构

```
config.py          → 配置（URL、请求头、OCR服务地址）
scraper.py         → 爬取（列表页 + 详情页 + 微信文章）
ai_analyzer.py     → 数据提取（QR码 + Docker OCR + 正则）
ocr_server/        → Docker PaddleOCR 3.x 服务（PP-OCRv5）
main.py            → 主入口 + HTML 生成（PC多列/手机单列 + 网站筛选）
```

数据流：`网站列表 → 爬取文字 → 图片处理(QR+OCR) → 正则提取 → HTML`

## 关键设计决策

- **纯提取模式**：去掉了所有 AI API 调用（之前用 mimo-v2-omni），数据 100% 来自原文，不经过 AI 加工
- **Docker OCR**：PaddleOCR 3.x + PP-OCRv5 通过 Docker 容器提供 OCR 服务（Windows 原生安装有 oneDNN 兼容性问题），服务地址在 `config.py` 或 `ai_analyzer.py` 的 `OCR_API_URL`
- **QR 码检测**：用 pyzbar 扫描图片中的二维码获取投递链接（比 OCR 读 URL 更可靠）
- **正则提取**：从 OCR 文字和原文中用正则匹配结构化字段（链接、邮箱、日期、电话等），无 AI 参与
- **HTML 双模式**：PC 端多列网格布局，手机端单列卡片布局，通过 CSS 媒体查询切换
- **扩展性**：`config.py` 的 `SITE_NAME` 支持多网站，HTML 自动根据数据生成筛选按钮

## OCR 服务管理

OCR 运行在 Docker 容器中（`ocr_server/` 目录）：

```bash
# 检查状态
docker ps | grep ocr-api
curl http://localhost:8899/health

# 重启
docker restart ocr-api

# 查看日志
docker logs ocr-api --tail 20

# 停止/删除
docker stop ocr-api && docker rm ocr-api
```

OCR 服务端口默认 8899（映射容器内 5000），如被占用可在 `docker run -p` 和 `ai_analyzer.py` 的 `OCR_API_URL` 中修改。

## 输出

- `output/jobs_YYYYMMDD.json` — 结构化数据
- `output/jobs_YYYYMMDD.html` — 可视化卡片页面（PC+手机自适应）
