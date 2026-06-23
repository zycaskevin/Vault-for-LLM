"""Extended tests for vault/privacy.py"""
import pytest


class TestRedactedSpan:
    def test_redacted_span_short(self):
        """Test short snippet gets full redaction."""
        from vault.privacy import _redacted_span
        result = _redacted_span("hello world", 0, 5)  # "hello" is 5 chars <= 8
        assert result == "[REDACTED]"

    def test_redacted_span_long(self):
        """Test longer snippet gets partial redaction."""
        from vault.privacy import _redacted_span
        result = _redacted_span("abcdefghij", 0, 10)  # 10 chars > 8
        assert result.startswith("abc")
        assert result.endswith("hij")
        assert "…" in result

    def test_redacted_span_exactly_eight(self):
        """Test exactly 8 chars gets full redaction."""
        from vault.privacy import _redacted_span
        result = _redacted_span("12345678", 0, 8)
        assert result == "[REDACTED]"


class TestScanPrivacy:
    def test_scan_privacy_no_secrets(self):
        from vault.privacy import scan_privacy
        result = scan_privacy("Hello, this is a normal text.")
        assert result["status"] == "pass"
        assert len(result["findings"]) == 0

    def test_scan_privacy_with_api_key(self):
        from vault.privacy import scan_privacy
        result = scan_privacy("api_key = sk-1234567890abcdefghij")
        assert result["status"] == "fail"
        assert len(result["findings"]) > 0

    def test_scan_privacy_with_standalone_openai_key(self):
        from vault.privacy import scan_privacy
        result = scan_privacy("Use sk-proj-1234567890abcdefghij1234567890 only in env vars.")
        assert result["status"] == "fail"
        assert any(item["type"] == "openai_api_key" for item in result["findings"])

    def test_scan_privacy_with_password(self):
        from vault.privacy import scan_privacy
        result = scan_privacy("password = mysecretpass123")
        assert result["status"] == "fail"
        assert len(result["findings"]) > 0

    def test_scan_privacy_with_email(self):
        from vault.privacy import scan_privacy
        result = scan_privacy("Contact me at test@example.com")
        assert result["status"] == "warn"
        assert len(result["findings"]) > 0

    def test_scan_privacy_with_phone(self):
        from vault.privacy import scan_privacy
        result = scan_privacy("Call me at +1-555-123-4567")
        assert result["status"] == "warn"

    def test_scan_privacy_with_url_secret(self):
        from vault.privacy import scan_privacy
        result = scan_privacy("Check https://example.com?token=secret123")
        assert result["status"] == "warn"

    def test_scan_privacy_with_github_token(self):
        from vault.privacy import scan_privacy
        result = scan_privacy("ghp_abcdefghijklmnopqrstuvwxyz0123456789")
        assert result["status"] == "fail"

    def test_scan_privacy_with_bearer_token(self):
        from vault.privacy import scan_privacy
        result = scan_privacy("Authorization: Bearer abcdef1234567890")
        assert result["status"] == "fail"

    def test_scan_privacy_empty_text(self):
        from vault.privacy import scan_privacy
        result = scan_privacy("")
        assert result["status"] == "pass"

    def test_scan_privacy_none(self):
        from vault.privacy import scan_privacy
        result = scan_privacy(None)
        assert result["status"] == "pass"


class TestRedactSecrets:
    def test_redact_secrets_no_secrets(self):
        from vault.privacy import redact_secrets
        text = "Hello world, nothing secret here."
        result = redact_secrets(text)
        assert result == text

    def test_redact_secrets_with_api_key(self):
        from vault.privacy import redact_secrets
        text = "api_key = sk-1234567890abcdefghij"
        result = redact_secrets(text)
        assert "[REDACTED]" in result
        assert "sk-1234567890abcdefghij" not in result

    def test_redact_secrets_with_standalone_openai_key(self):
        from vault.privacy import redact_secrets
        token = "sk-proj-1234567890abcdefghij1234567890"
        result = redact_secrets(f"Never store {token} in memory.")
        assert "[REDACTED]" in result
        assert token not in result

    def test_redact_secrets_with_github_token(self):
        from vault.privacy import redact_secrets
        text = "My token: ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        result = redact_secrets(text)
        assert "[REDACTED]" in result
        assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in result

    def test_redact_secrets_empty(self):
        from vault.privacy import redact_secrets
        result = redact_secrets("")
        assert result == ""

    def test_redact_secrets_none(self):
        from vault.privacy import redact_secrets
        result = redact_secrets(None)
        assert result == ""


class TestPrivacyGate:
    def test_privacy_gate_alias(self):
        from vault.privacy import privacy_gate, scan_privacy
        text = "Test with api_key = abc123def456ghi789"
        assert privacy_gate(text) == scan_privacy(text)
