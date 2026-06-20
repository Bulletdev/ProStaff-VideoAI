FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential curl ffmpeg unzip nodejs \
    && curl -fsSL https://deno.land/install.sh | sh \
    && ln -sf /root/.deno/bin/deno /usr/local/bin/deno \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
