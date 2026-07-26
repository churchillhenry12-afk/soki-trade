from importlib.util import find_spec


def capability_status() -> dict[str, str | bool]:
    available = find_spec("pyqpanda") is not None
    return {
        "adapter_kind": "qpanda",
        "available": available,
        "verified": False,
        "detail": "installed but unverified" if available else "pyqpanda is not installed",
    }
