"""Concrete HTTP transport for Ollama-compatible providers using httpx."""

from __future__ import annotations

from dataclasses import dataclass

from contextforge.adapters.providers.ollama import HttpResponse, OllamaHttpTransport


@dataclass(frozen=True, slots=True)
class HttpxOllamaTransport(OllamaHttpTransport):
    """Send bounded requests to an Ollama-compatible HTTP endpoint."""

    endpoint: str
    timeout_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, str) or not self.endpoint.strip():
            raise ValueError("endpoint must be a non-empty string")
        if not isinstance(self.timeout_seconds, (int, float)):
            raise TypeError("timeout_seconds must be numeric")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None,
        headers: tuple[tuple[str, str], ...],
        timeout_seconds: float,
    ) -> HttpResponse:
        """Execute one bounded HTTP request without exposing transport details."""
        import httpx

        if method not in ("GET", "POST"):
            raise ValueError(f"unsupported HTTP method: {method}")
        if not path.startswith("/"):
            raise ValueError("path must start with '/'")
        url = self._url(path)
        header_dict = dict(headers)
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        try:
            response = httpx.request(
                method,
                url,
                content=body,
                headers=header_dict,
                timeout=effective_timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException as error:
            raise TimeoutError("Ollama-compatible request timed out.") from error
        except (httpx.ConnectError, httpx.NetworkError) as error:
            raise OSError("Ollama-compatible provider is unreachable.") from error
        except httpx.HTTPError as error:
            raise OSError("Ollama-compatible HTTP request failed.") from error
        return HttpResponse(response.status_code, response.content)

    def _url(self, path: str) -> str:
        base = self.endpoint.rstrip("/")
        return f"{base}{path}"
