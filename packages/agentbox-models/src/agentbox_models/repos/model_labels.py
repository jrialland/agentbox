"""Canonicalize model labels and resolve them to model rows.

Labels are user-facing aliases joined to models through ``ModelLabelLink``.
Resolution prefers lower link priority, then provider name, then model name, so
the same label maps deterministically across providers.
"""

from sqlmodel import select

from agentbox_models.tables.core import Label, Model, ModelLabelLink, Provider

MAX_LABEL_LENGTH = 40


def canonical_label(name: str) -> str:
    """Normalize a label to lowercase words separated by single spaces.

    Args:
        name: Raw label text.

    Returns:
        The canonical spelling; empty or whitespace-only input returns ``""``.
    """
    return " ".join(name.strip().lower().split())


async def resolve_model_label(session, label: str, provider: str | None = None):
    """Resolve a label to a model row using the caller's session.

    Matching is case-insensitive after canonicalization and ordered by link
    priority, then provider name, then model name, so the first row is the
    preferred match.

    Args:
        session: Caller-owned session; the caller controls the transaction.
        label: Raw label text to canonicalize and look up.
        provider: Optional provider name to restrict the match.

    Returns:
        The preferred matching model row, or ``None`` when the label is empty,
        overlong, or unknown.
    """
    canonical = canonical_label(label)
    # Reject empty or overlong labels before querying.
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
    # Apply the provider scope after ordering; the ranking stays identical and
    # the first row is still the preferred model for that provider.
    if provider is not None:
        statement = statement.where(Provider.name == provider)
    return (await session.execute(statement)).scalars().first()
