package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"

	"github.com/firebase/genkit/go/ai"
	"github.com/firebase/genkit/go/genkit"
	"github.com/firebase/genkit/go/plugins/compat_oai/openai"
	"github.com/firebase/genkit/go/plugins/mcp"
)

// printPrettyJSON recursively prints JSON, parsing nested JSON strings
func printPrettyJSON(data any, indent string) {
	// First, marshal the data
	jsonBytes, err := json.MarshalIndent(data, indent, "  ")
	if err != nil {
		log.Printf("%s%v\n", indent, data)
		return
	}

	// Try to detect and parse nested JSON strings
	var parsed any
	if err := json.Unmarshal(jsonBytes, &parsed); err == nil {
		// Check if we have a map with nested JSON strings
		if m, ok := parsed.(map[string]any); ok {
			processNestedJSON(m)
			// Re-marshal with the processed nested JSON
			jsonBytes, _ = json.MarshalIndent(m, indent, "  ")
		}
	}

	log.Printf("%s\n", string(jsonBytes))
}

// processNestedJSON recursively processes maps and slices to parse JSON strings
func processNestedJSON(data any) {
	switch v := data.(type) {
	case map[string]any:
		for key, val := range v {
			switch strVal := val.(type) {
			case string:
				// Try to parse as JSON
				var parsed any
				if err := json.Unmarshal([]byte(strVal), &parsed); err == nil {
					// Check if it's a valid JSON object or array
					if _, isMap := parsed.(map[string]any); isMap {
						v[key] = parsed
						processNestedJSON(parsed)
					} else if _, isSlice := parsed.([]any); isSlice {
						v[key] = parsed
						processNestedJSON(parsed)
					}
				}
			default:
				processNestedJSON(val)
			}
		}
	case []any:
		for i, item := range v {
			switch strVal := item.(type) {
			case string:
				var parsed any
				if err := json.Unmarshal([]byte(strVal), &parsed); err == nil {
					if _, isMap := parsed.(map[string]any); isMap {
						v[i] = parsed
						processNestedJSON(parsed)
					} else if _, isSlice := parsed.([]any); isSlice {
						v[i] = parsed
						processNestedJSON(parsed)
					}
				}
			default:
				processNestedJSON(item)
			}
		}
	}
}

func main() {
	ctx := context.Background()

	// Check if debug mode is enabled
	debug := strings.ToLower(os.Getenv("DEBUG")) == "true"

	g := genkit.Init(ctx,
		genkit.WithPlugins(&openai.OpenAI{
			APIKey: os.Getenv("OPENAI_API_KEY"),
		}),
		genkit.WithDefaultModel("openai/gpt-5"),
		genkit.WithPromptDir("./prompts"),
	)

	kubernetesClient, err := mcp.NewGenkitMCPClient(mcp.MCPClientOptions{
		Name: "mcp-kubernetes",
		Stdio: &mcp.StdioConfig{
			Command: "./mcp-kubernetes",
			Args:    []string{"serve"},
			Env:     []string{fmt.Sprintf("KUBECONFIG=%s", os.Getenv("KUBECONFIG"))},
		},
	})
	if err != nil {
		log.Fatal(err)
	}

	tools, _ := kubernetesClient.GetActiveTools(ctx, g)
	var toolRefs []ai.ToolRef
	for _, tool := range tools {
		toolRefs = append(toolRefs, tool)
	}

	investigate := genkit.LookupPrompt(g, "investigate")

	resp, err := investigate.Execute(ctx, ai.WithTools(toolRefs...), ai.WithInput(map[string]any{"issue": "list namespaces in the cluster"}))
	if err != nil {
		log.Fatalf("could not generate model response: %v", err)
	}

	// Debug mode: print all tool calls and responses
	if debug {
		log.Println("\n========== DEBUG MODE: Tool Calls ==========")

		// Check if there are messages in the request (conversation history)
		if resp.Request != nil && len(resp.Request.Messages) > 0 {
			for i, msg := range resp.Request.Messages {

				// Look for tool requests in model messages
				if msg.Role == ai.RoleModel {
					for _, part := range msg.Content {
						if part.IsToolRequest() && part.ToolRequest != nil {
							log.Printf("\n[Message %d - Tool Request]\n", i+1)
							log.Printf("  Tool Name: %s\n", part.ToolRequest.Name)
							inputJSON, _ := json.MarshalIndent(part.ToolRequest.Input, "  ", "  ")
							log.Printf("  Input:\n%s\n", string(inputJSON))
						}
					}
				}

				// Look for tool responses in tool messages
				if msg.Role == ai.RoleTool {
					for _, part := range msg.Content {
						if part.IsToolResponse() && part.ToolResponse != nil {
							log.Printf("\n[Message %d - Tool Response]\n", i+1)
							log.Printf("  Tool Name: %s\n", part.ToolResponse.Name)
							log.Printf("  Output:\n")
							printPrettyJSON(part.ToolResponse.Output, "  ")
						}
					}
				}
			}
		}

		// Also check the final response message
		if resp.Message != nil && len(resp.Message.Content) > 0 {
			for _, part := range resp.Message.Content {
				if part.IsReasoning() {
					log.Printf("\n[Final Response - AI Reasoning/Thoughts]\n")
					log.Printf("  %s\n", part.Text)
				}
				if part.IsToolRequest() && part.ToolRequest != nil {
					log.Printf("\n[Final Response - Tool Request]\n")
					log.Printf("  Tool Name: %s\n", part.ToolRequest.Name)
					inputJSON, _ := json.MarshalIndent(part.ToolRequest.Input, "  ", "  ")
					log.Printf("  Input:\n%s\n", string(inputJSON))
				}
			}
		}

		log.Println("========== END DEBUG ==========")
	}

	log.Println(resp.Text())
}
