"""Core domain tables for providers, models, Agents, Projects, and Sessions.

The schema models the agentbox hierarchy: a ``Provider`` exposes ``Model`` rows,
an ``Agent`` configuration binds a model plus tools and modes, a ``Project``
groups work, and a ``SessionRow`` runs an Agent configuration inside a Project.
``TurnRow`` and the attachment/activity tables persist conversation state.

Foreign keys use ``RESTRICT`` when deleting the referenced row would orphan live
configuration or history, ``CASCADE`` for rows wholly owned by a parent, and
``SET NULL`` for optional references. Timestamps are stored as timezone-aware
UTC values.
"""

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
    """Return the current time as a timezone-aware UTC datetime.

    Columns use ``UTCDateTime``, which binds values as UTC and re-attaches the
    UTC offset on read when a backend returns a naive datetime (SQLite and MySQL
    lack a native timezone-aware type), keeping timestamps comparable.
    """
    return datetime.now(UTC)


class Provider(SQLModel, table=True):
    """A model provider endpoint, either built in or user configured.

    Attributes:
        base_url: Optional API base URL override.
        api_key: Optional credential stored on the row. The stored value is
            preferred; the ``{PROVIDER_NAME}_API_KEY`` environment variable is
            only used as a fallback when no row value is set.
        models_url: Optional discovery endpoint for listing models.
        is_builtin: Marks providers seeded or managed by the application rather
            than created by a user.
    """

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
    """A model offered by a provider.

    Attributes:
        provider_id: Owning provider. ``RESTRICT`` blocks deleting a provider
            that still has models.
        context_window: Optional context size in tokens, when known.
    """

    id: str = Field(sa_column=Column(String(32), primary_key=True))
    # RESTRICT keeps provider rows from being deleted while their models exist;
    # the index supports provider-scoped model lookups.
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
    """A reusable label used to rank and select models.

    ``name`` is unique and length-limited so the unique index stays within
    MySQL/InnoDB key limits across supported vendors.
    """

    id: str = Field(sa_column=Column(String(32), primary_key=True))
    name: str = Field(sa_column=Column(String(128), nullable=False, unique=True))


class ModelLabelLink(SQLModel, table=True):
    """Association row attaching a label to a model.

    Attributes:
        priority: Ordering hint used by label resolution; lower values win and
            the default is ``0``.
    """

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
    """A stored media file and its integrity metadata.

    Attributes:
        storage_path: Path under the configured media directory; unique so one
            file is stored once. The length is bounded for cross-vendor index
            limits.
        size_bytes: Size in bytes; ``BigInteger`` avoids 32-bit overflow on
            server databases while SQLite stores it as a 64-bit integer.
        sha256: Hex-encoded content digest used for integrity checks and as an
            ETag.
    """

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
    """An Agent configuration: a model, instructions, tools, and modes.

    Attributes:
        model_id: Model backing the Agent; ``RESTRICT`` prevents deleting a
            model still referenced by an Agent.
        model_label: Optional denormalized label used for display and to
            re-resolve the model on load.
        avatar_file_id: Optional avatar media; ``SET NULL`` detaches it when the
            file is removed.
        created_by: Optional owning user; ``SET NULL`` preserves the Agent when
            the user is deleted.
    """

    id: str = Field(sa_column=Column(String(32), primary_key=True))
    name: str = Field(sa_column=Column(String(255), nullable=False, unique=True))
    description: str = Field(sa_column=Column(Text, nullable=False))
    instructions: str = Field(sa_column=Column(Text, nullable=False))
    # RESTRICT stops model deletion while Agents still reference it; the index
    # supports "Agents using this model" queries.
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
    # SET NULL keeps the Agent row when its avatar media is deleted.
    avatar_file_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(32), ForeignKey("media_file.id", ondelete="SET NULL"), nullable=True
        ),
    )
    # SET NULL preserves the Agent if the creating user is deleted; the index
    # supports owner-scoped listings.
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
    """A configured tool binding for an Agent.

    Attributes:
        kind: Discriminator for the binding type; only the fields relevant to
            that kind are populated.
        position: Display/execution order; unique per Agent via a constraint.
    """

    __tablename__ = "agent_tool_binding"
    # Enforce a single binding per position so tool ordering is deterministic.
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
    """A required flag for an Agent tool binding."""

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
    """A positional argument passed to an Agent tool binding."""

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
    """An environment variable set for an Agent tool binding."""

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
    """An environment variable name forwarded unchanged to an Agent tool binding."""

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
    """A named operating mode configured for an Agent.

    Attributes:
        position: Mode ordering; unique per Agent via a constraint.
    """

    __tablename__ = "agent_mode"
    # Keep mode ordering deterministic by disallowing duplicate positions.
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
    """A boolean flag that enables behavior within an Agent mode."""

    __tablename__ = "agent_mode_flag"
    mode_id: str = Field(
        sa_column=Column(
            String(32), ForeignKey("agent_mode.id", ondelete="CASCADE"), primary_key=True
        )
    )
    name: str = Field(sa_column=Column(String(64), primary_key=True))
    enabled: bool = Field(sa_column=Column(Boolean, nullable=False))


