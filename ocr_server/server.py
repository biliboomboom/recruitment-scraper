import os
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'

from flask import Flask, request, jsonify
from paddleocr import PaddleOCR
import numpy as np
import cv2
import base64
import logging

logging.disable(logging.WARNING)

app = Flask(__name__)

# 初始化 OCR（PP-OCRv5）
print("[OCR] 加载 PaddleOCR 3.x + PP-OCRv5...")
ocr = PaddleOCR(
    lang='ch',
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)
print("[OCR] 模型就绪")


@app.route('/ocr', methods=['POST'])
def ocr_endpoint():
    """OCR 识别接口"""
    try:
        data = request.json
        image_input = data.get('image', '')

        # 解码图片
        if image_input.startswith('http'):
            import requests as req
            resp = req.get(image_input, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://mp.weixin.qq.com/'
            })
            img_array = np.frombuffer(resp.content, np.uint8)
        elif ',' in image_input:
            b64_data = image_input.split(',', 1)[1]
            img_array = np.frombuffer(base64.b64decode(b64_data), np.uint8)
        else:
            img_array = np.frombuffer(base64.b64decode(image_input), np.uint8)

        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({'texts': [], 'count': 0})

        # 缩放大图
        h, w = img.shape[:2]
        if max(h, w) > 2000:
            scale = 2000 / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))

        # OCR 识别（不做额外预处理）
        result = ocr.predict(img)

        texts = []
        for r in result:
            texts.extend(r.get('rec_texts', []))

        return jsonify({'texts': texts, 'count': len(texts)})

    except Exception as e:
        return jsonify({'error': str(e), 'texts': [], 'count': 0}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'model': 'PP-OCRv5', 'engine': 'PaddleOCR 3.x'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
