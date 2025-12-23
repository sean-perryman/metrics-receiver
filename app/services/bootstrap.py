from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.user import User, UserRole


async def bootstrap_admin() -> None:
    async with AsyncSessionLocal() as db:
        q = await db.execute(select(User).where(User.role == UserRole.admin))
        if q.scalars().first():
            return

        admin = User(
            email=settings.bootstrap_admin_email.lower(),
            password_hash=hash_password(settings.bootstrap_admin_password),
            role=UserRole.admin,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
