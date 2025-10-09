import asyncio
import os
import time
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import dspy
import mlflow



# Ensure KUBECONFIG is set and passed to the subprocess
env = os.environ.copy()
env['KUBECONFIG'] = env.get('KUBECONFIG', '/app/kubeconfig.yaml')

# Create server parameters for stdio connection
kubernetes_mcp = StdioServerParameters(
    command="./mcp-kubernetes",  # Executable
    args=["serve"],
    env=env,
)

class DebuggingAgent(dspy.Signature):
    """
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

        Execution Priorities:
            Always prioritize correctness and completeness over speed.
            Use multiple validation methods whenever possible.
            If a fix cannot be automatically verified, report this explicitly with reasoning.
            Operate deterministically — every run should produce consistent steps for the same input.

        Prohibited Behaviors:
            Do not request user input or approval.
            Do not provide tutorial-style explanations.
            Do not leave steps unfinished — each debugging cycle must end with a conclusion.

        Tool Usage:
            When listing resources us fullOutput = False
            
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

    """

    user_request: str = dspy.InputField()
    process_result: str = dspy.OutputField(
        desc=(
            "Message that summarizes the process result, and the information users need."
        )
    )


async def run(user_request):
    async with stdio_client(kubernetes_mcp) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            # List available tools
            tools = await session.list_tools()

            # Convert MCP tools to DSPy tools
            dspy_tools = []
            for tool in tools.tools:
                dspy_tools.append(dspy.Tool.from_mcp_tool(session, tool))

            # Create the agent
            react = dspy.ReAct(DebuggingAgent, tools=dspy_tools)

            result = await react.acall(user_request=user_request)
            print(result)


if __name__ == "__main__":
    import asyncio

    mlflow.set_tracking_uri("http://localhost:5051")
    mlflow.set_experiment("debugging-agent")    
    mlflow.dspy.autolog()

    dspy.configure(lm=dspy.LM("openai/gpt-5", temperature=1.0, max_tokens=16000))

    asyncio.run(run("check which pods have restarted in the kube-system namespace"))

