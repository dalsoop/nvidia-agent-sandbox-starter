import pytest

from agent.llm import (
    NIM_BASE_URL,
    SANDBOX_BASE_URL,
    ChatClient,
    ConfigError,
    Endpoint,
    LLMError,
    resolve_endpoint,
)
from tests.conftest import final

KEY = "nvapi-test-canary-0000"


def test_endpoint_defaults_to_nim_with_a_key_and_to_inference_local_without():
    assert resolve_endpoint(env={"NVIDIA_API_KEY": KEY}) == Endpoint(NIM_BASE_URL, KEY)
    assert resolve_endpoint(env={}) == Endpoint(SANDBOX_BASE_URL, None)


def test_inference_local_never_carries_a_key():
    endpoint = resolve_endpoint(SANDBOX_BASE_URL, env={"NVIDIA_API_KEY": KEY})
    assert endpoint.api_key is None and endpoint.mode == "sandbox"


def test_nim_without_a_key_is_a_config_error():
    with pytest.raises(ConfigError):
        resolve_endpoint(NIM_BASE_URL, env={})


def test_key_is_sent_only_as_a_bearer_header(fake_llm):
    fake_llm.reply(final("ok"))
    ChatClient(Endpoint(fake_llm.base_url, KEY), "m").complete([{"role": "user", "content": "hi"}])
    request = fake_llm.requests[0]
    assert request["path"] == "/v1/chat/completions"
    assert request["headers"]["Authorization"] == f"Bearer {KEY}"
    assert KEY not in str(request["body"])


def test_no_authorization_header_without_a_key(fake_llm):
    fake_llm.reply(final("ok"))
    ChatClient(Endpoint(fake_llm.base_url, None), "m").complete([{"role": "user", "content": "hi"}])
    assert "Authorization" not in fake_llm.requests[0]["headers"]


def test_rate_limit_is_retried_with_retry_after(fake_llm):
    fake_llm.error(429, "slow down", headers={"Retry-After": "7"})
    fake_llm.error(503, "busy")
    fake_llm.error(500, "Internal server error")  # inference.local reports upstream 503 as 500
    fake_llm.reply(final("done"))
    delays: list[float] = []
    client = ChatClient(Endpoint(fake_llm.base_url, None), "m", sleep=delays.append)
    assert client.complete([{"role": "user", "content": "hi"}])["content"] == "done"
    assert delays == [7.0, 4.0, 8.0]


def test_retries_are_bounded(fake_llm):
    for _ in range(3):
        fake_llm.error(429)
    client = ChatClient(Endpoint(fake_llm.base_url, None), "m", max_retries=2, sleep=lambda _: None)
    with pytest.raises(LLMError, match="HTTP 429"):
        client.complete([{"role": "user", "content": "hi"}])
    assert len(fake_llm.requests) == 3


def test_client_errors_are_not_retried(fake_llm):
    fake_llm.error(400, "bad request")
    client = ChatClient(Endpoint(fake_llm.base_url, None), "m", sleep=lambda _: None)
    with pytest.raises(LLMError, match="HTTP 400"):
        client.complete([{"role": "user", "content": "hi"}])
    assert len(fake_llm.requests) == 1


def test_errors_carry_the_detail_but_not_the_key(fake_llm):
    fake_llm.error(410, "model reached its end of life")
    client = ChatClient(Endpoint(fake_llm.base_url, KEY), "m")
    with pytest.raises(LLMError) as raised:
        client.complete([{"role": "user", "content": "hi"}])
    assert "end of life" in str(raised.value) and KEY not in str(raised.value)


def test_unreachable_endpoint_raises():
    client = ChatClient(Endpoint("http://127.0.0.1:9/v1", None), "m", timeout=2)
    with pytest.raises(LLMError, match="cannot reach"):
        client.complete([{"role": "user", "content": "hi"}])
