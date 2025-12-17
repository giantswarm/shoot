package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"
)

// QueryRequest represents the incoming HTTP request
type QueryRequest struct {
	Query string `json:"query"`
}

// QueryResponse represents the response sent back to the client
type QueryResponse struct {
	Result       string  `json:"result"`
	SessionID    string  `json:"session_id,omitempty"`
	TotalCostUSD float64 `json:"total_cost_usd,omitempty"`
	DurationMS   int     `json:"duration_ms,omitempty"`
}

// ClaudeResponse represents the JSON output from claude CLI
type ClaudeResponse struct {
	Type         string  `json:"type"`
	Subtype      string  `json:"subtype"`
	Result       string  `json:"result"`
	SessionID    string  `json:"session_id"`
	TotalCostUSD float64 `json:"total_cost_usd"`
	DurationMS   int     `json:"duration_ms"`
	IsError      bool    `json:"is_error"`
}

var (
	logger            *slog.Logger
	coordinatorPrompt string
	wcCluster         string
	orgNS             string
	mcpConfigPath     string
)

func main() {
	// Initialize structured logger
	logger = slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))

	// Load environment variables
	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}

	wcCluster = os.Getenv("WC_CLUSTER")
	if wcCluster == "" {
		logger.Error("WC_CLUSTER environment variable is required")
		os.Exit(1)
	}

	orgNS = os.Getenv("ORG_NS")
	if orgNS == "" {
		logger.Error("ORG_NS environment variable is required")
		os.Exit(1)
	}

	// Load coordinator prompt
	promptBytes, err := os.ReadFile("prompts/coordinator_prompt.md")
	if err != nil {
		logger.Error("Failed to load coordinator prompt", "error", err)
		os.Exit(1)
	}

	// Substitute template variables
	coordinatorPrompt = string(promptBytes)
	coordinatorPrompt = strings.ReplaceAll(coordinatorPrompt, "${WC_CLUSTER}", wcCluster)
	coordinatorPrompt = strings.ReplaceAll(coordinatorPrompt, "${ORG_NS}", orgNS)

	// Determine MCP config file based on KUBECONFIG presence
	// KUBECONFIG is set in local dev, not set in Kubernetes pods
	mcpConfigPath = ".claude/mcp_config.k8s.json" // default to in-cluster
	if os.Getenv("KUBECONFIG") != "" {
		mcpConfigPath = ".claude/mcp_config.local.json" // use kubeconfig
	}

	logger.Info("Initialized shoot service",
		"port", port,
		"wc_cluster", wcCluster,
		"org_ns", orgNS,
		"mcp_config", mcpConfigPath,
	)

	// Set up HTTP handlers
	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/ready", readyHandler)
	http.HandleFunc("/", queryHandler)

	// Start server
	addr := fmt.Sprintf(":%s", port)
	logger.Info("Starting HTTP server", "address", addr)

	if err := http.ListenAndServe(addr, nil); err != nil {
		logger.Error("Server failed", "error", err)
		os.Exit(1)
	}
}

// healthHandler handles liveness probes
func healthHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "healthy"})
}

// readyHandler handles readiness probes
func readyHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Check if claude CLI is available
	_, err := exec.LookPath("claude")
	if err != nil {
		logger.Error("Claude CLI not found in PATH", "error", err)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(map[string]interface{}{
			"status": "not_ready",
			"reason": "claude CLI not available",
		})
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "ready"})
}

// queryHandler handles the main query endpoint
func queryHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Parse request
	var req QueryRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		logger.Error("Failed to parse request", "error", err)
		http.Error(w, "Invalid JSON request", http.StatusBadRequest)
		return
	}

	if req.Query == "" {
		logger.Error("Empty query received")
		http.Error(w, "Query field is required", http.StatusBadRequest)
		return
	}

	logger.Info("Processing query", "query", req.Query)

	// Execute claude CLI
	startTime := time.Now()
	result, err := executeClaude(req.Query, mcpConfigPath)
	if err != nil {
		logger.Error("Claude execution failed", "error", err, "duration", time.Since(startTime))
		http.Error(w, fmt.Sprintf("Claude execution failed: %v", err), http.StatusInternalServerError)
		return
	}

	logger.Info("Query completed",
		"duration", time.Since(startTime),
		"cost_usd", result.TotalCostUSD,
		"session_id", result.SessionID,
	)

	// Return response
	response := QueryResponse{
		Result:       result.Result,
		SessionID:    result.SessionID,
		TotalCostUSD: result.TotalCostUSD,
		DurationMS:   result.DurationMS,
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(response)
}

// executeClaude runs the claude CLI with the query and coordinator prompt
func executeClaude(query string, mcpConfigPath string) (*ClaudeResponse, error) {
	// Build claude command
	args := []string{
		"-p", query,
		"--append-system-prompt", coordinatorPrompt,
		"--mcp-config", mcpConfigPath,
		"--agents", ".claude/agents/",
		"--output-format", "json",
		"--permission-mode", "acceptEdits",
	}

	cmd := exec.Command("claude", args...)
	cmd.Dir = "." // Execute in current directory

	// Capture stdout and stderr
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	// Execute command
	if err := cmd.Run(); err != nil {
		logger.Error("Claude command failed",
			"error", err,
			"stderr", stderr.String(),
		)
		return nil, fmt.Errorf("claude command failed: %w (stderr: %s)", err, stderr.String())
	}

	// Parse JSON response
	var response ClaudeResponse
	if err := json.Unmarshal(stdout.Bytes(), &response); err != nil {
		logger.Error("Failed to parse claude response",
			"error", err,
			"stdout", stdout.String(),
		)
		return nil, fmt.Errorf("failed to parse claude response: %w", err)
	}

	// Check for errors in response
	if response.IsError {
		return nil, fmt.Errorf("claude returned error: %s", response.Result)
	}

	return &response, nil
}
