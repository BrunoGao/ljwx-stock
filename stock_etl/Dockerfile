FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

COPY requirements.txt /workspace/stock_etl/requirements.txt
RUN uv pip install --system --no-cache -r /workspace/stock_etl/requirements.txt

COPY . /workspace/stock_etl

CMD ["python", "-m", "stock_etl.app.main"]
