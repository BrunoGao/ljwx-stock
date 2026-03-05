FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

RUN mkdir -p /workspace/qlib_predict
COPY requirements.txt /workspace/qlib_predict/requirements.txt
RUN uv pip install --system --no-cache -r /workspace/qlib_predict/requirements.txt

COPY . /workspace/qlib_predict

CMD ["python", "-m", "qlib_predict.app.predict_to_pg"]
