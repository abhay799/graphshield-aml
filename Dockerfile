FROM python:3.12-slim
ARG TORCH_VERSION=2.13.0
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV HF_HOME=/opt/huggingface
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements-runtime.txt ./requirements-runtime.txt
RUN python -m pip install --upgrade pip
RUN python -m pip install --no-cache-dir torch==${TORCH_VERSION} --index-url https://download.pytorch.org/whl/cpu
RUN python -m pip install --no-cache-dir -r requirements-runtime.txt
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
COPY src ./src
EXPOSE 8000 8501
CMD ["python","-m","uvicorn","api.app:app","--host","0.0.0.0","--port","8000"]
