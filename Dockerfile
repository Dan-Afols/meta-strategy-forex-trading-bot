FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Create directories
RUN mkdir -p data/charts logs ml_models/saved

# Non-root user
RUN useradd -m trader && chown -R trader:trader /app
USER trader

EXPOSE 8000

CMD ["python", "main.py"]
