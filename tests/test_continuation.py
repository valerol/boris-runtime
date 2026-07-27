import pytest

from application.continuation import (
    ContinuationCodec,
    ContinuationUnavailable,
    InvalidContinuationToken,
    continuation_expiry_iso,
)


def test_continuation_codec_round_trips_signed_state():
    codec = ContinuationCodec(
        "test-secret-" * 4,
        ttl_seconds=600,
        clock=lambda: 1000,
    )

    token, claims = codec.issue({
        "session_id": "session-1",
        "resume_count": 0,
        "semantic_input": {"phase": "C03"},
    })

    assert codec.verify(token) == claims
    assert claims["version"] == "boris-continuation/1.4"
    assert claims["issued_at"] == 1000
    assert claims["expires_at"] == 1600
    assert continuation_expiry_iso(claims) == (
        "1970-01-01T00:26:40+00:00"
    )


def test_continuation_codec_rejects_tampering():
    codec = ContinuationCodec("test-secret-" * 4, clock=lambda: 1000)
    token, _claims = codec.issue({"session_id": "session-1"})
    prefix, payload, signature = token.split(".")
    replacement = "A" if payload[10] != "A" else "B"
    tampered = (
        f"{prefix}.{payload[:10]}{replacement}{payload[11:]}.{signature}"
    )

    with pytest.raises(
        InvalidContinuationToken,
        match="signature is invalid",
    ):
        codec.verify(tampered)


def test_continuation_codec_rejects_expired_token():
    now = [1000]
    codec = ContinuationCodec(
        "test-secret-" * 4,
        ttl_seconds=60,
        clock=lambda: now[0],
    )
    token, _claims = codec.issue({"session_id": "session-1"})
    now[0] = 1060

    with pytest.raises(
        InvalidContinuationToken,
        match="has expired",
    ):
        codec.verify(token)


def test_continuation_codec_requires_server_secret(monkeypatch):
    monkeypatch.delenv("BORIS_CONTINUATION_SECRET", raising=False)

    with pytest.raises(
        ContinuationUnavailable,
        match="at least 32 bytes",
    ):
        ContinuationCodec.from_environment()
