# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS ml-base
ARG TORCH_VERSION=2.13.0
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src HF_HOME=/opt/huggingface
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install --upgrade pip
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install torch==${TORCH_VERSION} --index-url https://download.pytorch.org/whl/cpu
COPY requirements-ml.txt ./requirements-ml.txt
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install -r requirements-ml.txt
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
FROM ml-base AS runtime
COPY requirements-core.txt ./requirements-core.txt
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install -r requirements-core.txt
COPY src ./src
EXPOSE 8000 8501
CMD ["python","-m","uvicorn","api.app:app","--host","0.0.0.0","--port","8000"]
