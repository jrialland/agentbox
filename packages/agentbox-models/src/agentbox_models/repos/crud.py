"""Generic async CRUD repositories for SQLModel tables.

``Repository`` provides create, read, list, and delete for a table with an
``id`` primary key. Each operation opens its own session from the injected
factory and commits writes before returning; concrete subclasses only bind a
model class.
"""

from typing import Generic, TypeVar

from sqlmodel import SQLModel, select

T = TypeVar("T", bound=SQLModel)


class Repository(Generic[T]):
    """Base repository for one SQLModel table with an ``id`` primary key.

    Subclasses set :attr:`model` to the table class they manage and inherit the
    standard operations. Instances hold only the session factory.

    Attributes:
        model: SQLModel table class managed by the repository.
    """

    model: type[T]

    def __init__(self, session_factory):
        self._factory = session_factory

    async def create(self, obj: T) -> T:
        """Persist a new row and return it refreshed from the database.

        Args:
            obj: Unsaved table instance.

        Returns:
            The same instance after commit and refresh.
        """
        async with self._factory() as s:
            s.add(obj)
            await s.commit()
            # Refresh after commit so server defaults and generated values are
            # populated before the object is returned to the caller.
            await s.refresh(obj)
            return obj

    async def get(self, id: str) -> T | None:
        """Return the row with the given primary key.

        Args:
            id: Primary key value.

        Returns:
            The matching row, or ``None`` when it does not exist.
        """
        async with self._factory() as s:
            return (
                await s.execute(select(self.model).where(getattr(self.model, "id") == id))
            ).scalars().first()

    async def list(self) -> list[T]:
        """Return every row in the table.

        Returns:
            All rows in unspecified order.
        """
        async with self._factory() as s:
            return list((await s.execute(select(self.model))).scalars().all())

    async def delete(self, id: str) -> None:
        """Delete the row with the given primary key.

        Missing rows are ignored. The delete is committed before returning.

        Args:
            id: Primary key value.
        """
        async with self._factory() as s:
            row = (
                await s.execute(select(self.model).where(getattr(self.model, "id") == id))
            ).scalars().first()
            if row is not None:
                await s.delete(row)
                await s.commit()


from agentbox_models.tables.auth import ApiKey, Permission, Role, User  # noqa: E402
from agentbox_models.tables.core import (  # noqa: E402
    Model,
    Project,
    Provider,
    SessionRow,
    TurnRow,
)


class UserRepository(Repository[User]):
    """Repository for user rows."""

    model = User


class RoleRepository(Repository[Role]):
    """Repository for role rows."""

    model = Role


class PermissionRepository(Repository[Permission]):
    """Repository for permission rows."""

    model = Permission


class ApiKeyRepository(Repository[ApiKey]):
    """Repository for API key rows."""

    model = ApiKey


class ProviderRepository(Repository[Provider]):
    """Repository for provider rows."""

    model = Provider


class ModelRepository(Repository[Model]):
    """Repository for model rows."""

    model = Model


class ProjectRepository(Repository[Project]):
    """Repository for project rows."""

    model = Project


class SessionRepository(Repository[SessionRow]):
    """Repository for session rows."""

    model = SessionRow


class TurnRepository(Repository[TurnRow]):
    """Repository for turn rows."""

    model = TurnRow
