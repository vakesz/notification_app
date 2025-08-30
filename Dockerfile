FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    FLASK_RUN_HOST=0.0.0.0 \
    FLASK_APP=app.web.main

WORKDIR /app

# Copy application code
COPY . .

# Install build dependencies and Python packages
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && pip install --upgrade pip \
    && pip install --no-cache-dir . gunicorn \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app.web.main:create_app()"]
