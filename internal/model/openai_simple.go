package model

import (
	"context"
	"encoding/json"
	"fmt"
	"iter"

	"github.com/openai/openai-go"
	"github.com/openai/openai-go/option"
	"github.com/openai/openai-go/shared"
	"google.golang.org/adk/model"
	"google.golang.org/genai"
)

// SimpleOpenAIModel implements ADK's model.LLM interface for OpenAI models
// This is a simplified version that handles basic text-based interactions
type SimpleOpenAIModel struct {
	client *openai.Client
	model  string
}

// NewSimpleOpenAIModel creates a new simplified OpenAI model adapter for ADK
func NewSimpleOpenAIModel(apiKey string, modelName string) (*SimpleOpenAIModel, error) {
	if apiKey == "" {
		return nil, fmt.Errorf("OpenAI API key is required")
	}
	if modelName == "" {
		return nil, fmt.Errorf("model name is required")
	}

	client := openai.NewClient(option.WithAPIKey(apiKey))

	return &SimpleOpenAIModel{
		client: &client,
		model:  modelName,
	}, nil
}

// Name returns the model name
func (m *SimpleOpenAIModel) Name() string {
	return m.model
}

// GenerateContent implements the LLM interface with simplified type conversion
func (m *SimpleOpenAIModel) GenerateContent(ctx context.Context, req *model.LLMRequest, stream bool) iter.Seq2[*model.LLMResponse, error] {
	// Convert ADK request to OpenAI format (simplified)
	messages, err := simpleConvertToOpenAIMessages(req.Contents)
	if err != nil {
		return func(yield func(*model.LLMResponse, error) bool) {
			yield(nil, fmt.Errorf("failed to convert messages: %w", err))
		}
	}

	// Convert tools if present
	var tools []openai.ChatCompletionToolParam
	if req.Config != nil && len(req.Config.Tools) > 0 {
		tools = simpleConvertToOpenAITools(req.Config.Tools)
	}

	// Build OpenAI request
	params := openai.ChatCompletionNewParams{
		Model:    shared.ChatModel(m.model),
		Messages: messages,
	}

	if len(tools) > 0 {
		params.Tools = tools
	}

	// Apply additional config if present
	if req.Config != nil {
		if req.Config.Temperature != nil {
			params.Temperature = openai.Float(float64(*req.Config.Temperature))
		}
		if req.Config.MaxOutputTokens != 0 {
			params.MaxCompletionTokens = openai.Int(int64(req.Config.MaxOutputTokens))
		}
	}

	// Return a sequence with a single response (non-streaming)
	return func(yield func(*model.LLMResponse, error) bool) {
		resp, err := m.client.Chat.Completions.New(ctx, params)
		if err != nil {
			yield(nil, fmt.Errorf("OpenAI API error: %w", err))
			return
		}

		if len(resp.Choices) == 0 {
			yield(nil, fmt.Errorf("no choices in response"))
			return
		}

		// Convert OpenAI response to ADK format
		adkResponse, err := simpleConvertFromOpenAIResponse(&resp.Choices[0])
		if err != nil {
			yield(nil, fmt.Errorf("failed to convert response: %w", err))
			return
		}

		// Add usage metadata
		adkResponse.UsageMetadata = &genai.GenerateContentResponseUsageMetadata{
			PromptTokenCount:     int32(resp.Usage.PromptTokens),
			CandidatesTokenCount: int32(resp.Usage.CompletionTokens),
			TotalTokenCount:      int32(resp.Usage.TotalTokens),
		}

		yield(adkResponse, nil)
	}
}

// simpleConvertToOpenAIMessages converts ADK genai.Content to OpenAI messages (simplified)
func simpleConvertToOpenAIMessages(contents []*genai.Content) ([]openai.ChatCompletionMessageParamUnion, error) {
	messages := make([]openai.ChatCompletionMessageParamUnion, 0, len(contents))

	for _, content := range contents {
		// Extract text from parts
		var text string
		for _, part := range content.Parts {
			if part.Text != "" {
				text += part.Text
			}
			// Handle function responses
			if part.FunctionResponse != nil {
				resultJSON, _ := json.Marshal(part.FunctionResponse.Response)
				// For function responses, we need the function call ID which we don't have
				// For now, add as user message with the result
				messages = append(messages, openai.UserMessage(fmt.Sprintf("Function %s returned: %s",
					part.FunctionResponse.Name, string(resultJSON))))
				continue
			}
		}

		// Convert based on role
		switch content.Role {
		case genai.RoleUser:
			messages = append(messages, openai.UserMessage(text))
		case genai.RoleModel:
			messages = append(messages, openai.AssistantMessage(text))
		case "system":
			messages = append(messages, openai.SystemMessage(text))
		default:
			// For unknown roles, treat as user
			if text != "" {
				messages = append(messages, openai.UserMessage(text))
			}
		}
	}

	return messages, nil
}

// simpleConvertToOpenAITools converts ADK tools to OpenAI format
func simpleConvertToOpenAITools(tools []*genai.Tool) []openai.ChatCompletionToolParam {
	openAITools := make([]openai.ChatCompletionToolParam, 0)

	for _, tool := range tools {
		if tool.FunctionDeclarations == nil {
			continue
		}

		for _, fn := range tool.FunctionDeclarations {
			// Convert Schema to map
			var params map[string]interface{}
			if fn.Parameters != nil {
				schemaJSON, _ := json.Marshal(fn.Parameters)
				json.Unmarshal(schemaJSON, &params)
			} else {
				params = map[string]interface{}{}
			}

			openAITools = append(openAITools, openai.ChatCompletionToolParam{
				Function: shared.FunctionDefinitionParam{
					Name:        fn.Name,
					Description: openai.String(fn.Description),
					Parameters:  shared.FunctionParameters(params),
				},
			})
		}
	}

	return openAITools
}

// simpleConvertFromOpenAIResponse converts OpenAI response to ADK format
func simpleConvertFromOpenAIResponse(choice *openai.ChatCompletionChoice) (*model.LLMResponse, error) {
	parts := make([]*genai.Part, 0)

	// Add text content if present
	if choice.Message.Content != "" {
		parts = append(parts, &genai.Part{
			Text: choice.Message.Content,
		})
	}

	// Add function calls if present
	for _, toolCall := range choice.Message.ToolCalls {
		var args map[string]interface{}
		if err := json.Unmarshal([]byte(toolCall.Function.Arguments), &args); err != nil {
			return nil, fmt.Errorf("failed to parse tool arguments: %w", err)
		}

		parts = append(parts, &genai.Part{
			FunctionCall: &genai.FunctionCall{
				Name: toolCall.Function.Name,
				Args: args,
			},
		})
	}

	content := &genai.Content{
		Role:  genai.RoleModel,
		Parts: parts,
	}

	// Convert finish reason
	var finishReason genai.FinishReason
	switch string(choice.FinishReason) {
	case "stop":
		finishReason = genai.FinishReasonStop
	case "length":
		finishReason = genai.FinishReasonMaxTokens
	case "tool_calls":
		finishReason = genai.FinishReasonStop
	case "content_filter":
		finishReason = genai.FinishReasonSafety
	default:
		finishReason = genai.FinishReasonOther
	}

	return &model.LLMResponse{
		Content:      content,
		TurnComplete: true,
		FinishReason: finishReason,
	}, nil
}
