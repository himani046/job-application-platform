FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

COPY . .

RUN mkdir -p /app/data/profiles /app/data/resumes /app/data/browsers /app/data/applications /app/data/jobs /app/data/runs

EXPOSE 8000 8501

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
