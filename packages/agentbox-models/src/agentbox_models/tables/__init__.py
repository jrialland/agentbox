"""Re-export the SQLModel table classes grouped by domain area.

Tables live in the ``auth`` and ``core`` modules; re-exporting them here keeps
the physical module layout an implementation detail for repositories, the API,
and tests, which can import every table from ``agentbox_models.tables``.
"""

# Auth tables (users, roles, permissions, API keys); see ``tables.auth`` for the
# cascade and UTC timestamp conventions that apply to these rows.
from agentbox_models.tables.auth import (
    ApiKey,
    ApiKeyScope,
    Permission,
    Role,
    RolePermissionLink,
    User,
    UserRoleLink,
)

# Core domain tables (providers, models, Agent configurations, Projects,
# Sessions, Turns, attachments, plans, and plugins); see ``tables.core``.
from agentbox_models.tables.core import (
    Agent,
    AgentCard,
    AgentMode,
    AgentModeFlag,
    AgentToolBinding,
    AgentToolBindingArg,
    AgentToolBindingEnv,
    AgentToolBindingEnvPassthrough,
    AgentToolBindingRequiredFlag,
    Label,
    MediaFile,
    Model,
    ModelLabelLink,
    PlanItem,
    Project,
    ProjectRoot,
    Provider,
    SessionAttachment,
    SessionRow,
    TurnActivity,
    TurnAttachment,
    TurnRow,
    TurnToolActivity,
)

__all__ = [
    "Agent",
    "AgentCard",
    "AgentMode",
    "AgentModeFlag",
    "AgentToolBinding",
    "AgentToolBindingArg",
    "AgentToolBindingEnv",
    "AgentToolBindingEnvPassthrough",
    "AgentToolBindingRequiredFlag",
    "ApiKey",
    "ApiKeyScope",
    "Label",
    "MediaFile",
    "Model",
    "ModelLabelLink",
    "Permission",
    "PlanItem",
    "Project",
    "ProjectRoot",
    "Provider",
    "Role",
    "RolePermissionLink",
    "SessionAttachment",
    "SessionRow",
    "TurnActivity",
    "TurnAttachment",
    "TurnRow",
    "TurnToolActivity",
    "User",
    "UserRoleLink",
]
