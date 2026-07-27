"""Tests for the httpx-based Ollama-compatible transport."""

import httpx
import pytest

from contextforge.adapters.providers import HttpResponse, HttpxOllamaTransport


def test_transport_returns_normalized_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_request(
        method: str,
        url: str,
        *,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float,
        follow_redirects: bool,
    ) -> httpx.Response:
        assert method == "GET"
        assert url == "http://localhost:11434/api/version"
        assert headers == {"Accept": "application/json"}
        assert timeout == 5.0
        assert follow_redirects is False
        return httpx.Response(200, content=b'{"version":"0.9.1"}')

    monkeypatch.setattr("httpx.request", _fake_request)
    transport = HttpxOllamaTransport("http://localhost:11434", 5.0)

    response = transport.request(
        "GET",
        "/api/version",
        body=None,
        headers=(("Accept", "application/json"),),
        timeout_seconds=5.0,
    )

    assert isinstance(response, HttpResponse)
    assert response.status_code == 200
    assert response.body == b'{"version":"0.9.1"}'


def test_transport_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_request(
        method: str,
        url: str,
        *,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float,
        follow_redirects: bool,
    ) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(200, content=b"{}")

    monkeypatch.setattr("httpx.request", _fake_request)
    transport = HttpxOllamaTransport("http://localhost:11434/", 5.0)
    transport.request(
        "GET",
        "/api/tags",
        body=None,
        headers=(),
        timeout_seconds=5.0,
    )

    assert captured["url"] == "http://localhost:11434/api/tags"


def test_transport_preserves_custom_base_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_request(
        method: str,
        url: str,
        *,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float,
        follow_redirects: bool,
    ) -> httpx.Response:
        captured["url"] = url
        return httpx.Response(200, content=b"{}")

    monkeypatch.setattr("httpx.request", _fake_request)
    transport = HttpxOllamaTransport("http://localhost:11434/ollama", 5.0)
    transport.request(
        "GET",
        "/api/version",
        body=None,
        headers=(),
        timeout_seconds=5.0,
    )

    assert captured["url"] == "http://localhost:11434/ollama/api/version"


def test_transport_converts_httpx_timeout_to_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_request(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr("httpx.request", _fake_request)
    transport = HttpxOllamaTransport("http://localhost:11434", 5.0)

    with pytest.raises(TimeoutError):
        transport.request(
            "GET",
            "/api/version",
            body=None,
            headers=(),
            timeout_seconds=5.0,
        )


def test_transport_converts_connect_error_to_os_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_request(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("httpx.request", _fake_request)
    transport = HttpxOllamaTransport("http://localhost:11434", 5.0)

    with pytest.raises(OSError):
        transport.request(
            "GET",
            "/api/version",
            body=None,
            headers=(),
            timeout_seconds=5.0,
        )


def test_transport_rejects_invalid_endpoint() -> None:
    with pytest.raises(ValueError, match="endpoint must be a non-empty string"):
        HttpxOllamaTransport("", 5.0)


def test_transport_rejects_invalid_timeout() -> None:
    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        HttpxOllamaTransport("http://localhost:11434", 0.0)


def test_transport_rejects_non_numeric_timeout() -> None:
    with pytest.raises(TypeError, match="timeout_seconds must be numeric"):
        HttpxOllamaTransport("http://localhost:11434", "fast")  # type: ignore[arg-type]


def test_transport_rejects_unsupported_method() -> None:
    transport = HttpxOllamaTransport("http://localhost:11434", 5.0)
    with pytest.raises(ValueError, match="unsupported HTTP method"):
        transport.request(
            "DELETE",
            "/api/tags",
            body=None,
            headers=(),
            timeout_seconds=5.0,
        )


def test_transport_rejects_path_without_leading_slash() -> None:
    transport = HttpxOllamaTransport("http://localhost:11434", 5.0)
    with pytest.raises(ValueError, match="path must start with"):
        transport.request(
            "GET",
            "api/version",
            body=None,
            headers=(),
            timeout_seconds=5.0,
        )


def test_transport_uses_request_timeout_when_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_request(
        method: str,
        url: str,
        *,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float,
        follow_redirects: bool,
    ) -> httpx.Response:
        captured["timeout"] = timeout
        return httpx.Response(200, content=b"{}")

    monkeypatch.setattr("httpx.request", _fake_request)
    transport = HttpxOllamaTransport("http://localhost:11434", 30.0)
    transport.request(
        "GET",
        "/api/version",
        body=None,
        headers=(),
        timeout_seconds=7.5,
    )

    assert captured["timeout"] == 7.5


def test_transport_follow_redirects_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_request(
        method: str,
        url: str,
        *,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float,
        follow_redirects: bool,
    ) -> httpx.Response:
        captured["follow_redirects"] = follow_redirects
        return httpx.Response(200, content=b"{}")

    monkeypatch.setattr("httpx.request", _fake_request)
    transport = HttpxOllamaTransport("http://localhost:11434", 5.0)
    transport.request(
        "GET",
        "/api/version",
        body=None,
        headers=(),
        timeout_seconds=5.0,
    )

    assert captured["follow_redirects"] is False
