from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import re
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from pathlib import Path
from sys import platform
from time import monotonic
from typing import Annotated, Any, Literal, cast
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
import structlog
from fastapi import (
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, SecretStr
from qforge import __version__
from qforge.agents import HermesAdapter, MockHermesAdapter, ProductionHermesAdapter
from qforge.backtester import run_backtest
from qforge.database import Approvals, Repository
from qforge.gateways import (
    GatewayConnectionError,
    GatewayManager,
    MT5AccountMode,
    MT5Connection,
    MT5Transport,
    TelegramConnection,
)
from qforge.hermes_runtime import HermesRuntimeClient, RuntimeAttachment, SokiAgentRuntime
from qforge.market_data import (
    MarketDataAdapter,
    MockMarketDataAdapter,
    YahooFinanceMarketDataAdapter,
)
from qforge.model_router import ModelRouter, ProviderKind
from qforge.mt5 import DisabledMT5Adapter, MockMT5Adapter, MT5Adapter
from qforge.optimizer import select_portfolio
from qforge.orchestrator import ExperimentOrchestrator
from qforge.proof import ProofLedger
from qforge.quantum import (
    ClassicalControlBackend,
    MockQuantumBackend,
    QuantumBackend,
    benchmark,
)
from qforge.schemas import (
    AgentTask,
    Approval,
    ApprovalCreate,
    Attachment,
    AttachmentKind,
    BacktestResult,
    Experiment,
    ExperimentCreate,
    ExperimentEvent,
    Mode,
    ResearchObjective,
    ResearchObjectiveCreate,
    RiskDecision,
    SolverBenchmark,
    SolverResult,
    StatisticalResult,
    StrategyDefinition,
    SystemStatus,
    utc_now,
)
from qforge.settings import Settings

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger("qforge.api")
started_at = monotonic()


class DirectBacktestRequest(BaseModel):
    experiment_id: UUID
    strategy_id: str
    seed: int = 42


class OptimizationRequest(BaseModel):
    experiment_id: UUID
    seed: int = 42


class QuantumJobRequest(BaseModel):
    experiment_id: UUID
    seed: int = 42


class ModelConfigurationRequest(BaseModel):
    provider: ProviderKind
    model: str = Field(max_length=200)
    base_url: str = Field(default="", max_length=500)
    api_key: SecretStr | None = None
    persist: bool = True


class ModelDiscoveryRequest(BaseModel):
    provider: ProviderKind
    base_url: str = Field(min_length=8, max_length=500)
    api_key: SecretStr | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    reply: str
    provider: str
    model: str
    mock: bool


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    experiment_id: UUID | None = None
    session_id: str = Field(default_factory=lambda: f"soki-{uuid4().hex}", max_length=120)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=8)


class AgentChatResponse(BaseModel):
    reply: str
    action: Literal[
        "MESSAGE",
        "EXPERIMENT_STARTED",
        "REPORT",
        "STATUS",
        "CONNECTION_SETUP",
        "CONNECTION_CHANGED",
    ]
    client_action: Literal[
        "CONNECT_MODEL",
        "CONNECT_HERMES",
        "CONNECT_TELEGRAM",
        "CONNECT_MT5",
        "PAIR_PHONE",
    ] | None = None
    experiment_id: UUID | None = None
    state: str | None = None
    session_id: str | None = None
    task_id: UUID | None = None
    runtime: str = "soki-core"
    proof: AgentTask | None = None


class AttachmentResponse(BaseModel):
    attachment_id: UUID
    name: str
    media_type: str
    kind: AttachmentKind
    size_bytes: int
    sha256: str
    created_at: str
    download_url: str


ActivityEmitter = Callable[[str, str, str, str], Awaitable[None]]


async def _emit_activity(
    emitter: ActivityEmitter | None,
    activity_id: str,
    label: str,
    *,
    state: str = "completed",
    detail: str = "",
) -> None:
    if emitter is not None:
        await emitter(activity_id, label, state, detail)


