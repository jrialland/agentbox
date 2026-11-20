from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from agentbox_harness.session import Turn


def turns_to_messages(turns: list[Turn]) -> list[ModelMessage]:
    messages: list[ModelMessage] = []
    for turn in turns:
        if turn.role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=turn.content)]))
        elif turn.role == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=turn.content)]))
        elif turn.role == "summary":
            messages.append(
                ModelRequest(
                    parts=[
                        UserPromptPart(
                            content=(
                                "Earlier conversation summary:\n\n"
                                f"{turn.content}"
                            )
                        )
                    ]
                )
            )
    return messages
