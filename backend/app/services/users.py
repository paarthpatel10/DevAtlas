"""Demo-user support. V0 has no authentication; all user-owned data belongs to one demo user."""

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import User

DEMO_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEMO_USER_EMAIL = "demo@example.com"


def ensure_demo_user(session: Session) -> User:
    session.execute(
        insert(User)
        .values(id=DEMO_USER_ID, email=DEMO_USER_EMAIL, display_name="Demo user")
        .on_conflict_do_nothing(index_elements=[User.id])
    )
    user = session.get(User, DEMO_USER_ID)
    assert user is not None
    return user
