FROM python:3.13-alpine AS builder-py

RUN mkdir /build
WORKDIR /build

RUN apk add --no-cache curl

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

# Install uv and dependencies
RUN --mount=type=cache,target=/root/.cache,id=pip \
    python -m pip install uv 

COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache,id=pip \
    uv pip install --system -r /build/requirements.txt

#Final image
FROM python:3.13-alpine AS release 
COPY --from=builder-py /usr/local /usr/local
RUN mkdir /app
WORKDIR /app
#COPY kubeconfig.yaml .
COPY --from=builder-py /build/mcp-kubernetes /app/mcp-kubernetes
COPY main.py .

CMD ["python", "main.py"]

