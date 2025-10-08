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

# Download and install mcp-kubernetes binary (latest v0.0.35)
# RUN curl -L https://github.com/containers/kubernetes-mcp-server/releases/download/v0.0.52/kubernetes-mcp-server-linux-amd64 -o /usr/local/bin/mcp-kubernetes \
#     && chmod +x /usr/local/bin/mcp-kubernetes

COPY mcp-kubernetes /usr/local/bin/mcp-kubernetes
RUN chmod +x /usr/local/bin/mcp-kubernetes

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py .

# Set environment variable for API key (can be overridden at runtime)
ENV OPENAI_API_KEY=""
ENV KUBECONFIG=/app/kubeconfig.yaml

# Run the application
CMD ["python", "main.py"]

