##@ Go Development

.PHONY: go-build
go-build: ## Build the Go binary
	@echo "Building Go binary..."
	CGO_ENABLED=0 go build -o bin/shoot .

.PHONY: go-run
go-run: ## Run the Go application locally
	@echo "Running Go application..."
	go run .

.PHONY: go-test
go-test: ## Run Go tests
	@echo "Running Go tests..."
	go test -v ./...

.PHONY: go-lint
go-lint: ## Run Go linters
	@echo "Running Go linters..."
	go fmt ./...
	go vet ./...

.PHONY: go-mod-tidy
go-mod-tidy: ## Tidy Go module dependencies
	@echo "Tidying Go modules..."
	go mod tidy

.PHONY: docker-build
docker-build: ## Build Docker image
	@echo "Building Docker image..."
	docker build -t shoot:latest .

.PHONY: docker-run
docker-run: ## Run Docker container
	@echo "Running Docker container..."
	docker run --rm -p 8000:8000 \
		-e OPENAI_API_KEY="${OPENAI_API_KEY}" \
		-e OPENAI_COORDINATOR_MODEL="${OPENAI_COORDINATOR_MODEL}" \
		-e OPENAI_COLLECTOR_MODEL="${OPENAI_COLLECTOR_MODEL}" \
		-e WC_CLUSTER="${WC_CLUSTER}" \
		-e ORG_NS="${ORG_NS}" \
		-e DEBUG="${DEBUG}" \
		shoot:latest

.PHONY: go-clean
go-clean: ## Clean Go build artifacts
	@echo "Cleaning Go build artifacts..."
	rm -rf bin/
	go clean

