from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.services.users import DEMO_USER_ID, ensure_demo_user


def get_current_user(session: Annotated[Session, Depends(get_db)]) -> User:
    """V0 has no authentication: every request acts as the seeded demo user."""
    user = session.get(User, DEMO_USER_ID)
    if user is None:
        user = ensure_demo_user(session)
        session.commit()
    return user
