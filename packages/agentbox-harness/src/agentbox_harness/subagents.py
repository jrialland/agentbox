from collections.abc import Callable

from pydantic_ai import Agent, RunContext


def build_subagent_tool(sub_agent: Agent) -> Callable:
    async def delegate(ctx: RunContext, task: str) -> str:
        result = await sub_agent.run(task, usage=ctx.usage)
        return str(result.output)

    delegate.__name__ = f"delegate_{sub_agent.name}"
    return delegate
