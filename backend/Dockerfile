# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY requirements.txt requirements-ml.txt ./
RUN pip install -r requirements.txt

# Build with --build-arg INSTALL_ML=true to bundle the self-hosted model runtime (CPU-only torch).
ARG INSTALL_ML=false
RUN if [ "$INSTALL_ML" = "true" ]; then \
      pip install torch --index-url https://download.pytorch.org/whl/cpu && \
      pip install -r requirements-ml.txt; \
    fi

COPY app ./app
RUN useradd --system --create-home --uid 10001 imageproof && chown -R imageproof /srv
USER imageproof
ENV HF_HOME=/home/imageproof/.cache/huggingface

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).status==200 else 1)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header", "--no-access-log"]
