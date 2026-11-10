from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.ai.provider import Providers
from app.ai.vocabulary import get_vocabulary
from app.api.deps import get_current_user, get_providers_dep
from app.db.session import get_db
from app.models import User
from app.schemas.recommendation import RecommendRequest, RecommendResponse
from app.services.recommendation_service import recommend

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/recommend", response_model=RecommendResponse)
def recommend_repositories(
    body: RecommendRequest,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    providers: Annotated[Providers, Depends(get_providers_dep)],
) -> RecommendResponse:
    settings = request.app.state.settings
    return recommend(session, body, providers, get_vocabulary(), settings, user.id)
