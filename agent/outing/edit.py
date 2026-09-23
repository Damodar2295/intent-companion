from decimal import Decimal
from typing import Literal

from pydantic import Field

from agent.domain import Model


class OutingEditRequest(Model):
    customer_id: str = Field(min_length=1, max_length=100)
    operation: Literal["REMOVE_STOP", "CHANGE_CATEGORY", "CHANGE_BUDGET", "CHANGE_DURATION", "ADD_STOP", "REPLACE_STOP"]
    stop_id: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=30)
    budget: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, pattern="^[A-Z]{3}$")
    visit_minutes: int | None = Field(default=None, ge=15, le=180)
