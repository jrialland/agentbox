from typing import Generic, TypeVar

from sqlmodel import SQLModel, select

T = TypeVar("T", bound=SQLModel)


class Repository(Generic[T]):
    model: type[T]

    def __init__(self, session_factory):
        self._factory = session_factory

    async def create(self, obj: T) -> T:
        async with self._factory() as s:
            s.add(obj)
            await s.commit()
            await s.refresh(obj)
            return obj

    async def get(self, id: str) -> T | None:
        async with self._factory() as s:
            return (
                await s.execute(select(self.model).where(getattr(self.model, "id") == id))
            ).scalars().first()

    async def list(self) -> list[T]:
        async with self._factory() as s:
            return list((await s.execute(select(self.model))).scalars().all())

    async def delete(self, id: str) -> None:
        async with self._factory() as s:
            row = (
                await s.execute(select(self.model).where(getattr(self.model, "id") == id))
            ).scalars().first()
            if row is not None:
                await s.delete(row)
                await s.commit()


from agentbox_models.tables.auth import ApiKey, Permission, Role, User  # noqa: E402
from agentbox_models.tables.core import (  # noqa: E402
    Project,
    Provider,
    SessionRow,
    TurnRow,
)


class UserRepository(Repository[User]):
    model = User


class RoleRepository(Repository[Role]):
    model = Role


class PermissionRepository(Repository[Permission]):
    model = Permission


class ApiKeyRepository(Repository[ApiKey]):
    model = ApiKey


class ProviderRepository(Repository[Provider]):
    model = Provider


class ProjectRepository(Repository[Project]):
    model = Project


class SessionRepository(Repository[SessionRow]):
    model = SessionRow


class TurnRepository(Repository[TurnRow]):
    model = TurnRow
