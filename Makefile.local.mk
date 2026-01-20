##@ Local Development

IMAGE_NAME ?= shoot
IMAGE_TAG ?= local
LOCAL_CONFIG_DIR ?= local_config

# Helper for optional JSON fields in curl commands
comma := ,

.PHONY: docker-build
docker-build: ## Build Docker image locally
	docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .

.PHONY: docker-run
docker-run: ## Run Docker container with local kubeconfigs
	@if [ ! -f $(LOCAL_CONFIG_DIR)/.env ]; then \
		echo "Error: $(LOCAL_CONFIG_DIR)/.env not found. Copy .env.example to $(LOCAL_CONFIG_DIR)/.env and configure it."; \
		exit 1; \
	fi
	docker run --rm -it \
		--env-file $(LOCAL_CONFIG_DIR)/.env \
		-v $(PWD)/$(LOCAL_CONFIG_DIR)/wc-kubeconfig.yaml:/k8s/wc-kubeconfig.yaml:ro \
		-v $(PWD)/$(LOCAL_CONFIG_DIR)/mc-kubeconfig.yaml:/k8s/mc-kubeconfig.yaml:ro \
		-v $(PWD)/config:/app/config:ro \
		-e KUBECONFIG=/k8s/wc-kubeconfig.yaml \
		-e MC_KUBECONFIG=/k8s/mc-kubeconfig.yaml \
		-e SHOOT_CONFIG=/app/config/shoot.yaml \
		-p 8000:8000 \
		$(IMAGE_NAME):$(IMAGE_TAG)

.PHONY: local-setup
local-setup: ## Create local_config directory with templates
	@mkdir -p $(LOCAL_CONFIG_DIR)
	@if [ ! -f $(LOCAL_CONFIG_DIR)/.env ]; then \
		cp .env.example $(LOCAL_CONFIG_DIR)/.env; \
		echo "Created $(LOCAL_CONFIG_DIR)/.env - edit with your ANTHROPIC_API_KEY"; \
	fi
	@echo ""
	@echo "Setup instructions:"
	@echo "  1. Edit $(LOCAL_CONFIG_DIR)/.env with your ANTHROPIC_API_KEY"
	@echo "  2. Place your kubeconfigs in $(LOCAL_CONFIG_DIR)/:"
	@echo "     - wc-kubeconfig.yaml (workload cluster)"
	@echo "     - mc-kubeconfig.yaml (management cluster)"
	@echo "  3. Configuration file: config/shoot.yaml (default)"
	@echo "     - Customize or set SHOOT_CONFIG to use a different config file"

.PHONY: local-kubeconfig
local-kubeconfig: ## Login to clusters via tsh and create kubeconfigs. Usage: make -f Makefile.local.mk local-kubeconfig MC=<cluster> [WC=<cluster>]
	@if [ -z "$(MC)" ]; then \
		echo "Error: MC parameter is required"; \
		echo "Usage: make -f Makefile.local.mk local-kubeconfig MC=<management-cluster> [WC=<workload-cluster>]"; \
		echo "  If WC is omitted, MC is used for both clusters"; \
		exit 1; \
	fi
	@mkdir -p $(LOCAL_CONFIG_DIR)
	@if [ -z "$(WC)" ]; then \
		echo "Using $(MC) for both MC and WC..."; \
		echo "Logging into $(MC)..."; \
		tsh kube login $(MC); \
		KUBECONFIG=$(PWD)/$(LOCAL_CONFIG_DIR)/mc-kubeconfig.yaml tsh kube login $(MC); \
		cp $(PWD)/$(LOCAL_CONFIG_DIR)/mc-kubeconfig.yaml $(PWD)/$(LOCAL_CONFIG_DIR)/wc-kubeconfig.yaml; \
		echo "Created $(LOCAL_CONFIG_DIR)/mc-kubeconfig.yaml"; \
		echo "Created $(LOCAL_CONFIG_DIR)/wc-kubeconfig.yaml (copy of MC)"; \
	else \
		echo "Logging into MC: $(MC)..."; \
		KUBECONFIG=$(PWD)/$(LOCAL_CONFIG_DIR)/mc-kubeconfig.yaml tsh kube login $(MC); \
		echo "Created $(LOCAL_CONFIG_DIR)/mc-kubeconfig.yaml"; \
		echo "Logging into WC: $(WC)..."; \
		KUBECONFIG=$(PWD)/$(LOCAL_CONFIG_DIR)/wc-kubeconfig.yaml tsh kube login $(WC); \
		echo "Created $(LOCAL_CONFIG_DIR)/wc-kubeconfig.yaml"; \
	fi
	@echo "Done! Kubeconfigs saved to $(LOCAL_CONFIG_DIR)/"

