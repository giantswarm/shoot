package agents

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
	"google.golang.org/adk/agent"
	"google.golang.org/adk/agent/llmagent"
	"google.golang.org/adk/artifact"
	"google.golang.org/adk/runner"
	"google.golang.org/adk/session"
	"google.golang.org/adk/tool"
	"google.golang.org/adk/tool/mcptoolset"
	"google.golang.org/genai"

	"github.com/giantswarm/shoot/internal/config"
	adkmodel "github.com/giantswarm/shoot/internal/model"
)

// CollectorAgent wraps an ADK agent with runner for collector functionality
type CollectorAgent struct {
	runner      *runner.Runner
	agent       agent.Agent
	name        string
	userID      string
	sessionSvc  session.Service
	artifactSvc artifact.Service
}

// NewWCCollector creates a workload cluster collector using ADK
func NewWCCollector(ctx context.Context, cfg *config.Config) (*CollectorAgent, error) {
	// Load and substitute prompt template
	promptTemplate, err := os.ReadFile("prompts/wc_collector_prompt.md")
	if err != nil {
		return nil, fmt.Errorf("failed to read WC collector prompt: %w", err)
	}

	systemPrompt := substituteTemplate(string(promptTemplate), map[string]string{
		"WC_CLUSTER": cfg.WCCluster,
	})

	// Create OpenAI model adapter
	model, err := adkmodel.NewSimpleOpenAIModel(cfg.OpenAIAPIKey, cfg.OpenAICollectorModel)
	if err != nil {
		return nil, fmt.Errorf("failed to create OpenAI model: %w", err)
	}

	// Create MCP toolset for workload cluster
	mcpToolset, err := mcptoolset.New(mcptoolset.Config{
		Transport: &mcp.CommandTransport{
			Command: exec.Command("/usr/local/bin/mcp-kubernetes", "serve", "--non-destructive"),
		},
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create MCP toolset: %w", err)
	}

	// Create LLM agent with MCP tools
	llmAgent, err := llmagent.New(llmagent.Config{
		Name:        "wc_collector",
		Model:       model,
		Description: "Collects diagnostic data from the workload cluster via Kubernetes MCP server",
		Instruction: systemPrompt,
		Toolsets:    []tool.Toolset{mcpToolset},
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create agent: %w", err)
	}

	// Create session and artifact services
	sessionSvc := session.InMemoryService()
	artifactSvc := artifact.InMemoryService()

	// Create runner for the agent
	agentRunner, err := runner.New(runner.Config{
		Agent:           llmAgent,
		SessionService:  sessionSvc,
		ArtifactService: artifactSvc,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create runner: %w", err)
	}

	return &CollectorAgent{
		runner:      agentRunner,
		agent:       llmAgent,
		name:        "wc_collector",
		userID:      "system",
		sessionSvc:  sessionSvc,
		artifactSvc: artifactSvc,
	}, nil
}

// NewMCCollector creates a management cluster collector using ADK
func NewMCCollector(ctx context.Context, cfg *config.Config) (*CollectorAgent, error) {
	// Load and substitute prompt template
	promptTemplate, err := os.ReadFile("prompts/mc_collector_prompt.md")
	if err != nil {
		return nil, fmt.Errorf("failed to read MC collector prompt: %w", err)
	}

	systemPrompt := substituteTemplate(string(promptTemplate), map[string]string{
		"WC_CLUSTER": cfg.WCCluster,
		"ORG_NS":     cfg.OrgNS,
	})

	// Create OpenAI model adapter
	model, err := adkmodel.NewSimpleOpenAIModel(cfg.OpenAIAPIKey, cfg.OpenAICollectorModel)
	if err != nil {
		return nil, fmt.Errorf("failed to create OpenAI model: %w", err)
	}

	// Create MCP toolset for management cluster (in-cluster mode)
	mcpToolset, err := mcptoolset.New(mcptoolset.Config{
		Transport: &mcp.CommandTransport{
			Command: exec.Command("/usr/local/bin/mcp-kubernetes", "serve", "--non-destructive", "--in-cluster"),
		},
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create MCP toolset: %w", err)
	}

	// Create LLM agent with MCP tools
	llmAgent, err := llmagent.New(llmagent.Config{
		Name:        "mc_collector",
		Model:       model,
		Description: "Collects diagnostic data from the management cluster via Kubernetes MCP server",
		Instruction: systemPrompt,
		Toolsets:    []tool.Toolset{mcpToolset},
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create agent: %w", err)
	}

	// Create session and artifact services
	sessionSvc := session.InMemoryService()
	artifactSvc := artifact.InMemoryService()

	// Create runner for the agent
	agentRunner, err := runner.New(runner.Config{
		Agent:           llmAgent,
		SessionService:  sessionSvc,
		ArtifactService: artifactSvc,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create runner: %w", err)
	}

	return &CollectorAgent{
		runner:      agentRunner,
		agent:       llmAgent,
		name:        "mc_collector",
		userID:      "system",
		sessionSvc:  sessionSvc,
		artifactSvc: artifactSvc,
	}, nil
}

// Run executes the collector agent with a query using the runner
func (c *CollectorAgent) Run(ctx context.Context, query string, debug bool) (string, error) {
	// Create a session for this run
	sessionResp, err := c.sessionSvc.Create(ctx, &session.CreateRequest{
		AppName: "shoot",
		UserID:  c.userID,
	})
	if err != nil {
		return "", fmt.Errorf("failed to create session: %w", err)
	}

	// Create user message from query
	userMsg := genai.NewContentFromText(query, genai.RoleUser)

	// Run the agent via runner
	var finalOutput string
	var lastError error

	for event, err := range c.runner.Run(ctx, c.userID, sessionResp.Session.ID(), userMsg, agent.RunConfig{}) {
		if err != nil {
			lastError = err
			break
		}

		if debug {
			fmt.Printf("=== DEBUG: %s event ===\n", c.name)
			fmt.Printf("Event type: %T\n", event)
		}

		// Extract text from event content
		if event.Content != nil {
			for _, part := range event.Content.Parts {
				if part.Text != "" {
					if debug {
						fmt.Printf("Text: %s\n", part.Text)
					}
					finalOutput += part.Text
				}
			}
		}
	}

	if lastError != nil {
		return "", fmt.Errorf("agent execution failed: %w", lastError)
	}

	if debug {
		fmt.Printf("=== %s Final Output ===\n%s\n", c.name, finalOutput)
	}

	return finalOutput, nil
}

// substituteTemplate performs simple template substitution
func substituteTemplate(template string, vars map[string]string) string {
	result := template
	for key, value := range vars {
		placeholder := "${" + key + "}"
		result = strings.ReplaceAll(result, placeholder, value)
	}
	return result
}
