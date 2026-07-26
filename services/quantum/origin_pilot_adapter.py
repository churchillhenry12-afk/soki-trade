class OriginPilotUnavailable(RuntimeError):
    pass


def connect() -> None:
    raise OriginPilotUnavailable(
        "Origin Pilot is disabled until credentials and an official SDK are configured"
    )
