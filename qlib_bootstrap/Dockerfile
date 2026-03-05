FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

RUN mkdir -p /workspace/qlib_bootstrap
COPY requirements.txt /workspace/qlib_bootstrap/requirements.txt
RUN uv pip install --system --no-cache -r /workspace/qlib_bootstrap/requirements.txt

COPY . /workspace/qlib_bootstrap

CMD ["python", "-m", "qlib_bootstrap.app.main"]
