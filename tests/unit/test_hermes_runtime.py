import json

import httpx
from qforge.hermes_runtime import HermesRuntimeClient


async def test_hermes_runtime_probes_and_preserves_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer local-secret"
        if request.url.path == "/v1/capabilities":
            return httpx.Response(
                200,
                json={
                    "platform": "hermes-agent",
                    "runtime": {"tool_execution": "server"},
                    "features": {
                        "chat_completions_streaming": True,
                        "approval_events": True,
                    },
                },
            )
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["x-hermes-session-id"] == "session-7"
        body = json.loads(request.content)
        assert body["model"] == "hermes-agent"
        assert body["messages"][-1]["content"] == "Finish the task"
        stream = "\n\n".join(
            (
                'event: hermes.tool.progress\ndata: {"tool":"terminal","label":"Run tests",'
                '"toolCallId":"call-1","status":"running"}',
                'event: hermes.tool.progress\ndata: {"tool":"terminal",'
                '"toolCallId":"call-1","status":"completed"}',
                'data: {"choices":[{"delta":{"content":"Task verified."},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
                "data: [DONE]",
                "",
            )
        )
        return httpx.Response(
            200,
            headers={"X-Hermes-Session-Id": "session-7"},
            text=stream,
        )

    client = HermesRuntimeClient(
        base_url="http://hermes.local:8642",
        api_key="local-secret",
        model="hermes-agent",
        timeout_seconds=10,
        transport=httpx.MockTransport(handler),
    )

    assert await client.probe() is True
    activities: list[tuple[str, str, str, str]] = []

    async def activity(
        activity_id: str,
        label: str,
        state: str,
        detail: str,
    ) -> None:
        activities.append((activity_id, label, state, detail))

    reply = await client.chat(
        "Finish the task",
        history=[],
        session_id="session-7",
        on_activity=activity,
    )

    assert reply.text == "Task verified."
    assert reply.runtime == "hermes-agent"
    assert reply.session_id == "session-7"
    assert reply.completed is True
    assert activities == [
        ("hermes:call-1", "Run tests", "running", "terminal"),
        ("hermes:call-1", "Finished terminal", "completed", "terminal"),
    ]
