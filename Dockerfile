# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for PostgreSQL, matplotlib, and debugging tools
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    bash \
    procps \
    net-tools \
    tcpdump \
    build-essential \
    libfreetype6-dev \
    libpng-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and configuration
COPY analysis_llm/ ./analysis_llm/
COPY config/ ./config/
COPY docs/ ./docs/

# Create necessary directories
RUN mkdir -p /app/logs /app/analysis_output

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose port for MCP server (streamable-http mode)
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.path.append('/app'); import analysis_llm.main; print('MCP server is healthy')" || exit 1

# Default command to run the MCP server
CMD ["python", "-m", "analysis_llm.main"]
