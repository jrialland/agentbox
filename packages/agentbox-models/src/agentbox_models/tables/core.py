from datetime import UTC, datetime

from sqlalchemy import JSON, Column, LargeBinary
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
    context_window: int | None = None


class Label(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str = Field(index=True, unique=True)


class ModelLabelLink(SQLModel, table=True):
    model_id: str = Field(foreign_key="model.id", primary_key=True)
    label_id: str = Field(foreign_key="label.id", primary_key=True)
    priority: int = 0


class Agent(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    instructions: str
    model_id: str = Field(foreign_key="model.id")
    model_label: str | None = None
    tool_bindings: str = "[]"
    mode_definitions: str = "[]"
    sub_agent_ids: str = "[]"
    avatar_url: str | None = None
    avatar_data: bytes | None = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    avatar_media_type: str | None = None
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
    extra_roots: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default="[]"),
    )
    created_at: datetime = Field(default_factory=utcnow)


class SessionRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id")
    agent_id: str = Field(foreign_key="agent.id")
    title: str | None = None
    head_turn_id: str | None = None
    parent_session_id: str | None = Field(
        default=None, foreign_key="sessionrow.id", index=True
    )
    sub_session_status: str | None = None
    sub_session_error: str | None = None
    sub_session_output: str | None = None
    sub_session_depth: int = 0
    created_at: datetime = Field(default_factory=utcnow)


class PlanItem(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="sessionrow.id", index=True)
    position: int = 0
    content: str
    status: str = "pending"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class TurnRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="sessionrow.id")
    role: str
    content: str
    parent_id: str | None = None
    context_tokens: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    activity: dict | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    attachments: list[dict] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )


class SessionAttachment(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="sessionrow.id")
    media_type: str
    filename: str
    data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    created_at: datetime = Field(default_factory=utcnow)
