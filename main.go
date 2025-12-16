package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"

	"github.com/giantswarm/shoot/internal/agents"
	"github.com/giantswarm/shoot/internal/config"
	"github.com/giantswarm/shoot/internal/server"
)

func main() {
	ctx := context.Background()

	// Load configuration
	cfg, err := config.LoadConfig()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Initialize OpenTelemetry
	shutdown, err := initOTEL(ctx, cfg)
	if err != nil {
		log.Printf("Warning: Failed to initialize OpenTelemetry: %v", err)
		// Continue without OTEL rather than failing
	} else {
		defer func() {
			if err := shutdown(ctx); err != nil {
				log.Printf("Error shutting down OTEL: %v", err)
			}
		}()
	}

	// Create collector agents
	log.Println("Initializing workload cluster collector...")
	wcCollector, err := agents.NewWCCollector(ctx, cfg)
	if err != nil {
		log.Fatalf("Failed to create WC collector: %v", err)
	}

	log.Println("Initializing management cluster collector...")
	mcCollector, err := agents.NewMCCollector(ctx, cfg)
	if err != nil {
		log.Fatalf("Failed to create MC collector: %v", err)
	}

	// Create coordinator agent
	log.Println("Initializing coordinator agent...")
	coordinator, err := agents.NewCoordinator(ctx, cfg, wcCollector, mcCollector)
	if err != nil {
		log.Fatalf("Failed to create coordinator: %v", err)
	}

	// Create HTTP server
	srv := server.NewServer(coordinator, wcCollector, mcCollector, cfg)
	handler := srv.SetupRoutes()

	// Start HTTP server
	httpServer := &http.Server{
		Addr:    ":" + cfg.ServerPort,
		Handler: handler,
	}

	// Handle graceful shutdown
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)
		<-sigChan

		log.Println("Shutting down server...")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()

		if err := httpServer.Shutdown(shutdownCtx); err != nil {
			log.Printf("Error during server shutdown: %v", err)
		}
	}()

	log.Printf("Starting server on port %s...", cfg.ServerPort)
	log.Printf("Using OpenAI models: coordinator=%s, collectors=%s",
		cfg.OpenAICoordinatorModel, cfg.OpenAICollectorModel)

	if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("Server failed: %v", err)
	}

	log.Println("Server stopped")
}

// initOTEL initializes OpenTelemetry tracing
func initOTEL(ctx context.Context, cfg *config.Config) (func(context.Context) error, error) {
	if cfg.OTELEndpoint == "" {
		return func(ctx context.Context) error { return nil }, nil
	}

	// Create OTLP HTTP exporter
	opts := []otlptracehttp.Option{
		otlptracehttp.WithEndpoint(cfg.OTELEndpoint),
	}
	if cfg.OTELInsecure {
		opts = append(opts, otlptracehttp.WithInsecure())
	}

	exporter, err := otlptracehttp.New(ctx, opts...)
	if err != nil {
		return nil, fmt.Errorf("failed to create OTLP exporter: %w", err)
	}

	// Create resource
	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String("shoot-agent"),
			semconv.ServiceVersionKey.String("1.0.0"),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("failed to create resource: %w", err)
	}

	// Create tracer provider
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
	)

	otel.SetTracerProvider(tp)

	return tp.Shutdown, nil
}
