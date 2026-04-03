"""Shared Pydantic models — single source of truth for webhook payload types."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Fill(BaseModel):
    event: Literal["fill"] = "fill"
    symbol: str
    underlyingSymbol: str
    secType: str
    exchange: str
    op: str
    quantity: float
    avgPrice: float
    tradeDate: str
    lastFillTime: str
    orderTime: str
    orderId: str
    execIds: list[str]
    account: str
    commission: float
    commissionCurrency: str
    currency: str
    orderType: str
    fillCount: int


class WebhookPayload(BaseModel):
    trades: list[Fill]


if __name__ == "__main__":
    import json
    import sys

    schema = WebhookPayload.model_json_schema()
    json.dump(schema, sys.stdout, indent=2)
    sys.stdout.write("\n")
