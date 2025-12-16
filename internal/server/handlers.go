package server

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/giantswarm/shoot/internal/agents"
	"github.com/giantswarm/shoot/internal/config"
)

// Server holds the HTTP server with ADK-based agents
type Server struct {
	coordinator *agents.Coordinator
	wcCollector *agents.CollectorAgent
	mcCollector *agents.CollectorAgent
	config      *config.Config
}

// HealthResponse represents the health check response
type HealthResponse struct {
	Status string `json:"status"`
}

// ReadyResponse represents the readiness check response
type ReadyResponse struct {
	Status       string `json:"status"`
	KubernetesWC bool   `json:"kubernetes_wc"`
	KubernetesMC bool   `json:"kubernetes_mc"`
	Coordinator  bool   `json:"coordinator"`
}

// QueryRequest represents the query request body
type QueryRequest struct {
	Query string `json:"query"`
}

// ErrorResponse represents an error response
type ErrorResponse struct {
	Detail string `json:"detail"`
}

// NewServer creates a new HTTP server with ADK agents
func NewServer(coordinator *agents.Coordinator, wcCollector, mcCollector *agents.CollectorAgent, cfg *config.Config) *Server {
	return &Server{
		coordinator: coordinator,
		wcCollector: wcCollector,
		mcCollector: mcCollector,
		config:      cfg,
	}
}

// HealthHandler handles health check requests
func (s *Server) HealthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(HealthResponse{Status: "healthy"})
}

// ReadyHandler handles readiness check requests
func (s *Server) ReadyHandler(w http.ResponseWriter, r *http.Request) {
	checks := ReadyResponse{
		Status:       "ready",
		KubernetesWC: s.wcCollector != nil,
		KubernetesMC: s.mcCollector != nil,
		Coordinator:  s.coordinator != nil,
	}

	// If any critical dependency is missing, return 503
	if !checks.KubernetesWC || !checks.KubernetesMC || !checks.Coordinator {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(checks)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(checks)
}

// QueryHandler handles the main query requests with ADK agents
func (s *Server) QueryHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusMethodNotAllowed)
		json.NewEncoder(w).Encode(ErrorResponse{Detail: "Method not allowed"})
		return
	}

	// Parse request body
	var req QueryRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(ErrorResponse{Detail: fmt.Sprintf("Invalid request body: %v", err)})
		return
	}

	if req.Query == "" {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusBadRequest)
		json.NewEncoder(w).Encode(ErrorResponse{Detail: "Query is required"})
		return
	}

	// Run the coordinator agent
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	result, err := s.coordinator.Run(ctx, req.Query)
	if err != nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(ErrorResponse{Detail: err.Error()})
		return
	}

	// Return the result as JSON string (matching Python behavior)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(result)
}

// loggingMiddleware logs HTTP requests but filters out health/ready checks
func (s *Server) loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Skip logging for health and ready endpoints
		if r.URL.Path == "/health" || r.URL.Path == "/ready" {
			next.ServeHTTP(w, r)
			return
		}

		start := time.Now()
		next.ServeHTTP(w, r)
		duration := time.Since(start)

		fmt.Printf("%s %s - %v\n", r.Method, r.URL.Path, duration)
	})
}

// SetupRoutes sets up all HTTP routes
func (s *Server) SetupRoutes() http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("/health", s.HealthHandler)
	mux.HandleFunc("/ready", s.ReadyHandler)
	mux.HandleFunc("/", s.QueryHandler)

	return s.loggingMiddleware(mux)
}
