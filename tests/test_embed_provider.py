"""Embedding provider telemetry and retry tests."""

from __future__ import annotations

import json
import urllib.error


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


def test_ollama_embedding_provider_records_batch_metrics(monkeypatch):
    from vault.embed import OllamaEmbeddingProvider

    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, timeout))
        return _FakeResponse({"embeddings": [[1.0, 0.0], [0.0, 1.0]]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OllamaEmbeddingProvider(dim=None, max_retries=0)

    vectors = provider.encode(["alpha", "beta"])
    metrics = provider.get_metrics()

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert provider.dim == 2
    assert calls[0][0].endswith("/api/embed")
    assert metrics["encode_calls"] == 1
    assert metrics["encoded_texts"] == 2
    assert metrics["http_requests"] == 1
    assert metrics["http_retries"] == 0
    assert metrics["http_failures"] == 0
    assert metrics["last_latency_ms"] >= 0


def test_ollama_embedding_provider_retries_single_request(monkeypatch):
    from vault.embed import OllamaEmbeddingProvider

    attempts = {"count": 0}

    def fake_urlopen(req, timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise urllib.error.URLError("temporary")
        return _FakeResponse({"embedding": [0.5, 0.5]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OllamaEmbeddingProvider(dim=None, max_retries=1, retry_backoff=0)

    vectors = provider.encode("alpha")
    metrics = provider.get_metrics()

    assert vectors == [[0.5, 0.5]]
    assert provider.dim == 2
    assert metrics["encode_calls"] == 1
    assert metrics["encoded_texts"] == 1
    assert metrics["http_requests"] == 2
    assert metrics["http_retries"] == 1
    assert metrics["http_failures"] == 0


def test_embedding_provider_metrics_reset():
    from vault.embed import EmbeddingProvider

    provider = EmbeddingProvider(dim=3)
    provider._record_encode(2, 0)
    assert provider.get_metrics()["encode_calls"] == 1

    provider.reset_metrics()

    assert provider.get_metrics() == {
        "encode_calls": 0,
        "encoded_texts": 0,
        "http_requests": 0,
        "http_retries": 0,
        "http_failures": 0,
        "last_latency_ms": 0.0,
    }
