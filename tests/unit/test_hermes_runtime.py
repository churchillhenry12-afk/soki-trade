import json

import httpx
from qforge.hermes_runtime import HermesRuntimeClient


async def test_hermes_runtime_probes_and_preserves_session() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer local-secret"
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["x-hermes-session-id"] == "session-7"
        body = json.loads(request.content)
        assert body["model"] == "hermes-agent"
        assert body["messages"][-1]["content"] == "Finish the task"
        return httpx.Response(
            200,
            headers={
                "X-Hermes-Session-Id": "session-7",
                "X-Hermes-Completed": "true",
            },
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "Task verified."}}
                ]
            },
        )

    client = HermesRuntimeClient(
        base_url="http://hermes.local:8642",
        api_key="local-secret",
        model="hermes-agent",
        timeout_seconds=10,
        transport=httpx.MockTransport(handler),
    )

    assert await client.probe() is True
    reply = await client.chat("Finish the task", history=[], session_id="session-7")

    assert reply.text == "Task verified."
    assert reply.runtime == "hermes-agent"
    assert reply.session_id == "session-7"
    assert reply.completed is True
