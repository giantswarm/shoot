# Build stage
FROM golang:1.24-alpine AS builder

# Install build dependencies
RUN apk add --no-cache git

# Set working directory
WORKDIR /build

# Copy go mod files
COPY go.mod go.sum ./

# Copy source code
COPY main.go .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -o shoot main.go

# Runtime stage
FROM alpine:latest

# Install ca-certificates for HTTPS requests
RUN apk --no-cache add ca-certificates

# Set working directory
WORKDIR /app

# Copy the binary from builder
COPY --from=builder /build/shoot .

# Copy mcp-kubernetes binary
COPY mcp-kubernetes ./mcp-kubernetes
RUN chmod +x ./mcp-kubernetes

# Copy kubeconfig
COPY kubeconfig.yaml .

# Set environment variables
ENV OPENAI_API_KEY=""
ENV KUBECONFIG=/app/kubeconfig.yaml

# Run the application
CMD ["./shoot"]

