# 两阶段：builder 装依赖 + 预构建索引；runtime 只带运行必需的东西，非 root 运行。
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${PYTHON_IMAGE} AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt requirements-api.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt -r requirements-api.txt
COPY src ./src
COPY scripts ./scripts
COPY data/docs ./data/docs
RUN /opt/venv/bin/python scripts/build_index.py --docs data/docs --out data/index

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RAG_INDEX=/app/data/index \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app
# 非 root：镜像被拿去做扫描/部署时不会报 root 运行
RUN groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser
COPY --from=builder /opt/venv /opt/venv
COPY api ./api
COPY src ./src
COPY --from=builder /build/data/index ./data/index
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
