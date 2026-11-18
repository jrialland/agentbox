import json
from pathlib import Path

from agentbox_api.app import create_app
from agentbox_api.config import Settings

app = create_app(Settings(jwt_secret="x" * 32))
out = Path(__file__).resolve().parent.parent / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
print(f"Wrote {out}")
