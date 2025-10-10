# Use Python 3.13 slim image as base
FROM python:3.13-slim

# Install Node.js and bash (required for npx and MCP servers)
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    bash \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

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

# Set environment variable for API key (can be overridden at runtime)
ENV OPENAI_API_KEY=""
ENV KUBECONFIG=/app/kubeconfig.yaml
ENV MLFLOW_TRACKING_URI=http://localhost:5051

# Run the application
CMD ["python", "main.py"]