class HermesConfigurationRequest(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    api_key: SecretStr
    model: str = Field(default="hermes", min_length=1, max_length=200)
    persist: bool = True


class PairingSessionRequest(BaseModel):
    api_base_url: str = Field(min_length=8, max_length=500)


class PairingSessionResponse(BaseModel):
    pairing_id: UUID
    expires_at: str
    qr_payload: str


class PairingClaimRequest(BaseModel):
    pairing_id: UUID
    code: str = Field(min_length=8, max_length=80)
    device_name: str = Field(min_length=1, max_length=120)


class PairingClaimResponse(BaseModel):
    device_id: UUID
    device_token: str
    api_base_url: str


class TelegramGatewayRequest(BaseModel):
    bot_token: SecretStr
    chat_id: str = Field(default="", max_length=120)


class MT5GatewayRequest(BaseModel):
    transport: MT5Transport
    endpoint: str = Field(min_length=8, max_length=500)
    account_mode: MT5AccountMode
    token: SecretStr | None = None


async def _probe_model_connection(router: ModelRouter) -> bool:
    reply = await router.complete(
        "Reply with exactly QFORGE_CONNECTED.",
        system_prompt="Return exactly QFORGE_CONNECTED and nothing else.",
    )
    return "QFORGE_CONNECTED" in reply.upper()


def _saved_hermes_configuration(settings: Settings) -> dict[str, str]:
    path = Path(settings.hermes_config_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        key: str(payload.get(key, ""))
        for key in ("url", "api_key", "model")
        if payload.get(key)
    }


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    settings = Settings()
    repository = Repository(settings.database_url)
    model_router = ModelRouter()
    app.state.settings = settings
    app.state.repository = repository
    app.state.model_router = model_router
    saved_hermes = _saved_hermes_configuration(settings)
    hermes_runtime = HermesRuntimeClient(
        base_url=saved_hermes.get("url", settings.hermes_url),
        api_key=saved_hermes.get("api_key", settings.hermes_api_key),
        model=saved_hermes.get("model", settings.hermes_model),
        timeout_seconds=settings.hermes_timeout_seconds,
    )
    app.state.hermes_runtime = hermes_runtime
    app.state.agent_runtime = SokiAgentRuntime(hermes_runtime, model_router)
    app.state.proof_ledger = ProofLedger(repository)
    if hermes_runtime.configured:
        await hermes_runtime.probe()
    app.state.model_connected = False
    if not model_router.configuration.is_mock:
        try:
            app.state.model_connected = await asyncio.wait_for(
                _probe_model_connection(model_router),
                timeout=12,
            )
        except (TimeoutError, httpx.HTTPError, ValueError) as error:
            logger.warning(
                "saved_model_probe_failed",
                error_type=type(error).__name__,
            )
    app.state.gateways = GatewayManager(Path(settings.gateway_config_path))
    hermes: HermesAdapter
    market_data: MarketDataAdapter
    quantum: QuantumBackend
    mt5: MT5Adapter
    if settings.demo_mode:
        hermes = MockHermesAdapter()
        market_data = MockMarketDataAdapter()
        quantum = MockQuantumBackend()
        mt5 = MockMT5Adapter()
    else:
        hermes = ProductionHermesAdapter(model_router)
        market_data = YahooFinanceMarketDataAdapter(Path(settings.market_data_directory))
        quantum = ClassicalControlBackend()
        mt5 = DisabledMT5Adapter()
    app.state.market_data = market_data
    app.state.mt5 = mt5
    app.state.orchestrator = ExperimentOrchestrator(
        repository,
        hermes,
        market_data,
        quantum,
    )
    app.state.telegram_task = asyncio.create_task(_telegram_agent_loop(app))
    yield
    tasks = [*app.state.orchestrator.tasks.values(), app.state.telegram_task]
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(
    title="soki code API",
    summary="Agentic operations with deterministic trading research",
    version=__version__,
    lifespan=lifespan,
)
cors_settings = Settings()
hosted_ui_origin = "https://soki-trade-agent.vercel.app"
cors_allowed_origins = list(dict.fromkeys([*cors_settings.allowed_origins, hosted_ui_origin]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_origin_regex=r"https?://(?:127\.0\.0\.1|localhost)(?::\d+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_private_network=True,
)


def _repository() -> Repository:
    return cast(Repository, app.state.repository)


def _orchestrator() -> ExperimentOrchestrator:
    return cast(ExperimentOrchestrator, app.state.orchestrator)


def _model_router() -> ModelRouter:
    return cast(ModelRouter, app.state.model_router)


def _agent_runtime() -> SokiAgentRuntime:
    return cast(SokiAgentRuntime, app.state.agent_runtime)


def _proof_ledger() -> ProofLedger:
    return cast(ProofLedger, app.state.proof_ledger)


def _hermes_runtime() -> HermesRuntimeClient:
    return cast(HermesRuntimeClient, app.state.hermes_runtime)


def _gateways() -> GatewayManager:
    return cast(GatewayManager, app.state.gateways)


def _settings() -> Settings:
    return cast(Settings, app.state.settings)


def _market_data() -> MarketDataAdapter:
    return cast(MarketDataAdapter, app.state.market_data)


def _secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _attachment_kind(media_type: str) -> AttachmentKind:
    top_level = media_type.split("/", 1)[0]
    if top_level == "image":
        return AttachmentKind.IMAGE
    if top_level == "video":
        return AttachmentKind.VIDEO
    if top_level == "audio":
        return AttachmentKind.AUDIO
    if media_type in {
        "application/pdf",
        "application/json",
        "application/rtf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    } or media_type.startswith("text/"):
        return AttachmentKind.DOCUMENT
    if media_type in {"application/zip", "application/x-tar", "application/gzip"}:
        return AttachmentKind.ARCHIVE
    return AttachmentKind.OTHER


def _attachment_response(attachment: Attachment, *, mobile: bool = False) -> AttachmentResponse:
    prefix = "/mobile/attachments" if mobile else "/attachments"
    return AttachmentResponse(
        attachment_id=attachment.attachment_id,
        name=attachment.name,
        media_type=attachment.media_type,
        kind=attachment.kind,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
        created_at=attachment.created_at.isoformat(),
        download_url=f"{prefix}/{attachment.attachment_id}",
    )


async def _store_attachment(upload: UploadFile, *, owner: str) -> Attachment:
    original_name = Path(upload.filename or "attachment").name.strip()
    safe_name = re.sub(r"[^A-Za-z0-9._() -]+", "_", original_name)[:240] or "attachment"
    media_type = (upload.content_type or mimetypes.guess_type(safe_name)[0] or "").lower()
    if not media_type or media_type == "application/octet-stream":
        media_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    kind = _attachment_kind(media_type)
    if kind is AttachmentKind.OTHER:
        raise HTTPException(status_code=415, detail="This file type is not supported.")

    attachment_id = uuid4()
    directory = Path(_settings().attachment_directory) / str(attachment_id)
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / safe_name
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("xb") as target:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > _settings().attachment_max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="Attachments can be up to 200 MB.",
                    )
                digest.update(chunk)
                target.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        with suppress(OSError):
            directory.rmdir()
        raise
    finally:
        await upload.close()

    attachment = Attachment(
        attachment_id=attachment_id,
        owner=owner,
        name=safe_name,
        media_type=media_type,
        kind=kind,
        size_bytes=size,
        sha256=digest.hexdigest(),
        storage_path=str(path),
    )
    return _repository().save_attachment(attachment)


def _runtime_attachments(ids: list[UUID], *, owner: str) -> list[RuntimeAttachment]:
    resolved: list[RuntimeAttachment] = []
    for attachment_id in ids:
        attachment = _repository().get_attachment(attachment_id, owner=owner)
        if attachment is None:
            raise HTTPException(status_code=404, detail="An attachment was not found.")
        path = Path(attachment.storage_path)
        if not path.is_file():
            raise HTTPException(
                status_code=410,
                detail=f"{attachment.name} is no longer available.",
            )
        resolved.append(
            RuntimeAttachment(
                name=attachment.name,
                media_type=attachment.media_type,
                kind=attachment.kind.value,
                path=path,
                size_bytes=attachment.size_bytes,
            )
        )
    return resolved


def _require_local_request(request: Request) -> None:
    host = request.client.host if request.client is not None else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(
            status_code=403,
            detail="This control action is available only from the laptop running soki code.",
        )


def _validated_api_base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="Enter a valid HTTP or HTTPS API URL.")
    return url


def _authenticated_device(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A paired-device token is required.")
    token = authorization.removeprefix("Bearer ").strip()
    if len(token) < 32:
        raise HTTPException(status_code=401, detail="The paired-device token is invalid.")
    device = _repository().authenticate_device(_secret_hash(token))
    if device is None:
        raise HTTPException(status_code=401, detail="This device is not paired or was revoked.")
    return device


def _market_data_status() -> dict[str, str | bool]:
    adapter = _market_data()
    if isinstance(adapter, MockMarketDataAdapter):
        return {
            "status": "MOCK",
            "adapter_kind": adapter.name,
            "verified": adapter.verified,
            "directory": "",
        }
    directory = cast(YahooFinanceMarketDataAdapter, adapter).data_directory
    files = list(directory.glob("*.csv")) + list(directory.glob("*.parquet"))
    cached_files = list((directory / ".cache").glob("*.csv"))
    return {
        "status": "READY",
        "adapter_kind": adapter.name,
        "verified": adapter.verified,
        "directory": str(directory),
        "source": "LOCAL_OVERRIDE" if files else ("CACHE" if cached_files else "PUBLIC_FEED"),
    }


def _production_blockers() -> list[str]:
    if _settings().demo_mode:
        return []
    blockers: list[str] = []
    if not _orchestrator().hermes.verified:
        blockers.append("production research engine is unavailable")
    if _market_data_status()["status"] != "READY":
        blockers.append("market data adapter is unavailable")
    return blockers


def _http_error(error: Exception) -> HTTPException:
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail="resource not found")
    return HTTPException(status_code=409, detail=str(error))


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "runtime": "DEMO" if _settings().demo_mode else "PRODUCTION",
    }