class AgentCard(SQLModel, table=True):
    """A cached Agent card document for A2A discovery.

    Attributes:
        agent_id: One-to-one link to the Agent; unique and cascade-deleted with
            it.
        file_id: Optional media file holding the card; ``SET NULL`` keeps the
            card row when the file is removed.
    """

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
    """A workspace grouping Sessions and their files.

    Attributes:
        owner_id: User that owns the Project. ``RESTRICT`` prevents deleting a
            user while their Projects still exist.
    """

    id: str = Field(sa_column=Column(String(32), primary_key=True))
    name: str = Field(sa_column=Column(String(255), nullable=False))
    path: str = Field(sa_column=Column(Text, nullable=False))
    # RESTRICT protects Sessions and history by blocking deletion of an owner
    # who still has Projects; the index supports owner-scoped lookups.
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
    """An additional filesystem root attached to a Project.

    Attributes:
        position: Ordering for extra roots; unique per Project via a constraint.
    """

    __tablename__ = "project_root"
    # Disallow duplicate positions so extra-root ordering is deterministic.
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
    """A live Agent session within a Project.

    A Session runs an Agent configuration and owns its Turns, attachments, plan
    items, and any child subagent sessions.

    Attributes:
        project_id: Owning Project. ``RESTRICT`` keeps Session history from being
            orphaned by deleting its Project.
        agent_id: Agent configuration used by the Session. ``RESTRICT`` prevents
            deleting a configuration that still has sessions.
        parent_session_id: Parent Session when this is a subagent session;
            cascade-deleted with the parent.
        subagent_session_status: Status metadata recorded when this Session runs
            as a subagent session; ``None`` for ordinary sessions.
        subagent_session_output: Optional captured output for a completed
            subagent session.
        subagent_session_depth: Nesting depth, ``0`` for a root Session.
    """

    id: str = Field(sa_column=Column(String(32), primary_key=True))
    # RESTRICT keeps Session history while its Project or Agent configuration
    # still exists; indexes support per-project and per-agent listings.
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
    # A subagent session is owned by its parent, so deleting the parent cascades
    # to children; the self-reference is indexed for child lookups.
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
    """A single user, assistant, or tool turn within a Session.

    Attributes:
        session_id: Session that owns the turn; cascade-deleted with it.
        parent_id: Optional parent turn for branching history; cascade deletes
            the subtree.
        context_tokens: Optional prompt-context token count recorded for the
            turn.
    """

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
    # Branching history: deleting a turn also removes its descendants; the index
    # supports child lookup.
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
    """Reasoning and error details recorded for a Turn.

    Attributes:
        reasoning_ms: Accumulated reasoning time in milliseconds.
        error_code: Optional generic error code paired with ``error_message``
            when the turn failed.
        error_message: Optional human-readable failure detail.
    """

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
    """A record of one tool invocation within a Turn.

    Attributes:
        position: Order of invocation within the turn; unique per turn via a
            constraint.
        duration_ms: Wall-clock tool duration in milliseconds.
        args: Serialized tool arguments.
        result: Serialized tool result.
    """

    __tablename__ = "turn_tool_activity"
    # Preserve a stable tool-call order within a turn.
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
    """A media file attached to a Session and available to its turns."""

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
    # CASCADE removes the attachment row together with the underlying media file.
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
    """Association row linking a Session attachment to a Turn.

    Attributes:
        position: Ordering of attachments within the turn; unique per turn via
            a constraint.
    """

    __tablename__ = "turn_attachment"
    # Keep attachment ordering deterministic within a turn.
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


class AgentPluginMcpBinding(SQLModel, table=True):
    """A plugin-provided MCP server binding configured for an Agent.

    Attributes:
        position: Ordering; unique per Agent via a constraint.
        project_id: Optional Project scope; cascade-deleted with the Project.
        binding_id: Stable identifier used to correlate the runtime MCP binding.
    """

    __tablename__ = "agent_plugin_mcp_binding"
    # Disallow duplicate positions so plugin MCP ordering is deterministic.
    __table_args__ = (
        UniqueConstraint(
            "agent_id", "position", name="uq_agent_plugin_mcp_pos"
        ),
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
    plugin: str = Field(sa_column=Column(String(64), nullable=False))
    server: str = Field(sa_column=Column(String(255), nullable=False))
    project_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(32),
            ForeignKey("project.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    binding_id: str = Field(
        default="", sa_column=Column(String(160), nullable=False)
    )


class PluginState(SQLModel, table=True):
    """Enablement state for a plugin within a scope.

    Attributes:
        id: Stable ``scope:plugin`` identifier, including the project id for
            project scope.
        scope: Scope kind, either ``global`` or ``project``.
        project_id: Optional Project scope; cascade-deleted with the Project.
        enabled: Whether the plugin is active for the scope.
    """

    id: str = Field(sa_column=Column(String(160), primary_key=True))
    plugin_name: str = Field(sa_column=Column(String(64), nullable=False))
    scope: str = Field(sa_column=Column(String(16), nullable=False))
    project_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(32),
            ForeignKey("project.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    enabled: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False)
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(UTCDateTime, nullable=False)
    )


class PlanItem(SQLModel, table=True):
    """A plan item tracked within a Session.

    Attributes:
        position: Ordering within the plan; defaults to ``0``.
        status: Lifecycle status such as ``pending``.
    """

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
