FROM python:3.11-slim

WORKDIR /app

COPY libs/py-shared /libs/py-shared
RUN pip install --no-cache-dir -e /libs/py-shared

COPY services/billing/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/billing/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
