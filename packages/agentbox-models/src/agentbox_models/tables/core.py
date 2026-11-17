from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Provider(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    kind: str
    base_url: str | None = None
    api_key: str | None = None
    models_url: str | None = None
    is_builtin: bool = False


class Model(SQLModel, table=True):
    id: str = Field(primary_key=True)
    provider_id: str = Field(foreign_key="provider.id")
    name: str


class Agent(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    instructions: str
    model_id: str = Field(foreign_key="model.id")
    tool_bindings: str = "[]"
    mode_definitions: str = "[]"
    sub_agent_ids: str = "[]"
    avatar_url: str | None = None
    created_by: str | None = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)


class AgentCard(SQLModel, table=True):
    id: str = Field(primary_key=True)
    agent_id: str = Field(foreign_key="agent.id")
    card: str


class Project(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    path: str
    owner_id: str = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)


class SessionRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id")
    agent_id: str = Field(foreign_key="agent.id")
    head_turn_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class TurnRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="sessionrow.id")
    role: str
    content: str
    parent_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
