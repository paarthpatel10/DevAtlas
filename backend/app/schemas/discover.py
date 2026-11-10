from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.repository import RepositoryCard

FeedName = Literal["trending", "rising", "new", "hidden-gems", "weekly"]
Period = Literal["day", "week", "month", "all"]
Label = Literal["trending", "rising", "new", "hidden_gem"]
FeedBasis = Literal["growth", "popularity_activity", "insufficient_history", "not_computed"]


class DiscoverItem(RepositoryCard):
    labels: list[Label]
    signals: dict[str, Any]
    signal_text: list[str]
    one_liner: str | None
    why_explore: str | None


class FeedPage(BaseModel):
    items: list[DiscoverItem]
    page: int
    page_size: int
    total: int
    feed: str
    period: str | None
    basis: FeedBasis
    computed_at: datetime | None


class CategorySummary(BaseModel):
    value: str
    label: str
    count: int
    top: list[DiscoverItem]
