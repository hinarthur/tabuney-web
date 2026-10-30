# 使用官方的 Python 鏡像
FROM python:3.12.3

# ===============================
# 建置參數：區分 local 開發 vs VPS production
#   WITH_HEAVY=1 (預設) → 安裝系統 OCR 套件與 CPU 版 torch（local 開發）
#   WITH_HEAVY=0        → 跳過上述，僅裝精簡 base requirements（VPS production）
#   REQ_FILE            → requirements.dev.txt（完整）或 requirements.base.txt（精簡）
# production 建置範例：
#   docker build --build-arg WITH_HEAVY=0 --build-arg REQ_FILE=requirements.base.txt .
# ===============================
ARG WITH_HEAVY=1
ARG REQ_FILE=requirements.dev.txt

# 安裝 tzdata 並設定時區
# ENV TZ=Europe/London
# RUN apt-get update && \
#     DEBIAN_FRONTEND=noninteractive apt-get install -y tzdata && \
#     ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && \
#     echo $TZ > /etc/timezone && \
#     dpkg-reconfigure -f noninteractive tzdata && \
#     apt-get clean && rm -rf /var/lib/apt/lists/*

# ===============================
# 1️⃣ 系統層套件（OCR / OpenCV）— 僅 local（WITH_HEAVY=1）需要
# ===============================
RUN if [ "$WITH_HEAVY" = "1" ]; then \
      apt-get update && apt-get install -y \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-chi-tra \
        tesseract-ocr-chi-sim \
        tesseract-ocr-fra \
        tesseract-ocr-spa \
        tesseract-ocr-deu \
        tesseract-ocr-jpn \
        libgl1 \
        libglib2.0-0 \
      && rm -rf /var/lib/apt/lists/*; \
    fi

# ===============================
# 2️⃣ 工作目錄
# ===============================
WORKDIR /app

# ===============================
# 3️⃣ Python 依賴
# ===============================
# 三個檔案都複製進來（dev.txt 內含 `-r requirements.base.txt`）
COPY requirements.txt requirements.base.txt requirements.dev.txt /app/

# 安裝項目依賴
RUN pip install --upgrade pip
# 先強制安裝 CPU 版的 PyTorch（僅 local；production 不需要 torch）
RUN if [ "$WITH_HEAVY" = "1" ]; then \
      pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu; \
    fi
# 再安裝對應層級的依賴（dev=完整 / base=精簡）
RUN pip install --no-cache-dir -r $REQ_FILE

# ===============================
# 4️⃣ App code
# ===============================
# 複製項目文件到容器
COPY . /app
# COPY wait-for-it.sh /app/
RUN chmod +x /app/wait-for-it.sh

# 暴露端口
EXPOSE 8000

# 啟動Django 開發服務器
# CMD ["python", "initialize_site.py", "&&", "python", "manage.py", "runserver", "0.0.0.0:8000"]
# CMD ["sh", "-c", "./wait-for-it.sh postgres:5432 -- python initialize_site.py && python manage.py runserver 0.0.0.0:8000"]
CMD ["bash", "-c", "./wait-for-it.sh postgres:5432 -- python initialize_site.py && python manage.py runserver 0.0.0.0:8000"]
