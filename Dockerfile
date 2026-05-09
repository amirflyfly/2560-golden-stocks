ARG PYTHON_BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r requirements.txt -i ${PIP_INDEX_URL}

COPY . .

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV APP_ENV=production
ENV WEB_WORKERS=2
ENV WEB_THREADS=4
ENV WEB_TIMEOUT=120
ENV WEB_GRACEFUL_TIMEOUT=30

RUN mkdir -p data

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8765/api/v1/readiness || exit 1

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:8765 --workers ${WEB_WORKERS:-2} --threads ${WEB_THREADS:-4} --timeout ${WEB_TIMEOUT:-120} --graceful-timeout ${WEB_GRACEFUL_TIMEOUT:-30} --access-logfile - --error-logfile - --capture-output app:app"]
