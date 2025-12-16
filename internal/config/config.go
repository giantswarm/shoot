package config

import (
	"fmt"
	"os"
	"strings"
)

// Config holds all configuration for the application
type Config struct {
	// OpenAI Configuration
	OpenAIAPIKey           string
	OpenAICoordinatorModel string
	OpenAICollectorModel   string

	// Cluster Configuration
	WCCluster string
	OrgNS     string

	// Debug Mode
	Debug bool

	// OpenTelemetry Configuration
	OTELEndpoint string
	OTELInsecure bool

	// Server Configuration
	ServerPort string
}

// LoadConfig loads configuration from environment variables
func LoadConfig() (*Config, error) {
	cfg := &Config{
		OpenAIAPIKey:           os.Getenv("OPENAI_API_KEY"),
		OpenAICoordinatorModel: os.Getenv("OPENAI_COORDINATOR_MODEL"),
		OpenAICollectorModel:   getEnvOrDefault("OPENAI_COLLECTOR_MODEL", "gpt-4o-mini"),
		WCCluster:              getEnvOrDefault("WC_CLUSTER", "workload cluster"),
		OrgNS:                  getEnvOrDefault("ORG_NS", "organization namespace"),
		Debug:                  isDebugEnabled(),
		OTELEndpoint:           getEnvOrDefault("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
		OTELInsecure:           getEnvOrDefault("OTEL_EXPORTER_OTLP_INSECURE", "false") == "true",
		ServerPort:             getEnvOrDefault("SERVER_PORT", "8000"),
	}

	// Validate required fields
	if cfg.OpenAIAPIKey == "" {
		return nil, fmt.Errorf("OPENAI_API_KEY environment variable is required")
	}
	if cfg.OpenAICoordinatorModel == "" {
		return nil, fmt.Errorf("OPENAI_COORDINATOR_MODEL environment variable is required")
	}

	return cfg, nil
}

// getEnvOrDefault returns the environment variable value or a default
func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

// isDebugEnabled checks if debug mode is enabled
func isDebugEnabled() bool {
	debug := strings.ToLower(os.Getenv("DEBUG"))
	return debug == "true" || debug == "1" || debug == "yes"
}
