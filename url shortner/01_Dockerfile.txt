# Pin the base image to an exact Debian slim release with Python 3.12
FROM python:3.12.8-slim-bookworm

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/appuser/.local/bin:${PATH}"

# Install curl for healthcheck support and clean up apt cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m -s /sbin/nologin appuser

# Set working directory
WORKDIR /app

# Copy dependency definition first to leverage Docker layer caching
COPY requirements.txt .

# Install dependencies before copying source code
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code with non-root ownership
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8080

# Command to start the app, listening on 0.0.0.0:8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
