FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including Chrome dependencies for seleniumbase
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    git \
    wget \
    gnupg \
    unzip \
    xvfb \
    libxi6 \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    fonts-liberation \
    libappindicator3-1 \
    libdrm2 \
    libxrandr2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Clear Python cache to ensure fresh code execution
RUN find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find . -type f -name "*.pyc" -delete 2>/dev/null || true && \
    find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Set Python path to include current directory
ENV PYTHONPATH=/app:$PYTHONPATH

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
