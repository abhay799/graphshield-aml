FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-core.txt requirements-ml.txt requirements-live-scoring.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install -r requirements-ml.txt \
    && python -m pip install -r requirements-core.txt \
    && python -m pip install -r requirements-live-scoring.txt

COPY src ./src
COPY models ./models
COPY data ./data
COPY reports ./reports
COPY run_api.py ./run_api.py

EXPOSE 8080
CMD ["python", "run_api.py"]
