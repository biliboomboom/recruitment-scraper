FROM paddlepaddle/paddle:3.0.0

WORKDIR /app

# 安装 PaddleOCR + API 依赖
RUN pip install --no-cache-dir paddleocr flask -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制服务代码
COPY server.py .

# 预下载模型
RUN PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True python -c "\
from paddleocr import PaddleOCR;\
ocr = PaddleOCR(lang='ch', use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False);\
print('Models downloaded')"

EXPOSE 5000

CMD ["python", "server.py"]