@app.get("/ready", tags=["system"])
async def readiness() -> dict[str, str | list[str]]:
    blockers = _production_blockers()
    if blockers:
        raise HTTPException(
            status_code=503, detail={"status": "CONFIG_REQUIRED", "blockers": blockers}
        )
    return {"status": "ready", "blockers": []}


@app.post(
    "/research/objectives",
    response_model=ResearchObjective,
    status_code=status.HTTP_201_CREATED,
    tags=["research"],
)
async def create_objective(request: ResearchObjectiveCreate) -> ResearchObjective:
    return _orchestrator().create_objective(request)


@app.get("/research/objectives", response_model=list[ResearchObjective], tags=["research"])
async def list_objectives() -> list[ResearchObjective]:
    return _repository().list_objectives()


@app.post(
    "/experiments",
    response_model=Experiment,
    status_code=status.HTTP_201_CREATED,
    tags=["experiments"],
)
async def create_experiment(request: ExperimentCreate) -> Experiment:
    try:
        return _orchestrator().create_experiment(request)
    except (KeyError, ValueError) as error:
        raise _http_error(error) from error


@app.get("/experiments", response_model=list[Experiment], tags=["experiments"])
async def list_experiments() -> list[Experiment]:
    return _repository().list_experiments()


@app.get("/experiments/{experiment_id}", response_model=Experiment, tags=["experiments"])
async def get_experiment(experiment_id: UUID) -> Experiment:
    experiment = _repository().get_experiment(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return experiment


@app.post("/experiments/{experiment_id}/start", response_model=Experiment, tags=["experiments"])
async def start_experiment(experiment_id: UUID) -> Experiment:
    blockers = _production_blockers()
    if blockers:
        raise HTTPException(
            status_code=503,
            detail={"status": "CONFIG_REQUIRED", "blockers": blockers},
        )
    try:
        return _orchestrator().start(experiment_id)
    except (KeyError, ValueError) as error:
        raise _http_error(error) from error


@app.post("/experiments/{experiment_id}/pause", response_model=Experiment, tags=["experiments"])
async def pause_experiment(experiment_id: UUID) -> Experiment:
    try:
        return _orchestrator().pause(experiment_id)
    except (KeyError, ValueError) as error:
        raise _http_error(error) from error


@app.post("/experiments/{experiment_id}/resume", response_model=Experiment, tags=["experiments"])
async def resume_experiment(experiment_id: UUID) -> Experiment:
    try:
        return _orchestrator().resume(experiment_id)
    except (KeyError, ValueError) as error:
        raise _http_error(error) from error


@app.post("/experiments/{experiment_id}/cancel", response_model=Experiment, tags=["experiments"])
async def cancel_experiment(experiment_id: UUID) -> Experiment:
    try:
        return _orchestrator().cancel(experiment_id)
    except (KeyError, ValueError) as error:
        raise _http_error(error) from error


@app.get(
    "/experiments/{experiment_id}/events",
    response_model=list[ExperimentEvent],
    tags=["experiments"],
)
async def experiment_events(
    experiment_id: UUID, after: Annotated[int, Query(ge=0)] = 0
) -> list[ExperimentEvent]:
    if _repository().get_experiment(experiment_id) is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return _repository().events(experiment_id, after=after)


@app.get("/strategies", response_model=list[StrategyDefinition], tags=["strategies"])
async def list_strategies() -> list[dict[str, Any]]:
    return _repository().strategies()


@app.get("/strategies/{strategy_id}", response_model=StrategyDefinition, tags=["strategies"])
async def get_strategy(strategy_id: str) -> dict[str, Any]:
    for strategy in _repository().strategies():
        if strategy["strategy_id"] == strategy_id:
            return strategy
    raise HTTPException(status_code=404, detail="strategy not found")


@app.post("/backtests", response_model=BacktestResult, tags=["backtests"])
async def create_backtest(request: DirectBacktestRequest) -> BacktestResult:
    experiment = _repository().get_experiment(request.experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    objective = _repository().get_objective(experiment.objective_id)
    strategy_payload = next(
        (item for item in _repository().strategies() if item["strategy_id"] == request.strategy_id),
        None,
    )
    if objective is None or strategy_payload is None:
        raise HTTPException(status_code=404, detail="objective or strategy not found")
    frame = await asyncio.to_thread(
        _market_data().bars,
        objective.symbols[0],
        objective.timeframe,
        seed=request.seed,
    )
    return await asyncio.to_thread(
        run_backtest,
        StrategyDefinition.model_validate(strategy_payload),
        frame,
        seed=request.seed,
    )


@app.get("/backtests/{backtest_id}", response_model=BacktestResult, tags=["backtests"])
async def get_backtest(backtest_id: UUID) -> dict[str, Any]:
    for backtest in _repository().backtests():
        if backtest["backtest_id"] == str(backtest_id):
            return backtest
    raise HTTPException(status_code=404, detail="backtest not found")


def _statistics_for(experiment_id: UUID) -> list[StatisticalResult]:
    experiment = _repository().get_experiment(experiment_id)
    if experiment is None or experiment.report is None:
        raise HTTPException(status_code=409, detail="experiment report is not ready")
    return experiment.report.statistical_results


@app.post("/optimizations", response_model=SolverResult, tags=["optimization"])
async def create_optimization(request: OptimizationRequest) -> SolverResult:
    return select_portfolio(_statistics_for(request.experiment_id), seed=request.seed)


@app.get("/optimizations/{experiment_id}", response_model=SolverResult, tags=["optimization"])
async def get_optimization(experiment_id: UUID) -> SolverResult:
    experiment = _repository().get_experiment(experiment_id)
    if experiment is None or experiment.report is None:
        raise HTTPException(status_code=404, detail="optimization not found")
    return experiment.report.classical_selection


@app.post("/quantum/jobs", response_model=SolverBenchmark, tags=["quantum"])
async def create_quantum_job(request: QuantumJobRequest) -> SolverBenchmark:
    statistics = _statistics_for(request.experiment_id)
    classical = select_portfolio(statistics, seed=request.seed)
    quantum = _orchestrator().quantum.solve(statistics, seed=request.seed)
    return benchmark(classical, quantum)


@app.get("/quantum/jobs/{experiment_id}", response_model=SolverBenchmark, tags=["quantum"])
async def get_quantum_job(experiment_id: UUID) -> SolverBenchmark:
    experiment = _repository().get_experiment(experiment_id)
    if experiment is None or experiment.report is None:
        raise HTTPException(status_code=404, detail="quantum benchmark not found")
    return experiment.report.solver_benchmark


@app.get("/risk/reviews", response_model=list[RiskDecision], tags=["risk"])
async def list_risk_reviews() -> list[dict[str, Any]]:
    return _repository().risk_reviews()


@app.post("/approvals", response_model=Experiment, tags=["risk"])
async def approve_experiment(request: ApprovalCreate) -> Experiment:
    approval = Approval(
        experiment_id=request.experiment_id,
        approver=request.approver,
        target_mode=request.target_mode,
    )
    experiment = _repository().get_experiment(request.experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    _repository().save_resource(
        Approvals,
        experiment_id=experiment.experiment_id,
        correlation_id=experiment.correlation_id,
        agent="HUMAN",
        status="ACKNOWLEDGED",
        payload=approval.model_dump(mode="json"),
    )
    try:
        return await _orchestrator().approve(approval)
    except (KeyError, ValueError) as error:
        raise _http_error(error) from error


@app.get("/system/status", response_model=SystemStatus, tags=["system"])
async def system_status() -> SystemStatus:
    quantum = _orchestrator().quantum
    hermes_status = (
        {
            "status": "MOCK",
            "adapter_kind": _orchestrator().hermes.name,
            "verified": False,
        }
        if _settings().demo_mode
        else _hermes_runtime().status()
    )
    return SystemStatus(
        version=__version__,
        mode=Mode.RESEARCH,
        runtime="DEMO" if _settings().demo_mode else "PRODUCTION",
        hermes=hermes_status,
        market_data=_market_data_status(),
        mt5=app.state.mt5.health_check(),
        quantum={
            "status": "MOCK" if _settings().demo_mode else "DISABLED",
            "adapter_kind": quantum.name,
            "verified": quantum.verified if _settings().demo_mode else False,
        },
        uptime_seconds=monotonic() - started_at,
    )


@app.get("/models/config", tags=["models"])
async def model_configuration() -> dict[str, str | bool]:
    return _model_router().status()


@app.post("/models/config", tags=["models"])
async def configure_model(request: ModelConfigurationRequest) -> dict[str, str | bool]:
    try:
        key = request.api_key.get_secret_value() if request.api_key is not None else None
        configured = _model_router().configure(
            provider=request.provider,
            model=request.model,
            base_url=request.base_url,
            api_key=key,
            persist=request.persist,
        )
        app.state.model_connected = False
        return configured
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/models/scan", tags=["models"])
async def scan_models(request: ModelDiscoveryRequest) -> dict[str, str | int | list[str]]:
    key = request.api_key.get_secret_value() if request.api_key is not None else None
    try:
        models = await _model_router().discover_models(
            provider=request.provider,
            base_url=request.base_url,
            api_key=key,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except httpx.HTTPStatusError as error:
        status_code = error.response.status_code
        raise HTTPException(
            status_code=502,
            detail=f"provider model scan failed with HTTP {status_code}",
        ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail=f"provider model scan failed: {error}",
        ) from error
    return {
        "provider": request.provider,
        "base_url": request.base_url.rstrip("/"),
        "count": len(models),
        "models": models,
    }


@app.post("/models/test", tags=["setup"])
async def test_model_connection() -> dict[str, str | bool]:
    router = _model_router()
    if router.configuration.is_mock:
        raise HTTPException(status_code=422, detail="select a real or local model provider")
    try:
        connected = await _probe_model_connection(router)
    except (httpx.HTTPError, ValueError) as error:
        app.state.model_connected = False
        raise HTTPException(status_code=502, detail=f"model connection failed: {error}") from error
    app.state.model_connected = connected
    if not connected:
        raise HTTPException(status_code=502, detail="model returned an unexpected test response")
    return {**router.status(), "connected": True}


@app.get("/setup/status", tags=["setup"])
async def setup_status() -> dict[str, Any]:
    system = await system_status()
    model = _model_router().status()
    gateways = _gateways().status()
    intelligence_ready = bool(app.state.model_connected) or _hermes_runtime().healthy
    market_ready = system.market_data.get("status") in {"READY", "MOCK"}
    core_ready = intelligence_ready and market_ready
    return {
        "agent": {
            "name": "soki code",
            "ready": core_ready,
            "runtime": system.runtime,
            "execution": "RESEARCH_AND_PAPER_ONLY",
            "proof_loop": "ENABLED",
        },
        "hermes": _hermes_runtime().status(),
        "model": {**model, "connected": bool(app.state.model_connected)},
        "market_data": system.market_data,
        "telegram": gateways["telegram"],
        "mt5": gateways["mt5"],
        "paired_devices": len(_repository().list_paired_devices()),
    }


@app.get("/hermes/status", tags=["hermes"])
async def hermes_status() -> dict[str, str | bool]:
    return _hermes_runtime().status()


@app.post("/hermes/config", tags=["hermes"])
async def configure_hermes(
    payload: HermesConfigurationRequest,
    request: Request,
) -> dict[str, str | bool]:
    _require_local_request(request)
    base_url = _validated_api_base_url(payload.url)
    runtime = _hermes_runtime()
    runtime.base_url = base_url
    runtime.api_key = payload.api_key.get_secret_value()
    runtime.model = payload.model.strip()
    if payload.persist:
        path = Path(_settings().hermes_config_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "url": runtime.base_url,
                        "api_key": runtime.api_key,
                        "model": runtime.model,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            path.chmod(0o600)
        except OSError as error:
            raise HTTPException(
                status_code=500,
                detail=f"Could not save the Hermes configuration: {error}",
            ) from error
    await runtime.probe()
    if not runtime.healthy:
        raise HTTPException(status_code=502, detail=runtime.last_error)
    return runtime.status()


@app.post("/hermes/test", tags=["hermes"])
async def test_hermes(request: Request) -> dict[str, str | bool]:
    _require_local_request(request)
    runtime = _hermes_runtime()
    if not await runtime.probe():
        raise HTTPException(status_code=502, detail=runtime.last_error)
    return runtime.status()


@app.post(
    "/pairing/sessions",
    response_model=PairingSessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["pairing"],
)
async def create_pairing_session(
    payload: PairingSessionRequest,
    request: Request,
) -> PairingSessionResponse:
    _require_local_request(request)
    pairing_id = uuid4()
    code = secrets.token_urlsafe(12)
    expires_at = utc_now() + timedelta(minutes=5)
    api_base_url = _validated_api_base_url(payload.api_base_url)
    _repository().create_pairing_session(
        pairing_id=pairing_id,
        code_hash=_secret_hash(code),
        api_base_url=api_base_url,
        expires_at=expires_at,
    )
    pairing_token = base64.urlsafe_b64encode(pairing_id.bytes).decode().rstrip("=")
    qr_parts = ["soki", "1", pairing_token, code]
    if api_base_url != "http://127.0.0.1:8000":
        encoded_url = base64.urlsafe_b64encode(api_base_url.encode()).decode().rstrip("=")
        qr_parts.append(encoded_url)
    qr_payload = ":".join(qr_parts)
    return PairingSessionResponse(
        pairing_id=pairing_id,
        expires_at=expires_at.isoformat(),
        qr_payload=qr_payload,
    )


@app.get("/pairing/sessions/{pairing_id}", tags=["pairing"])
async def pairing_session_status(pairing_id: UUID, request: Request) -> dict[str, Any]:
    _require_local_request(request)
    pairing = _repository().pairing_session(pairing_id)
    if pairing is None:
        raise HTTPException(status_code=404, detail="pairing session not found")
    claimed = pairing["claimed_at"] is not None
    expired = pairing["expires_at"] <= utc_now()
    return {
        "pairing_id": pairing["pairing_id"],
        "status": "PAIRED" if claimed else ("EXPIRED" if expired else "WAITING"),
        "expires_at": pairing["expires_at"],
        "device_id": pairing["claimed_device_id"],
    }


@app.post(
    "/pairing/claim",
    response_model=PairingClaimResponse,
    tags=["pairing"],
)
async def claim_pairing_session(payload: PairingClaimRequest) -> PairingClaimResponse:
    token = secrets.token_urlsafe(36)
    device_id = uuid4()
    pairing = _repository().claim_pairing_session(
        pairing_id=payload.pairing_id,
        code_hash=_secret_hash(payload.code),
        device_id=device_id,
        device_name=payload.device_name.strip(),
        token_hash=_secret_hash(token),
        claimed_at=utc_now(),
    )
    if pairing is None:
        raise HTTPException(
            status_code=410,
            detail="This pairing code is invalid, expired, or already used.",
        )
    return PairingClaimResponse(
        device_id=device_id,
        device_token=token,
        api_base_url=str(pairing["api_base_url"]),
    )


@app.get("/devices", tags=["pairing"])
async def paired_devices(request: Request) -> list[dict[str, Any]]:
    _require_local_request(request)
    return _repository().list_paired_devices()


@app.delete("/devices/{device_id}", tags=["pairing"])
async def revoke_device(device_id: UUID, request: Request) -> dict[str, bool]:
    _require_local_request(request)
    if not _repository().revoke_paired_device(device_id):
        raise HTTPException(status_code=404, detail="paired device not found")
    return {"revoked": True}


@app.post("/gateways/telegram/connect", tags=["setup"])
async def connect_telegram(request: TelegramGatewayRequest) -> dict[str, str | bool]:
    try:
        return await _gateways().connect_telegram(
            TelegramConnection(
                token=request.bot_token.get_secret_value(),
                chat_id=request.chat_id,
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except GatewayConnectionError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.delete("/gateways/telegram", tags=["setup"])
async def disconnect_telegram() -> dict[str, str | bool]:
    return _gateways().disconnect_telegram()


@app.post("/gateways/mt5/connect", tags=["setup"])
async def connect_mt5(request: MT5GatewayRequest) -> dict[str, str | bool]:
    try:
        return await _gateways().connect_mt5(
            MT5Connection(
                transport=request.transport,
                endpoint=request.endpoint,
                account_mode=request.account_mode,
                token=request.token.get_secret_value() if request.token else "",
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except GatewayConnectionError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.delete("/gateways/mt5", tags=["setup"])
async def disconnect_mt5() -> dict[str, str | bool]:
    return _gateways().disconnect_mt5()


def _local_mt5_terminal() -> Path | None:
    candidate: Path | None = (
        Path("/Applications/MetaTrader 5.app")
        if platform == "darwin"
        else Path("C:/Program Files/MetaTrader 5/terminal64.exe")
        if platform == "win32"
        else None
    )
    return candidate if candidate is not None and candidate.exists() else None


def _connection_status_response(
    *,
    include_telegram: bool = True,
    include_mt5: bool = True,
) -> AgentChatResponse:
    gateways = _gateways().status()
    parts: list[str] = []
    if include_telegram:
        telegram = gateways["telegram"]
        if telegram["connected"]:
            username = str(telegram.get("bot_username", "")).strip()
            parts.append(
                f"Telegram is connected{f' as @{username}' if username else ''}."
            )
        else:
            parts.append(
                "Telegram is not connected. Use Connect Telegram and enter a bot token "
                "plus the one chat ID allowed to control soki code."
            )
    if include_mt5:
        mt5 = gateways["mt5"]
        if mt5["connected"]:
            verification = (
                "verified by the bridge"
                if mt5.get("account_mode_source") == "BRIDGE_VERIFIED"
                else "selected during setup"
            )
            parts.append(
                f"MT5 is connected through {str(mt5['transport']).upper()} "
                f"({mt5['account_mode']} account, {verification}, read-only)."
            )
        else:
            local_terminal = _local_mt5_terminal()
            if local_terminal is not None:
                parts.append(
                    f"MT5 is not connected, although the terminal is installed at "
                    f"{local_terminal}. Log into the intended Demo or Real account, start "
                    "a compatible REST or MCP bridge, then use Connect MT5 to select the "
                    "account type and enter its endpoint and token. Real accounts remain "
                    "read-only."
                )
            else:
                parts.append(
                    "MT5 is not connected and no local terminal was detected. Install "
                    "MetaTrader 5, log into a Demo or Real account, start a compatible REST "
                    "or MCP bridge, then use Connect MT5 to select the matching account type."
                )
    if include_telegram and include_mt5:
        model = _model_router().status()
        model_state = "connected" if app.state.model_connected else "configured"
        parts.insert(
            0,
            f"AI model is {model_state} as {model['model']} ({model['provider']}).",
        )
    return AgentChatResponse(reply=" ".join(parts), action="STATUS")


def _tool_name_from_reply(reply: str) -> str | None:
    patterns = (
        r"<function\s*=\s*([a-zA-Z0-9_.-]+)\s*>",
        r"<function>\s*([a-zA-Z0-9_.-]+)\s*</function>",
        r'"name"\s*:\s*"([a-zA-Z0-9_.-]+)"',
    )
    if "<tool_call" not in reply.lower() and '"tool_call"' not in reply.lower():
        return None
    for pattern in patterns:
        match = re.search(pattern, reply, flags=re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return ""


async def _handle_agent_chat(
    request: AgentChatRequest,
    *,
    attachments: list[RuntimeAttachment] | None = None,
    emit: ActivityEmitter | None = None,
) -> AgentChatResponse:
    message = request.message.strip()
    lowered = message.lower()
    await _emit_activity(
        emit,
        "understand",
        "Understood the request",
        detail="Classified intent and checked safety boundaries",
    )
    wants_disconnect = bool(re.search(r"\b(disconnect|unlink|remove|forget)\b", lowered))
    wants_connect = bool(
        re.search(r"\b(connect|link|configure|pair)\b", lowered)
        or re.search(r"\bset\s*up\b", lowered)
    )
    mentions_telegram = "telegram" in lowered
    mentions_mt5 = bool(re.search(r"\b(mt5|metatrader(?:\s*5)?)\b", lowered))
    mentions_phone = bool(re.search(r"\b(phone|android|mobile|pair)\b", lowered))
    mentions_hermes = "hermes" in lowered
    mentions_model = bool(re.search(r"\b(model|provider|ai gateway)\b", lowered))
    asks_connection_state = bool(
        re.search(r"\b(connected|connection|connections|status|online|offline)\b", lowered)
        and (mentions_telegram or mentions_mt5 or "connections" in lowered)
        and not wants_connect
        and not wants_disconnect
    )

    if wants_disconnect and (
        "all connections" in lowered or "everything" in lowered
    ):
        await _emit_activity(emit, "connections", "Removed saved gateway connections")
        _gateways().disconnect_telegram()
        _gateways().disconnect_mt5()
        return AgentChatResponse(
            reply="Telegram and MT5 are disconnected, and their saved credentials were removed.",
            action="CONNECTION_CHANGED",
        )
    if wants_disconnect and mentions_telegram:
        await _emit_activity(emit, "telegram", "Removed the Telegram gateway")
        _gateways().disconnect_telegram()
        return AgentChatResponse(
            reply="Telegram is disconnected, and its saved bot credentials were removed.",
            action="CONNECTION_CHANGED",
        )
    if wants_disconnect and mentions_mt5:
        await _emit_activity(emit, "mt5", "Removed the MT5 gateway")
        _gateways().disconnect_mt5()
        return AgentChatResponse(
            reply="MT5 is disconnected, and its saved gateway credentials were removed.",
            action="CONNECTION_CHANGED",
        )
    if wants_connect and mentions_telegram:
        await _emit_activity(emit, "telegram", "Prepared guided Telegram setup")
        connected = _gateways().status()["telegram"]["connected"]
        return AgentChatResponse(
            reply=(
                "Telegram is already connected. Enter new details below to replace the "
                "current bot, or cancel to keep it."
                if connected
                else "I can connect Telegram now. Enter the bot token and the one chat ID "
                "allowed to control me; I will validate both with Telegram."
            ),
            action="CONNECTION_SETUP",
            client_action="CONNECT_TELEGRAM",
        )
    if wants_connect and mentions_mt5:
        await _emit_activity(emit, "mt5", "Prepared guided MT5 setup")
        connected = _gateways().status()["mt5"]["connected"]
        return AgentChatResponse(
            reply=(
                "MT5 is already connected. Enter another gateway below to replace it, "
                "or cancel to keep the current connection."
                if connected
                else "I can connect MT5 now. Choose MCP or REST and enter the gateway URL; "
                "I will run a real protocol check before saving it."
            ),
            action="CONNECTION_SETUP",
            client_action="CONNECT_MT5",
        )
    if wants_connect and mentions_phone:
        await _emit_activity(emit, "phone", "Created a phone pairing handoff")
        return AgentChatResponse(
            reply=(
                "I can pair your Android phone now. I will create a one-use QR code "
                "linked to this local Soki workspace."
            ),
            action="CONNECTION_SETUP",
            client_action="PAIR_PHONE",
        )
    if wants_connect and mentions_hermes:
        await _emit_activity(emit, "hermes", "Opened Hermes runtime setup")
        return AgentChatResponse(
            reply=(
                "I can configure the Hermes runtime. Enter its local or remote URL, "
                "API key, and model; I will save them locally and run a health check."
            ),
            action="CONNECTION_SETUP",
            client_action="CONNECT_HERMES",
        )
    if wants_connect and mentions_model:
        await _emit_activity(emit, "model", "Opened fallback model setup")
        return AgentChatResponse(
            reply=(
                "I can connect an AI provider. Add its API key and base URL, scan the live "
                "model catalog, then choose the model you want me to use."
            ),
            action="CONNECTION_SETUP",
            client_action="CONNECT_MODEL",
        )
    if asks_connection_state:
        await _emit_activity(emit, "connections", "Read current connection state")
        return _connection_status_response(
            include_telegram=mentions_telegram or not mentions_mt5,
            include_mt5=mentions_mt5 or not mentions_telegram,
        )
    if any(
        phrase in lowered
        for phrase in (
            "connection status",
            "connections status",
            "what is connected",
            "what's connected",
            "show connections",
        )
    ):
        await _emit_activity(emit, "connections", "Read current connection state")
        return _connection_status_response()
    if request.experiment_id is not None and any(
        phrase in lowered for phrase in ("report", "result", "status", "how is", "what happened")
    ):
        await _emit_activity(emit, "report", "Loaded the current research report")
        experiment = _repository().get_experiment(request.experiment_id)
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        if experiment.report is None:
            return AgentChatResponse(
                reply=(
                    f"The study is currently {experiment.state}. I will show the report here "
                    "as soon as deterministic risk review finishes."
                ),
                action="STATUS",
                experiment_id=experiment.experiment_id,
                state=experiment.state,
            )
        report = experiment.report
        ranked = sorted(
            report.statistical_results,
            key=lambda item: item.robustness_score,
            reverse=True,
        )
        best = ranked[0]
        backtest = next(item for item in report.backtests if item.strategy_id == best.strategy_id)
        decision = "eligible for paper review" if report.risk_decision.eligible else "blocked"
        reason_labels = {
            "portfolio_not_empty": "no candidate met the portfolio threshold",
            "drawdown_within_limit": "drawdown breached the risk limit",
            "minimum_trade_count": "too few validated trades",
            "overfitting_within_limit": "overfitting risk was too high",
            "stress_tests_passed": "execution stress tests failed",
            "human_approval_present": "paper approval has not been granted",
        }
        reasons = [
            reason_labels.get(reason, reason.replace("_", " "))
            for reason in report.risk_decision.rejection_reasons
        ]
        return AgentChatResponse(
            reply=(
                f"The study finished and risk marked it {decision}. The strongest candidate "
                f"was {best.strategy_id} with robustness {best.robustness_score:.3f}, "
                f"net return {backtest.metrics.net_return * 100:.2f}%, maximum drawdown "
                f"{backtest.metrics.maximum_drawdown * 100:.2f}%, and "
                f"{backtest.metrics.number_of_trades} trades. "
                f"Risk notes: {', '.join(reasons) or 'none'}."
            ),
            action="REPORT",
            experiment_id=experiment.experiment_id,
            state=experiment.state,
        )
    if re.search(r"^\s*(run|start|backtest|test|research)\b", lowered) or any(
        phrase in lowered
        for phrase in ("run a backtest", "test this strategy", "test a strategy", "start a study")
    ):
        await _emit_activity(
            emit,
            "research",
            "Prepared deterministic market research",
            detail="Parsed symbol, timeframe, and study objective",
        )
        symbol_match = re.search(
            r"\b(EURUSD|GBPUSD|USDJPY|AUDUSD|USDCAD|USDCHF|NZDUSD|BTCUSD|ETHUSD)\b",
            message.upper(),
        )
        timeframe_match = re.search(r"\b(M5|M15|M30|H1|H4|D1)\b", message.upper())
        symbol = symbol_match.group(1) if symbol_match else "EURUSD"
        timeframe = timeframe_match.group(1) if timeframe_match else "M15"
        objective = _orchestrator().create_objective(
            ResearchObjectiveCreate(
                title=f"{symbol} {timeframe} agent study",
                thesis=(
                    message
                    if len(message) >= 12
                    else f"Test robust deterministic strategies for {symbol} on {timeframe}."
                ),
                symbols=[symbol],
                timeframe=cast(Any, timeframe),
            )
        )
        experiment = _orchestrator().create_experiment(
            ExperimentCreate(objective_id=objective.objective_id, seed=42)
        )
        _orchestrator().start(experiment.experiment_id)
        await _emit_activity(
            emit,
            "backtest",
            "Started the backtest and risk pipeline",
            detail=f"{symbol} {timeframe} · research and paper only",
        )
        return AgentChatResponse(
            reply=(
                f"I started a real-data {symbol} {timeframe} study. I will generate typed "
                "candidates, backtest them, attack them with cost stress, and apply the risk "
                "rules. You can ask “show me the report” when it finishes."
            ),
            action="EXPERIMENT_STARTED",
            experiment_id=experiment.experiment_id,
            state=experiment.state,
        )
    try:
        work_label = ""
        completed_work_label = ""
        if re.search(
            r"\b(code|coding|debug|implement|refactor|program|script|function|class)\b",
            lowered,
        ):
            work_label = "Preparing a coding response"
            completed_work_label = "Finished the coding response"
        elif re.search(r"\b(write|draft|rewrite|edit|compose|document|copy)\b", lowered):
            work_label = "Writing the requested content"
            completed_work_label = "Finished the requested writing"
        if work_label:
            await _emit_activity(emit, "work", work_label, state="running")
        runtime_label = (
            "Calling the Hermes agent runtime"
            if _hermes_runtime().healthy
            else "Calling the configured fallback model"
        )
        await _emit_activity(
            emit,
            "runtime",
            runtime_label,
            state="running",
            detail=f"{len(attachments or [])} attachment(s)" if attachments else "",
        )
        runtime_reply = await _agent_runtime().chat(
            message,
            history=[item.model_dump() for item in request.history],
            session_id=request.session_id,
            attachments=attachments,
        )
        reply = runtime_reply.text
        await _emit_activity(
            emit,
            "runtime",
            "Received the agent response",
            detail=runtime_reply.runtime,
        )
        if completed_work_label:
            await _emit_activity(emit, "work", completed_work_label)
    except (httpx.HTTPError, ValueError) as error:
        app.state.model_connected = False
        raise HTTPException(status_code=502, detail=str(error)) from error
    app.state.model_connected = True
    tool_name = _tool_name_from_reply(reply)
    await _emit_activity(
        emit,
        "inspect",
        "Checked the response for safe tool actions",
    )
    if tool_name in {"list_connections", "connection_status", "get_connections"}:
        return _connection_status_response()
    if tool_name in {"connect_telegram", "telegram_connect"}:
        return AgentChatResponse(
            reply="I can connect Telegram. Enter the secure bot details below.",
            action="CONNECTION_SETUP",
            client_action="CONNECT_TELEGRAM",
        )
    if tool_name in {"connect_mt5", "mt5_connect"}:
        return AgentChatResponse(
            reply="I can connect MT5. Enter the MCP or REST gateway details below.",
            action="CONNECTION_SETUP",
            client_action="CONNECT_MT5",
        )
    if tool_name is not None:
        return AgentChatResponse(
            reply=(
                "I could not safely complete that tool request. Please name the action "
                "directly—for example, “show connection status”, “connect MT5”, or "
                "“connect Telegram”."
            ),
            action="MESSAGE",
        )
    if not reply.strip():
        raise HTTPException(status_code=502, detail="model provider returned an empty response")
    return AgentChatResponse(
        reply=reply,
        action="MESSAGE",
        session_id=runtime_reply.session_id,
        runtime=runtime_reply.runtime,
    )


async def _telegram_agent_loop(application: FastAPI) -> None:
    offset = 0
    experiments: dict[str, UUID] = {}
    while True:
        manager = cast(GatewayManager, application.state.gateways)
        connection = manager.telegram_connection()
        if connection is None:
            await asyncio.sleep(2)
            continue
        base_url = f"https://api.telegram.org/bot{connection.token}"
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.get(
                    f"{base_url}/getUpdates",
                    params={"timeout": 20, "offset": offset, "allowed_updates": '["message"]'},
                )
                response.raise_for_status()
                body = response.json()
                updates = body.get("result", []) if isinstance(body, dict) else []
                for update in updates:
                    if not isinstance(update, dict):
                        continue
                    offset = max(offset, int(update.get("update_id", 0)) + 1)
                    message = update.get("message", {})
                    if not isinstance(message, dict) or not isinstance(message.get("text"), str):
                        continue
                    chat_payload = message.get("chat", {})
                    if not isinstance(chat_payload, dict):
                        continue
                    chat_id = str(chat_payload.get("id", ""))
                    if chat_id != connection.chat_id:
                        continue
                    try:
                        agent_response = await _handle_agent_chat(
                            AgentChatRequest(
                                message=message["text"],
                                history=[],
                                experiment_id=experiments.get(chat_id),
                            )
                        )
                        if agent_response.experiment_id is not None:
                            experiments[chat_id] = agent_response.experiment_id
                        reply = agent_response.reply
                    except Exception as error:
                        logger.exception("telegram.agent_failed", error=str(error))
                        reply = "I could not complete that request. Check soki code setup."
                    send = await client.post(
                        f"{base_url}/sendMessage",
                        json={"chat_id": chat_id, "text": reply},
                    )
                    send.raise_for_status()
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("telegram.poll_failed", error_type=type(error).__name__)
            await asyncio.sleep(3)


async def _proven_agent_chat(
    request: AgentChatRequest,
    *,
    attachment_owner: str = "local",
    emit: ActivityEmitter | None = None,
) -> AgentChatResponse:
    await _emit_activity(
        emit,
        "proof",
        "Opened a proof record",
        state="running",
        detail=request.session_id[-12:],
    )
    task = _proof_ledger().start(session_id=request.session_id, request=request.message)
    try:
        response = await _handle_agent_chat(
            request,
            attachments=_runtime_attachments(
                request.attachment_ids,
                owner=attachment_owner,
            ),
            emit=emit,
        )
    except Exception as error:
        _proof_ledger().fail(task, str(error))
        raise
    proof = _proof_ledger().finish(
        task,
        response=response.reply,
        action=response.action,
        runtime=response.runtime,
        experiment_id=response.experiment_id,
    )
    await _emit_activity(
        emit,
        "proof",
        "Verified and saved the result",
        detail=f"task {str(proof.task_id)[:8]} · {proof.status.lower()}",
    )
    return response.model_copy(
        update={
            "session_id": response.session_id or request.session_id,
            "task_id": proof.task_id,
            "proof": proof,
        }
    )


@app.post("/agent/chat", response_model=AgentChatResponse, tags=["agent"])
async def agent_chat(request: AgentChatRequest) -> AgentChatResponse:
    return await _proven_agent_chat(request, attachment_owner="local")


@app.post("/agent/chat/stream", tags=["agent"])
async def agent_chat_stream(request: AgentChatRequest) -> StreamingResponse:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def emit(
        activity_id: str,
        label: str,
        state: str,
        detail: str,
    ) -> None:
        await queue.put(
            {
                "type": "activity",
                "activity": {
                    "id": activity_id,
                    "label": label,
                    "state": state,
                    "detail": detail,
                },
            }
        )

    async def run() -> None:
        try:
            response = await _proven_agent_chat(
                request,
                attachment_owner="local",
                emit=emit,
            )
            await queue.put(
                {
                    "type": "result",
                    "response": response.model_dump(mode="json"),
                }
            )
        except HTTPException as error:
            await queue.put(
                {
                    "type": "error",
                    "status": error.status_code,
                    "detail": error.detail,
                }
            )
        except Exception as error:
            logger.exception("agent.stream_failed", error=str(error))
            await queue.put(
                {
                    "type": "error",
                    "status": 500,
                    "detail": "The agent could not complete this request.",
                }
            )
        finally:
            await queue.put(None)

    async def events() -> AsyncIterator[str]:
        worker = asyncio.create_task(run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield json.dumps(event, separators=(",", ":")) + "\n"
        finally:
            if not worker.done():
                worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    return StreamingResponse(events(), media_type="application/x-ndjson")


@app.post(
    "/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["attachments"],
)
async def upload_attachment(
    request: Request,
    file: Annotated[UploadFile, File()],
) -> AttachmentResponse:
    _require_local_request(request)
    return _attachment_response(await _store_attachment(file, owner="local"))


@app.get("/attachments", response_model=list[AttachmentResponse], tags=["attachments"])
async def list_attachments(request: Request) -> list[AttachmentResponse]:
    _require_local_request(request)
    return [
        _attachment_response(item)
        for item in _repository().list_attachments(owner="local")
    ]


@app.get("/attachments/{attachment_id}", tags=["attachments"])
async def download_attachment(attachment_id: UUID, request: Request) -> FileResponse:
    _require_local_request(request)
    attachment = _repository().get_attachment(attachment_id, owner="local")
    if attachment is None:
        raise HTTPException(status_code=404, detail="attachment not found")
    path = Path(attachment.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="attachment is no longer available")
    return FileResponse(path, media_type=attachment.media_type, filename=attachment.name)


@app.get("/agent/tasks", response_model=list[AgentTask], tags=["agent"])
async def list_agent_tasks(limit: Annotated[int, Query(ge=1, le=100)] = 25) -> list[AgentTask]:
    return _repository().list_agent_tasks(limit=limit)


@app.get("/agent/tasks/{task_id}", response_model=AgentTask, tags=["agent"])
async def get_agent_task(task_id: UUID) -> AgentTask:
    task = _repository().get_agent_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="agent task not found")
    return task


@app.get("/mobile/status", tags=["mobile"])
async def mobile_status(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    device = _authenticated_device(authorization)
    return {
        "agent": "soki code",
        "device": device,
        "hermes": _hermes_runtime().status(),
        "execution": "RESEARCH_AND_PAPER_ONLY",
    }


@app.post("/mobile/chat", response_model=AgentChatResponse, tags=["mobile"])
async def mobile_chat(
    request: AgentChatRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> AgentChatResponse:
    device = _authenticated_device(authorization)
    safe_request = request.model_copy(
        update={
            "session_id": (
                request.session_id
                if request.session_id.startswith(f"mobile-{device['device_id']}-")
                else f"mobile-{device['device_id']}-{uuid4().hex}"
            )
        }
    )
    return await _proven_agent_chat(
        safe_request,
        attachment_owner=f"device:{device['device_id']}",
    )


@app.post(
    "/mobile/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["mobile"],
)
async def upload_mobile_attachment(
    file: Annotated[UploadFile, File()],
    authorization: Annotated[str | None, Header()] = None,
) -> AttachmentResponse:
    device = _authenticated_device(authorization)
    attachment = await _store_attachment(
        file,
        owner=f"device:{device['device_id']}",
    )
    return _attachment_response(attachment, mobile=True)


@app.get("/mobile/attachments", response_model=list[AttachmentResponse], tags=["mobile"])
async def list_mobile_attachments(
    authorization: Annotated[str | None, Header()] = None,
) -> list[AttachmentResponse]:
    device = _authenticated_device(authorization)
    return [
        _attachment_response(item, mobile=True)
        for item in _repository().list_attachments(owner=f"device:{device['device_id']}")
    ]


@app.get("/mobile/attachments/{attachment_id}", tags=["mobile"])
async def download_mobile_attachment(
    attachment_id: UUID,
    authorization: Annotated[str | None, Header()] = None,
) -> FileResponse:
    device = _authenticated_device(authorization)
    attachment = _repository().get_attachment(
        attachment_id,
        owner=f"device:{device['device_id']}",
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="attachment not found")
    path = Path(attachment.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="attachment is no longer available")
    return FileResponse(path, media_type=attachment.media_type, filename=attachment.name)


@app.get("/mobile/tasks", response_model=list[AgentTask], tags=["mobile"])
async def mobile_tasks(
    authorization: Annotated[str | None, Header()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[AgentTask]:
    _authenticated_device(authorization)
    return _repository().list_agent_tasks(limit=limit)


@app.post("/chat", response_model=ChatResponse, tags=["models"])
async def chat(request: ChatRequest) -> ChatResponse:
    transcript = "\n".join(f"{item.role.upper()}: {item.content}" for item in request.history[-20:])
    prompt = f"{transcript}\nUSER: {request.message}" if transcript else request.message
    router = _model_router()
    try:
        reply = await router.complete(prompt)
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(status_code=502, detail=f"model provider failed: {error}") from error
    status_payload = router.status()
    return ChatResponse(
        reply=reply,
        provider=str(status_payload["provider"]),
        model=str(status_payload["model"]),
        mock=bool(router.configuration.is_mock),
    )


@app.get("/mt5/status", tags=["mt5"])
async def mt5_status() -> dict[str, str | bool]:
    return cast(dict[str, str | bool], app.state.mt5.health_check())


@app.get("/mt5/local-status", tags=["mt5"])
async def local_mt5_status() -> dict[str, str | bool]:
    application_path = _local_mt5_terminal()
    installed = application_path is not None
    gateway = _gateways().status()["mt5"]
    return {
        "platform": platform,
        "installed": installed,
        "application_path": str(application_path) if application_path is not None else "",
        "gateway_connected": bool(gateway["connected"]),
        "account_mode": str(gateway["account_mode"]),
        "account_mode_source": str(gateway["account_mode_source"]),
        "read_only": bool(gateway["read_only"]),
        "bridge_required": not bool(gateway["connected"]),
    }


async def _event_socket(websocket: WebSocket, experiment_id: UUID | None) -> None:
    await websocket.accept()
    if experiment_id is not None:
        if _repository().get_experiment(experiment_id) is None:
            await websocket.close(code=4404, reason="experiment not found")
            return
        for event in _repository().events(experiment_id):
            await websocket.send_json(event.model_dump(mode="json"))
    queue = _orchestrator().events.subscribe(experiment_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        _orchestrator().events.unsubscribe(queue, experiment_id)


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    await _event_socket(websocket, None)


@app.websocket("/ws/experiments/{experiment_id}")
async def websocket_experiment(websocket: WebSocket, experiment_id: UUID) -> None:
    await _event_socket(websocket, experiment_id)
