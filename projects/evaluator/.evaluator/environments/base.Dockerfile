# Base environment for retrocode tests
# Provides Python 3.11 + anthropic SDK for running AI agent tests

FROM python:3.11-slim

LABEL maintainer="retrocode" \
      description="Base environment for retrocode AI agent tests" \
      version="1.0"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for agent SDK
RUN pip install --no-cache-dir \
    anthropic>=0.18.0 \
    pydantic>=2.0 \
    pyyaml>=6.0

# Set up working directory
WORKDIR /workspace

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/root/.local/bin:${PATH}"

# Default entrypoint
CMD ["/bin/bash"]
