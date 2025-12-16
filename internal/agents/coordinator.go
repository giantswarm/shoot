package agents

import (
	"context"
	"fmt"
	"os"

	"google.golang.org/adk/agent"
	"google.golang.org/adk/agent/llmagent"
	"google.golang.org/adk/artifact"
	"google.golang.org/adk/runner"
	"google.golang.org/adk/session"
	"google.golang.org/adk/tool"
	"google.golang.org/adk/tool/functiontool"
	"google.golang.org/genai"

	"github.com/giantswarm/shoot/internal/config"
	adkmodel "github.com/giantswarm/shoot/internal/model"
)

// CollectorArgs defines the input arguments for collector tools
type CollectorArgs struct {
	Query string `json:"query" jsonschema:"description=The specific investigation query or data collection request"`
}

// CollectorResult defines the output of collector tools
type CollectorResult struct {
	Result string `json:"result" jsonschema:"description=The collected data and findings from the cluster"`
}

// Coordinator wraps an ADK agent with runner for coordinator functionality
type Coordinator struct {
	runner      *runner.Runner
	agent       agent.Agent
	wcCollector *CollectorAgent
	mcCollector *CollectorAgent
	userID      string
	sessionSvc  session.Service
	artifactSvc artifact.Service
	debug       bool
}

// NewCoordinator creates a coordinator agent using ADK
func NewCoordinator(ctx context.Context, cfg *config.Config, wcCollector, mcCollector *CollectorAgent) (*Coordinator, error) {
	// Load and substitute prompt template
	promptTemplate, err := os.ReadFile("prompts/coordinator_prompt.md")
	if err != nil {
		return nil, fmt.Errorf("failed to read coordinator prompt: %w", err)
	}

	systemPrompt := substituteTemplate(string(promptTemplate), map[string]string{
		"WC_CLUSTER": cfg.WCCluster,
		"ORG_NS":     cfg.OrgNS,
	})

	// Create OpenAI model adapter
	model, err := adkmodel.NewSimpleOpenAIModel(cfg.OpenAIAPIKey, cfg.OpenAICoordinatorModel)
	if err != nil {
		return nil, fmt.Errorf("failed to create OpenAI model: %w", err)
	}

	coordinator := &Coordinator{
		wcCollector: wcCollector,
		mcCollector: mcCollector,
		userID:      "system",
		debug:       cfg.Debug,
	}

	// Create function tools for collector agents
	collectWCTool, err := functiontool.New(functiontool.Config{
		Name:        "collect_wc_data",
		Description: "Collect data from the workload cluster. Use this to gather runtime information about pods, deployments, services, nodes, and other Kubernetes resources in the workload cluster.",
	}, func(ctx tool.Context, args CollectorArgs) (CollectorResult, error) {
		if coordinator.debug {
			fmt.Printf("=== Calling WC Collector ===\n")
			fmt.Printf("Query: %s\n", args.Query)
		}

		result, err := coordinator.wcCollector.Run(ctx, args.Query, coordinator.debug)
		if err != nil {
			return CollectorResult{}, fmt.Errorf("WC collector failed: %w", err)
		}

		if coordinator.debug {
			fmt.Printf("=== WC Collector Result ===\n%s\n", result)
		}

		return CollectorResult{Result: result}, nil
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create WC collector tool: %w", err)
	}

	collectMCTool, err := functiontool.New(functiontool.Config{
		Name:        "collect_mc_data",
		Description: "Collect data from the management cluster. Use this to check App, HelmRelease, and CAPI/CAPA resources related to the workload cluster deployment.",
	}, func(ctx tool.Context, args CollectorArgs) (CollectorResult, error) {
		if coordinator.debug {
			fmt.Printf("=== Calling MC Collector ===\n")
			fmt.Printf("Query: %s\n", args.Query)
		}

		result, err := coordinator.mcCollector.Run(ctx, args.Query, coordinator.debug)
		if err != nil {
			return CollectorResult{}, fmt.Errorf("MC collector failed: %w", err)
		}

		if coordinator.debug {
			fmt.Printf("=== MC Collector Result ===\n%s\n", result)
		}

		return CollectorResult{Result: result}, nil
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create MC collector tool: %w", err)
	}

	// Create a simple toolset that wraps both tools
	collectorToolset := &simpleToolset{
		name:        "collector_tools",
		description: "Tools to collect data from workload and management clusters",
		tools:       []tool.Tool{collectWCTool, collectMCTool},
	}

	// Create coordinator agent
	llmAgent, err := llmagent.New(llmagent.Config{
		Name:        "coordinator",
		Model:       model,
		Description: "Orchestrates Kubernetes cluster investigation by coordinating data collection from workload and management clusters",
		Instruction: systemPrompt,
		Toolsets:    []tool.Toolset{collectorToolset},
	})
	if err != nil {
		return nil, fmt.Errorf("failed to create coordinator agent: %w", err)
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

	coordinator.runner = agentRunner
	coordinator.agent = llmAgent
	coordinator.sessionSvc = sessionSvc
	coordinator.artifactSvc = artifactSvc

	return coordinator, nil
}

// Run executes the coordinator agent with a user query using the runner
func (c *Coordinator) Run(ctx context.Context, query string) (string, error) {
	if c.debug {
		fmt.Printf("=== Coordinator Running ===\n")
		fmt.Printf("Query: %s\n", query)
	}

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

		if c.debug {
			fmt.Printf("=== DEBUG: Coordinator event ===\n")
			fmt.Printf("Event type: %T\n", event)
		}

		// Extract text from event content
		if event.Content != nil {
			for _, part := range event.Content.Parts {
				if part.Text != "" {
					if c.debug {
						fmt.Printf("Text: %s\n", part.Text)
					}
					finalOutput += part.Text
				}
			}
		}
	}

	if lastError != nil {
		return "", fmt.Errorf("coordinator execution failed: %w", lastError)
	}

	if c.debug {
		fmt.Printf("=== Coordinator Final Output ===\n%s\n", finalOutput)
	}

	return finalOutput, nil
}

// simpleToolset is a basic implementation of tool.Toolset
type simpleToolset struct {
	name        string
	description string
	tools       []tool.Tool
}

func (s *simpleToolset) Name() string {
	return s.name
}

func (s *simpleToolset) Tools(ctx agent.ReadonlyContext) ([]tool.Tool, error) {
	return s.tools, nil
}
