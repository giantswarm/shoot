FROM python:3.13-slim AS builder-py

RUN mkdir /build
WORKDIR /build

# Install uv 
RUN --mount=type=cache,target=/root/.cache,id=pip \
    python -m pip install uv 

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache,id=pip \
    uv pip install --system -r /build/requirements.txt

# Install Node.js and bash (required for npx and MCP servers)
RUN apt-get update && apt-get install -y \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Download and install mcp-kubernetes binary (latest v0.0.35)
RUN MCP_VERSION=0.0.36 && arch=$(uname -m) && \
    if [ "$arch" = "x86_64" ]; then \
      MCP_URL="https://github.com/giantswarm/mcp-kubernetes/releases/download/v${MCP_VERSION}/mcp-kubernetes_linux_amd64"; \
    elif [ "$arch" = "aarch64" ] || [ "$arch" = "arm64" ]; then \
      MCP_URL="https://github.com/giantswarm/mcp-kubernetes/releases/download/v${MCP_VERSION}/mcp-kubernetes_linux_arm64"; \
    else \
      echo "Unsupported architecture: $arch" && exit 1; \
    fi && \
    curl -L $MCP_URL -o /build/mcp-kubernetes \
    && chmod +x /build/mcp-kubernetes


#Final image
FROM python:3.13-slim AS release 
COPY --from=builder-py /usr/local /usr/local
COPY --from=builder-py /build/mcp-kubernetes /build/mcp-kubernetes

WORKDIR /app

COPY main.py .

CMD ["python", "main.py"]

