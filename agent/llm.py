"""OpenAI-compatible chat client built on urllib (standard library only).

Two endpoint modes:

* direct  - https://integrate.api.nvidia.com/v1 with a build.nvidia.com API key.
* sandbox - https://inference.local/v1 inside an OpenShell sandbox. No key is
  sent; OpenShell's privacy router injects provider credentials outside the
  sandbox.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
SANDBOX_BASE_URL = "https://inference.local/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
# OpenShell's inference router reports an overloaded upstream (503) to the
# sandbox as 500, so 500 is retried as well.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class ConfigError(ValueError):
    """The endpoint cannot be used as configured."""


class LLMError(RuntimeError):
    """The model call failed. Never contains credentials."""


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    api_key: str | None

    @property
    def mode(self) -> str:
        if self.base_url.rstrip("/") == SANDBOX_BASE_URL:
            return "sandbox"
        return "direct" if self.base_url.rstrip("/") == NIM_BASE_URL else "custom"


def resolve_endpoint(base_url: str | None = None, env: Mapping[str, str] = os.environ) -> Endpoint:
    key = env.get("NVIDIA_API_KEY") or None
    url = (base_url or env.get("LLM_BASE_URL") or (NIM_BASE_URL if key else SANDBOX_BASE_URL)).rstrip("/")
    if url == SANDBOX_BASE_URL:
        return Endpoint(url, None)
    if url == NIM_BASE_URL and not key:
        raise ConfigError("NVIDIA_API_KEY is required for " + NIM_BASE_URL)
    return Endpoint(url, key)


class ChatClient:
    def __init__(
        self,
        endpoint: Endpoint,
        model: str = DEFAULT_MODEL,
        *,
        timeout: float = 120.0,
        max_retries: int = 3,
        max_tokens: int = 1024,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self._sleep = sleep
        # The model that actually answered. Inside OpenShell the inference route
        # decides the model, so it can differ from the one requested.
        self.served_model: str | None = None

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": self.max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.endpoint.api_key:
            headers["Authorization"] = f"Bearer {self.endpoint.api_key}"
        url = self.endpoint.base_url + "/chat/completions"
        data = json.dumps(body).encode("utf-8")

        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as error:
                if error.code in RETRY_STATUS and attempt < self.max_retries:
                    self._sleep(_retry_delay(error, attempt))
                    continue
                raise LLMError(f"HTTP {error.code} from {url}: {_error_detail(error)}") from None
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                raise LLMError(f"cannot reach {url}: {error}") from None
            except json.JSONDecodeError:
                raise LLMError(f"non-JSON response from {url}") from None

        self.served_model = payload.get("model") or self.served_model
        try:
            return payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise LLMError("response has no choices[0].message") from None


def _retry_delay(error: urllib.error.HTTPError, attempt: int) -> float:
    retry_after = error.headers.get("Retry-After") if error.headers else None
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), 60.0)
    return float(2 ** (attempt + 1))


def _error_detail(error: urllib.error.HTTPError) -> str:
    try:
        raw = error.read().decode("utf-8", "replace")
    except OSError:
        return error.reason or ""
    try:
        parsed = json.loads(raw)
        detail = parsed.get("detail") or parsed.get("error") or parsed
    except (json.JSONDecodeError, AttributeError):
        detail = raw
    return str(detail)[:300]
