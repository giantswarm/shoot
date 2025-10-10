# Use Python 3.13 slim image as base
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Download and install mcp-kubernetes binary (latest v0.0.35)
RUN MCP_VERSION=0.0.36 && arch=$(uname -m) && \
    if [ "$arch" = "x86_64" ]; then \
      MCP_URL="https://github.com/giantswarm/mcp-kubernetes/releases/download/v${MCP_VERSION}/mcp-kubernetes_linux_amd64"; \
    elif [ "$arch" = "aarch64" ] || [ "$arch" = "arm64" ]; then \
      MCP_URL="https://github.com/giantswarm/mcp-kubernetes/releases/download/v${MCP_VERSION}/mcp-kubernetes_linux_arm64"; \
    else \
      echo "Unsupported architecture: $arch" && exit 1; \
    fi && \
    curl -L $MCP_URL -o /app/mcp-kubernetes \
    && chmod +x /app/mcp-kubernetes

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py .

# Run the application
CMD ["python", "main.py"]

