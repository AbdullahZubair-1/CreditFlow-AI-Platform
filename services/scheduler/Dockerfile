FROM python:3.11-slim

WORKDIR /app

COPY libs/py-shared /libs/py-shared
RUN pip install --no-cache-dir -e /libs/py-shared

COPY services/scheduler/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/scheduler/app ./app

EXPOSE 8000
# Overridden per-container in docker-compose.yml for the worker/beat
# processes (same image, different CMD) — this default runs the REST API.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
