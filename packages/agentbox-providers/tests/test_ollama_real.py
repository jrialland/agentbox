import httpx
import pytest
from pydantic_ai import Agent

from agentbox_models.tables.core import Provider
from agentbox_providers.resolver import resolve_model

OLLAMA_NATIVE_URL = "http://localhost:11434"
OLLAMA_OPENAI_URL = "http://localhost:11434/v1"
MODEL_NAME = "gemma4:e2b"


@pytest.fixture
async def ollama_model():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{OLLAMA_NATIVE_URL}/api/tags", timeout=2.0)
            r.raise_for_status()
            tags = r.json().get("models", [])
    except Exception:
        pytest.skip("Ollama not running")
    if MODEL_NAME not in [m["name"] for m in tags]:
        pytest.skip(f"Model {MODEL_NAME} not pulled in Ollama")
    return resolve_model(
        Provider(id="p", name="ollama", kind="ollama", base_url=OLLAMA_OPENAI_URL),
        MODEL_NAME,
    )


async def test_ollama_real_model_responds(ollama_model):
    agent = Agent(ollama_model)
    result = await agent.run("Reply with the single word: pong")
    assert result.output is not None
    assert "pong" in result.output.lower()
