from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel
from sqlmodel.sql.sqltypes import UTCDateTime


def utcnow() -> datetime:
    return datetime.now(UTC)


class Provider(SQLModel, table=True):
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    kind: str = Field(sa_column=Column(String(64), nullable=False))
    base_url: str | None = Field(
        default=None, sa_column=Column(String(1024), nullable=True)
    )
    api_key: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    models_url: str | None = Field(
        default=None, sa_column=Column(String(1024), nullable=True)
    )
    is_builtin: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))


class Model(SQLModel, table=True):
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    provider_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("provider.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )
    name: str = Field(sa_column=Column(String(255), nullable=False))
    context_window: int | None = Field(
        default=None, sa_column=Column(Integer, nullable=True)
    )


class Label(SQLModel, table=True):
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    name: str = Field(sa_column=Column(String(128), nullable=False, unique=True))


class ModelLabelLink(SQLModel, table=True):
    model_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("model.id", ondelete="CASCADE"), primary_key=True
        )
    )
    label_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("label.id", ondelete="CASCADE"), primary_key=True
        )
    )
    priority: int = Field(default=0, sa_column=Column(Integer, nullable=False))


class MediaFile(SQLModel, table=True):
    __tablename__ = "media_file"
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    storage_path: str = Field(
        sa_column=Column(String(512), nullable=False, unique=True)
    )
    media_type: str = Field(sa_column=Column(String(255), nullable=False))
    size_bytes: int = Field(sa_column=Column(BigInteger, nullable=False))
    sha256: str = Field(sa_column=Column(String(64), nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class Agent(SQLModel, table=True):
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    name: str = Field(sa_column=Column(String(255), nullable=False, unique=True))
    description: str = Field(sa_column=Column(Text, nullable=False))
    instructions: str = Field(sa_column=Column(Text, nullable=False))
    model_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("model.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )
    model_label: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    avatar_file_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(32), ForeignKey("media_file.id", ondelete="SET NULL"), nullable=True
        ),
    )
    created_by: str | None = Field(
        default=None,
        sa_column=Column(
            String(32),
            ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class AgentToolBinding(SQLModel, table=True):
    __tablename__ = "agent_tool_binding"
    __table_args__ = (
        UniqueConstraint("agent_id", "position", name="uq_agent_tool_binding_pos"),
    )
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    agent_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    position: int = Field(sa_column=Column(Integer, nullable=False))
    kind: str = Field(sa_column=Column(String(16), nullable=False))
    name: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    server_url: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    tool_prefix: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    server_id: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    command: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    cwd: str | None = Field(default=None, sa_column=Column(Text, nullable=True))


class AgentToolBindingRequiredFlag(SQLModel, table=True):
    __tablename__ = "agent_tool_binding_required_flag"
    binding_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("agent_tool_binding.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    flag: str = Field(sa_column=Column(String(255), primary_key=True))


class AgentToolBindingArg(SQLModel, table=True):
    __tablename__ = "agent_tool_binding_arg"
    binding_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("agent_tool_binding.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    position: int = Field(sa_column=Column(Integer, primary_key=True))
    value: str = Field(sa_column=Column(Text, nullable=False))


class AgentToolBindingEnv(SQLModel, table=True):
    __tablename__ = "agent_tool_binding_env"
    binding_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("agent_tool_binding.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    key: str = Field(sa_column=Column(String(255), primary_key=True))
    value: str = Field(sa_column=Column(Text, nullable=False))


class AgentToolBindingEnvPassthrough(SQLModel, table=True):
    __tablename__ = "agent_tool_binding_env_passthrough"
    binding_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("agent_tool_binding.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    position: int = Field(sa_column=Column(Integer, primary_key=True))
    name: str = Field(sa_column=Column(String(255), nullable=False))


class AgentMode(SQLModel, table=True):
    __tablename__ = "agent_mode"
    __table_args__ = (
        UniqueConstraint("agent_id", "position", name="uq_agent_mode_pos"),
    )
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    agent_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    position: int = Field(sa_column=Column(Integer, nullable=False))
    name: str = Field(sa_column=Column(String(255), nullable=False))


class AgentModeFlag(SQLModel, table=True):
    __tablename__ = "agent_mode_flag"
    mode_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("agent_mode.id", ondelete="CASCADE"), primary_key=True
        )
    )
    name: str = Field(sa_column=Column(String(64), primary_key=True))
    enabled: bool = Field(sa_column=Column(Boolean, nullable=False))


class AgentCard(SQLModel, table=True):
    __tablename__ = "agent_card"
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    agent_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        )
    )
    file_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(32), ForeignKey("media_file.id", ondelete="SET NULL"), nullable=True
        ),
    )
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class Project(SQLModel, table=True):
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    path: str = Field(sa_column=Column(Text, nullable=False))
    owner_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("user.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class ProjectRoot(SQLModel, table=True):
    __tablename__ = "project_root"
    __table_args__ = (
        UniqueConstraint("project_id", "position", name="uq_project_root_pos"),
    )
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    project_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("project.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    position: int = Field(sa_column=Column(Integer, nullable=False))
    path: str = Field(sa_column=Column(Text, nullable=False))


class SessionRow(SQLModel, table=True):
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    project_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("project.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )
    agent_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("agent.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
    )
    title: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    parent_session_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(32),
            ForeignKey("sessionrow.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    subagent_session_status: str | None = Field(
        default=None, sa_column=Column(String(32), nullable=True)
    )
    subagent_session_error: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    subagent_session_output: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    subagent_session_depth: int = Field(
        default=0, sa_column=Column(Integer, nullable=False)
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class TurnRow(SQLModel, table=True):
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    session_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("sessionrow.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    role: str = Field(sa_column=Column(String(16), nullable=False))
    content: str = Field(sa_column=Column(Text, nullable=False))
    parent_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(32),
            ForeignKey("turnrow.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    context_tokens: int | None = Field(
        default=None, sa_column=Column(Integer, nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class TurnActivity(SQLModel, table=True):
    __tablename__ = "turn_activity"
    turn_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("turnrow.id", ondelete="CASCADE"), primary_key=True
        )
    )
    status: str = Field(sa_column=Column(String(32), nullable=False))
    reasoning_ms: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    reasoning_text: str = Field(
        default="", sa_column=Column(Text, nullable=False)
    )
    error_code: int | None = Field(
        default=None, sa_column=Column(Integer, nullable=True)
    )
    error_message: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )


class TurnToolActivity(SQLModel, table=True):
    __tablename__ = "turn_tool_activity"
    __table_args__ = (
        UniqueConstraint("turn_id", "position", name="uq_turn_tool_activity_pos"),
    )
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    turn_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("turnrow.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    position: int = Field(sa_column=Column(Integer, nullable=False))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    status: str = Field(sa_column=Column(String(32), nullable=False))
    duration_ms: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    args: str = Field(default="", sa_column=Column(Text, nullable=False))
    result: str = Field(default="", sa_column=Column(Text, nullable=False))


class SessionAttachment(SQLModel, table=True):
    __tablename__ = "session_attachment"
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    session_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("sessionrow.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    file_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("media_file.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    filename: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class TurnAttachment(SQLModel, table=True):
    __tablename__ = "turn_attachment"
    __table_args__ = (
        UniqueConstraint("turn_id", "position", name="uq_turn_attachment_pos"),
    )
    turn_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("turnrow.id", ondelete="CASCADE"), primary_key=True
        )
    )
    attachment_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("session_attachment.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    position: int = Field(sa_column=Column(Integer, nullable=False))


class PlanItem(SQLModel, table=True):
    id: str = Field(sa_column=Column(String(32), primary_key=True))
    session_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("sessionrow.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    position: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    content: str = Field(sa_column=Column(Text, nullable=False))
    status: str = Field(
        default="pending", sa_column=Column(String(32), nullable=False)
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
