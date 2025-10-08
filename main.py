import asyncio
import os
import time
import json
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings

# Ensure KUBECONFIG is set and passed to the subprocess
env = os.environ.copy()
env['KUBECONFIG'] = env.get('KUBECONFIG', '/app/kubeconfig.yaml')

kubernetes_server = MCPServerStdio('/usr/local/bin/mcp-kubernetes', args=['serve'], env=env)

model = OpenAIResponsesModel('gpt-5')
settings = OpenAIResponsesModelSettings(
    openai_reasoning_effort='high',
    openai_reasoning_summary='detailed',
)
agent = Agent(
    model, 
    model_settings=settings, 
    toolsets=[kubernetes_server],
    system_prompt=(
        """
            Role:
            You are an autonomous AI debugging agent. Your purpose is to debug and investigate issues directly, using your available tools, without asking the user for guidance or clarification. You should fully execute any necessary diagnostics, analyses, or tests yourself.

            🧠 Core Behavior:

            Autonomous Execution:

            You must independently execute all debugging and diagnostic steps using your available tools and environment.

            Do not ask the user for input or clarification at any stage.

            When information is missing or ambiguous, infer reasonable assumptions and clearly state them before acting.

            Full Investigation Coverage:

            If there are multiple viable debugging strategies or tools for the given problem, apply all of them.

            Capture outputs, logs, or results from each method.

            Analyze the consistency or divergence between them.

            Summarize findings clearly and concisely.

            Direct Problem Solving:

            Your goal is to diagnose the issue, not to suggest steps to the user.


            Result Reporting Format:

            🧩 Context:
            [Brief summary of the issue, assumptions made, and initial diagnostic plan.]

            🔧 Method 1 – [Tool/Approach Used]:
            [Execution summary + results.]

            🔧 Method 2 – [Tool/Approach Used]:
            [Execution summary + results.]

            ⚖️ Comparison (if more than one method is used):
            [Whether findings agree or differ, with brief explanation.]

            📊 Summary:
            [Concise technical conclusion including any remaining uncertainties or follow-up recommendations (if needed).]


            Execution Priorities:

            Always prioritize correctness and completeness over speed.

            Use multiple validation methods whenever possible.

            If a fix cannot be automatically verified, report this explicitly with reasoning.

            Operate deterministically — every run should produce consistent steps for the same input.

            Prohibited Behaviors:

            Do not request user input or approval.

            Do not provide tutorial-style explanations.

            Do not leave steps unfinished — each debugging cycle must end with a conclusion.

            🧩 Goal Summary

            Your ultimate objective is to autonomously detect, analyze, and fix issues using all available debugging tools, summarize your findings, and ensure the problem is verified as resolved — all without user intervention.
        """
    ),
)


def debug_print(message):
    print("🧠 Agent's Thought Process & Actions:")
    print("=" * 80)
    messages = result.all_messages()
    thought_count = 0
    tool_call_count = 0
    tool_response_count = 0
    
    for msg in messages:
        # Check if this is a ModelResponse with parts
        if hasattr(msg, 'parts'):
            for part in msg.parts:
                # Look for ThinkingPart objects
                if type(part).__name__ == 'ThinkingPart':
                    content = getattr(part, 'content', '')
                    if content and content.strip():  # Only print non-empty thoughts
                        thought_count += 1
                        print(f"\n[Thought {thought_count}]")
                        print(content)
                        print("-" * 80)
                
                # Look for ToolCallPart objects
                elif type(part).__name__ == 'ToolCallPart':
                    tool_call_count += 1
                    tool_name = getattr(part, 'tool_name', 'unknown')
                    args = getattr(part, 'args', '{}')
                    print(f"\n🔧 [Tool Call {tool_call_count}]")
                    print(f"Tool: {tool_name}")
                    print("Arguments:")
                    try:
                        # Try to parse and pretty-print JSON args
                        args_dict = json.loads(args)
                        print(json.dumps(args_dict, indent=2))
                    except:
                        # If not valid JSON, just print as-is
                        print(args)
                    print("-" * 80)
                
                # Look for ToolReturnPart objects
                elif type(part).__name__ == 'ToolReturnPart':
                    tool_response_count += 1
                    tool_name = getattr(part, 'tool_name', 'unknown')
                    content = getattr(part, 'content', None)
                    print(f"\n📦 [Tool Response {tool_response_count}]")
                    print(f"Tool: {tool_name}")
                    print("Response:")
                    if content is not None:
                        try:
                            # Try to pretty-print if it's a dict or JSON-serializable
                            if isinstance(content, (dict, list)):
                                print(json.dumps(content, indent=2))
                            else:
                                print(json.dumps(json.loads(str(content)), indent=2))
                        except:
                            # If not valid JSON, just print as-is
                            print(content)
                    else:
                        print("(empty response)")
                    print("-" * 80)
    
    print("\n")

async def main():
    start_time = time.time()
    result = await agent.run('investigate why pods have restarted on kube-system namespace')
    elapsed_time = time.time() - start_time
    
    # Check if DEBUG mode is enabled
    debug_mode = os.getenv('DEBUG', '').lower() == 'true'
    
    if debug_mode:
        debug_print(result)
        print("\n" * 10)
    
    # Print the final response
    print("✅ Final Response:")
    print("=" * 80)
    print(result.output)
    
    print(f"\n⏱️  Time taken: {elapsed_time:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())
