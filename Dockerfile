# Multi-stage build for Go application with Claude CLI

# Stage 1: Build Go application
FROM golang:1.23-alpine AS builder

WORKDIR /build

# Copy go mod files
COPY go.mod go.sum* ./

# Download dependencies
RUN go mod download

# Copy source code
COPY main.go ./

# Build static binary
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o shoot .

# Stage 2: Runtime image
FROM alpine:3.19

# Install dependencies
RUN apk add --no-cache \
    ca-certificates \
    curl \
    bash

# Install Claude CLI using official install script
RUN curl -fsSL https://claude.ai/install.sh | bash

# Download and install mcp-kubernetes binary (v0.0.41)
RUN curl -L https://github.com/giantswarm/mcp-kubernetes/releases/download/v0.0.41/mcp-kubernetes_linux_amd64 -o /usr/local/bin/mcp-kubernetes \
    && chmod +x /usr/local/bin/mcp-kubernetes

# Create app directory
WORKDIR /app

# Copy Go binary from builder
COPY --from=builder /build/shoot .

# Copy configuration files
COPY .claude/ ./.claude/
COPY prompts/ ./prompts/

# Expose port
EXPOSE 8000

# Run the application
CMD ["./shoot"]
