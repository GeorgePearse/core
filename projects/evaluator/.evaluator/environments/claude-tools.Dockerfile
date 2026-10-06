# Complete environment with all CLI tools from CLAUDE.md
# Includes: rg (ripgrep), fd-find, uv, fzf, jq, yq, ast-grep, and base dependencies

FROM python:3.11-slim

LABEL maintainer="retrocode" \
      description="Full environment with CLI tools for retrocode tests" \
      version="1.0"

# Install system dependencies (including build tools for cargo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    build-essential \
    ca-certificates \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Rust toolchain (needed for ripgrep, fd-find, ast-grep)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install ripgrep (rg) - fast recursive grep
RUN cargo install ripgrep --version 14.1.0 && \
    cargo cache --autoclean

# Install fd-find (fd) - user-friendly find alternative
RUN cargo install fd-find --version 10.1.0 && \
    cargo cache --autoclean

# Install ast-grep - AST-based code search
RUN cargo install ast-grep --version 0.21.2 && \
    cargo cache --autoclean

# Install uv (Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Install fzf (fuzzy finder) - pinned to stable version
RUN wget -qO- https://github.com/junegunn/fzf/releases/download/0.48.0/fzf-0.48.0-linux_amd64.tar.gz | \
    tar xz -C /usr/local/bin && \
    chmod +x /usr/local/bin/fzf

# Install jq (JSON query tool) - pinned to stable version
RUN wget -qO /usr/local/bin/jq https://github.com/stedolan/jq/releases/download/jq-1.7/jq-linux64 && \
    chmod +x /usr/local/bin/jq

# Install yq (YAML/XML query tool) - pinned to stable version
RUN wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/download/v4.40.5/yq_linux_amd64 && \
    chmod +x /usr/local/bin/yq

# Install Python dependencies for agent SDK
RUN pip install --no-cache-dir \
    anthropic>=0.18.0 \
    pydantic>=2.0 \
    pyyaml>=6.0 \
    tqdm>=4.60 \
    click>=8.0

# Set up working directory
WORKDIR /workspace

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/root/.cargo/bin:/root/.local/bin:${PATH}"

# Verify all tools are installed
RUN rg --version && \
    fd --version && \
    ast-grep --version && \
    uv --version && \
    fzf --version && \
    jq --version && \
    yq --version && \
    echo "All CLI tools installed successfully!"

# Default entrypoint
CMD ["/bin/bash"]
