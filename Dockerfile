FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Environment defaults
ENV DATA_DIR=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Volume for persistent auth & database
VOLUME ["/data"]

CMD ["python", "src/main.py"]
