from sqlmodel import select

from agentbox_models.tables.core import Label, Model, ModelLabelLink, Provider

MAX_LABEL_LENGTH = 40


def canonical_label(name: str) -> str:
    return " ".join(name.strip().lower().split())


async def resolve_model_label(session, label: str, provider: str | None = None):
    canonical = canonical_label(label)
    if not canonical or len(canonical) > MAX_LABEL_LENGTH:
        return None
    statement = (
        select(Model)
        .join(ModelLabelLink, ModelLabelLink.model_id == Model.id)  # ty: ignore[invalid-argument-type]
        .join(Label, Label.id == ModelLabelLink.label_id)  # ty: ignore[invalid-argument-type]
        .join(Provider, Provider.id == Model.provider_id)  # ty: ignore[invalid-argument-type]
        .where(Label.name == canonical)
        .order_by(
            ModelLabelLink.priority,  # ty: ignore[invalid-argument-type]
            Provider.name,
            Model.name,
        )
    )
    if provider is not None:
        statement = statement.where(Provider.name == provider)
    return (await session.execute(statement)).scalars().first()
