from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, field_validator

class Transaction(BaseModel):
    id: str
    posted: datetime
    amount: Decimal
    description: str
    pending: bool = False

    @field_validator("posted", mode="before")
    @classmethod
    def parse_epoch_to_utc(cls, value: datetime):
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        return value



class Account(BaseModel):
    id: str
    name: str
    currency: str
    balance: Decimal
    transactions: list[Transaction] = []


class AccountsResponse(BaseModel):
    errors: list[str] = []
    accounts: list[Account]