.PHONY: local-mcp
local-mcp: ## Download mcp-kubernetes binary to local_config
	@mkdir -p $(LOCAL_CONFIG_DIR)
	@if [ -f $(LOCAL_CONFIG_DIR)/mcp-kubernetes ]; then \
		echo "mcp-kubernetes already exists in $(LOCAL_CONFIG_DIR)/"; \
	else \
		echo "Downloading mcp-kubernetes..."; \
		ARCH=$$(uname -m); \
		OS=$$(uname -s | tr '[:upper:]' '[:lower:]'); \
		if [ "$$ARCH" = "arm64" ]; then ARCH="arm64"; elif [ "$$ARCH" = "x86_64" ]; then ARCH="amd64"; fi; \
		curl -L "https://github.com/giantswarm/mcp-kubernetes/releases/latest/download/mcp-kubernetes_$${OS}_$${ARCH}" \
			-o $(LOCAL_CONFIG_DIR)/mcp-kubernetes; \
		chmod +x $(LOCAL_CONFIG_DIR)/mcp-kubernetes; \
		echo "Downloaded to $(LOCAL_CONFIG_DIR)/mcp-kubernetes"; \
	fi

.PHONY: local-deps
local-deps: ## Create .venv and install/sync dependencies
	@if [ ! -d .venv ]; then \
		echo "Creating virtualenv..."; \
		uv venv .venv; \
	fi
	@echo "Installing dependencies..."
	@uv pip install -r requirements.txt

.PHONY: local-run
local-run: local-deps ## Run locally with uvicorn using local_config/.env and kubeconfigs
	@if [ ! -f $(LOCAL_CONFIG_DIR)/.env ]; then \
		echo "Error: $(LOCAL_CONFIG_DIR)/.env not found. Run 'make -f Makefile.local.mk local-setup' first."; \
		exit 1; \
	fi
	@if [ ! -f $(LOCAL_CONFIG_DIR)/wc-kubeconfig.yaml ]; then \
		echo "Error: $(LOCAL_CONFIG_DIR)/wc-kubeconfig.yaml not found. Run 'make -f Makefile.local.mk local-kubeconfig MC=<cluster>' first."; \
		exit 1; \
	fi
	@set -a && . $(LOCAL_CONFIG_DIR)/.env && set +a && \
		KUBECONFIG=$(PWD)/$(LOCAL_CONFIG_DIR)/wc-kubeconfig.yaml \
		MC_KUBECONFIG=$(PWD)/$(LOCAL_CONFIG_DIR)/mc-kubeconfig.yaml \
		MCP_KUBERNETES_PATH=$${MCP_KUBERNETES_PATH:-$(PWD)/$(LOCAL_CONFIG_DIR)/mcp-kubernetes} \
		SHOOT_CONFIG=$${SHOOT_CONFIG:-$(PWD)/config/shoot.yaml} \
		PYTHONPATH=$(PWD)/src \
		uv run uvicorn src.main:app --reload --port 8000

.PHONY: local-query
local-query: ## Send a test query to the local server. Usage: make -f Makefile.local.mk local-query [Q="your query"] [A="assistant_name"]
	@tmpfile=$$(mktemp); \
	curl -s http://localhost:8000/ \
		-H "Content-Type: application/json" \
		-d '{"query": "$(if $(Q),$(Q),List all namespaces in the workload cluster)"$(if $(A),$(comma) "assistant": "$(A)",)}' \
		> $$tmpfile; \
	jq -r '.result' $$tmpfile; \
	echo; \
	echo "================================================================================"; \
	echo "METRICS"; \
	echo "================================================================================"; \
	jq -r '"Assistant: \(.assistant)"' $$tmpfile; \
	jq -r '"Duration: \(.metrics.duration_ms / 1000)s"' $$tmpfile; \
	jq -r '"Turns: \(.metrics.num_turns)"' $$tmpfile; \
	jq -r '"Cost: $$\(.metrics.total_cost_usd)"' $$tmpfile; \
	jq -r '"Input tokens: \(.metrics.usage.input_tokens // 0)"' $$tmpfile; \
	jq -r '"Output tokens: \(.metrics.usage.output_tokens // 0)"' $$tmpfile; \
	if [ "$$(jq -r '.metrics.usage.cache_read_input_tokens // 0' $$tmpfile)" != "0" ]; then \
		jq -r '"Cache read tokens: \(.metrics.usage.cache_read_input_tokens)"' $$tmpfile; \
	fi; \
	if [ "$$(jq -r '.metrics.usage.cache_creation_input_tokens // 0' $$tmpfile)" != "0" ]; then \
		jq -r '"Cache creation tokens: \(.metrics.usage.cache_creation_input_tokens)"' $$tmpfile; \
	fi; \
	if [ "$$(jq -r '.metrics.breakdown' $$tmpfile)" != "null" ]; then \
		echo; \
		echo "Agent Breakdown:"; \
		jq -r '.metrics.breakdown | to_entries[] | "  \(.key):\n    Cost: $$\(.value.total_cost_usd // 0)\n    Input: \(.value.usage.input_tokens // 0), Output: \(.value.usage.output_tokens // 0)"' $$tmpfile; \
	fi; \
	rm -f $$tmpfile

.PHONY: local-assistants
local-assistants: ## List available assistants from the local server
	@curl -s http://localhost:8000/assistants | jq '.'

.PHONY: local-ready
local-ready: ## Check if the local server is ready (with deep checks)
	@curl -s "http://localhost:8000/ready?deep=true" | jq '.'
