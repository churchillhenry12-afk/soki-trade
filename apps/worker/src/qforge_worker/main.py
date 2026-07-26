from celery import Celery  # type: ignore[import-untyped]

worker = Celery(
    "qforge",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)
worker.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


@worker.task(name="qforge.health")  # type: ignore[untyped-decorator]
def health() -> dict[str, str]:
    return {"status": "ok", "execution": "disabled"}
