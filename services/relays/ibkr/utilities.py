"""IBKR-specific normalization utilities.

Maps raw IBKR strings (order types, asset categories) to normalized literals.
"""

from shared.models import AssetClass, OrderType

# IBKR order type strings → normalized OrderType.
# Used by the Flex parser; the listener doesn't receive order type info.
_ORDER_TYPE_MAP: dict[str, OrderType] = {
    "MKT": "market",
    "LMT": "limit",
    "STP": "stop",
    "STP LMT": "stop_limit",
    "TRAIL": "trailing_stop",
    "TRAIL LMT": "trailing_stop",
    "TRAIL LIMIT": "trailing_stop",
}


def normalize_order_type(raw: str) -> OrderType | None:
    """Map an IBKR order type string to the normalized OrderType literal.

    Returns None when the raw value is not in the known mapping.
    """
    return _ORDER_TYPE_MAP.get(raw)


# IBKR asset category / secType → normalized AssetClass.
# Used by both the Flex parser (assetCategory attr) and the listener (contract.secType).
_ASSET_CLASS_MAP: dict[str, AssetClass] = {
    "STK": "equity",
    "OPT": "option",
    "FUT": "future",
    "CRYPTO": "crypto",
    "CASH": "forex",
}


def normalize_asset_class(raw: str) -> AssetClass:
    """Map an IBKR asset category string to the normalized AssetClass literal.

    Returns ``"other"`` when the raw value is not in the known mapping.
    """
    return _ASSET_CLASS_MAP.get(raw, "other")
