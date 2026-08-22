# Dockerfile for PHD Scraper on VPS
FROM python:3.11-slim

# Set timezone and environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies if required (lxml build deps / ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY config/ ./config/
COPY scraper/ ./scraper/
COPY pyproject.toml .

# Create data and logs directories
RUN mkdir -p data logs

# Entry point defaults to scraper runner module
ENTRYPOINT ["python", "-m", "scraper.run"]
CMD ["scan"]
