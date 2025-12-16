# Build stage
FROM golang:1.24-bookworm AS builder

WORKDIR /build

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY main.go .
COPY internal/ internal/

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -o shoot .

# Runtime stage
FROM debian:bookworm-slim

# Install bash (required for shell operations if needed)
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    bash \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Download and install mcp-kubernetes binary
RUN curl -L https://github.com/giantswarm/mcp-kubernetes/releases/download/v0.0.41/mcp-kubernetes_linux_amd64 -o /usr/local/bin/mcp-kubernetes \
    && chmod +x /usr/local/bin/mcp-kubernetes

# Set working directory
WORKDIR /app

# Copy the compiled binary from builder
COPY --from=builder /build/shoot .

# Copy prompt files
COPY prompts/ prompts/

# Expose port 8000
EXPOSE 8000

# Run the application
CMD ["./shoot"]
