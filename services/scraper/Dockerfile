# Playwright's official image ships Chromium/Firefox/WebKit and all their
# OS-level dependencies already installed — far more reliable than
# `playwright install` on a bare python:3.11-slim base, which frequently
# fails without extra apt packages this image already has.
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

COPY libs/py-shared /libs/py-shared
RUN pip install --no-cache-dir -e /libs/py-shared

COPY services/scraper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/scraper/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
