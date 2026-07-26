from __future__ import annotations

from typing import Any, Protocol


class MT5Adapter(Protocol):
    name: str
    verified: bool

    def health_check(self) -> dict[str, Any]: ...


class MockMT5Adapter:
    name = "mock-mt5-readonly"
    verified = False

    def health_check(self) -> dict[str, str | bool]:
        return {
            "status": "MOCK",
            "adapter_kind": self.name,
            "verified": self.verified,
            "order_access": False,
            "account_mode": "NONE",
        }


class DisabledMT5Adapter:
    """Production research has no broker mutation surface."""

    name = "mt5-disabled-research-only"
    verified = True

    def health_check(self) -> dict[str, str | bool]:
        return {
            "status": "DISABLED",
            "adapter_kind": self.name,
            "verified": self.verified,
            "order_access": False,
            "account_mode": "NONE",
        }
