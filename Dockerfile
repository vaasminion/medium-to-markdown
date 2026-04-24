FROM python:3.11-slim

# System dependencies required by Chromium (Playwright / Patchright)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxcb1 libxkbcommon0 \
    libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libatspi2.0-0 libgtk-3-0 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install browser binaries for Playwright and Patchright
RUN scrapling install

COPY scraper.py .

ENV READING_LIST_URL=https://medium.com/@youruser/list/reading-list
ENV FREEDIUM_BASE=https://freedium-mirror.cfd/
ENV OUTPUT_DIR=/app/output
ENV STATE_FILE=/app/output/state.json
ENV RATE_LIMIT_SECONDS=2

CMD ["python", "scraper.py"]
