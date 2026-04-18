"""Comprehensive regression tests for security.py — zero coverage → full coverage."""

from __future__ import annotations

import pytest

from src.exceptions import SecurityError
from src.security import InputValidator, RateLimiter


# ---------------------------------------------------------------------------
# InputValidator.validate_task
# ---------------------------------------------------------------------------

class TestValidateTask:
    def test_valid_task_returned_stripped(self):
        result = InputValidator.validate_task("  Build a FastAPI endpoint  ")
        assert result == "Build a FastAPI endpoint"

    def test_empty_task_raises(self):
        with pytest.raises(SecurityError, match="cannot be empty"):
            InputValidator.validate_task("")

    def test_whitespace_only_raises(self):
        with pytest.raises(SecurityError, match="cannot be empty"):
            InputValidator.validate_task("   ")

    def test_task_exceeding_max_length_raises(self):
        long_task = "x" * 1001
        with pytest.raises(SecurityError, match="maximum length"):
            InputValidator.validate_task(long_task)

    def test_task_at_max_length_passes(self):
        task = "a" * 1000
        result = InputValidator.validate_task(task)
        assert len(result) == 1000

    def test_script_tag_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_task("Build <script>alert('xss')</script> something")

    def test_javascript_protocol_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_task("javascript:alert(1)")

    def test_vbscript_protocol_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_task("vbscript:MsgBox(1)")

    def test_eval_call_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_task("Use eval(user_input) to compute")

    def test_exec_call_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_task("Run exec(cmd) to execute shell commands")

    def test_dunder_import_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_task("Use __import__('os') to load os module")

    def test_file_open_call_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_task("Call open('etc/passwd') to read secrets")

    def test_data_html_uri_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_task("Load data:text/html,<b>test</b>")

    def test_normal_task_with_code_terms_passes(self):
        task = "Build a REST API with Python FastAPI and PostgreSQL using asyncio"
        result = InputValidator.validate_task(task)
        assert result == task

    def test_event_handler_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_task("Handle onclick=doSomething in button")


# ---------------------------------------------------------------------------
# InputValidator.validate_url
# ---------------------------------------------------------------------------

class TestValidateUrl:
    def test_valid_https_url_passes(self):
        url = "https://docs.python.org/3/library/asyncio.html"
        result = InputValidator.validate_url(url)
        assert result == url

    def test_valid_http_url_passes(self):
        url = "http://example.com/page"
        result = InputValidator.validate_url(url)
        assert result == url

    def test_empty_url_raises(self):
        with pytest.raises(SecurityError, match="cannot be empty"):
            InputValidator.validate_url("")

    def test_whitespace_url_raises(self):
        with pytest.raises(SecurityError, match="cannot be empty"):
            InputValidator.validate_url("   ")

    def test_url_exceeding_max_length_raises(self):
        long_url = "https://example.com/" + "x" * 2048
        with pytest.raises(SecurityError, match="maximum length"):
            InputValidator.validate_url(long_url)

    def test_ftp_scheme_raises(self):
        with pytest.raises(SecurityError, match="not allowed"):
            InputValidator.validate_url("ftp://example.com/file")

    def test_file_scheme_raises(self):
        with pytest.raises(SecurityError, match="not allowed"):
            InputValidator.validate_url("file:///etc/passwd")

    def test_javascript_scheme_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_url("javascript:alert(1)")

    def test_localhost_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator.validate_url("http://localhost/api")

    def test_localhost_localdomain_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator.validate_url("http://localhost.localdomain/api")

    def test_loopback_ip_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator.validate_url("http://127.0.0.1/secret")

    def test_private_class_a_ip_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator.validate_url("http://10.0.0.1/internal")

    def test_private_class_b_ip_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator.validate_url("http://172.16.0.1/internal")

    def test_private_class_c_ip_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator.validate_url("http://192.168.1.1/router")

    def test_link_local_ip_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator.validate_url("http://169.254.169.254/metadata")

    def test_missing_hostname_raises(self):
        with pytest.raises(SecurityError, match="hostname"):
            InputValidator.validate_url("http:///path/only")

    def test_suspicious_script_in_url_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_url("https://example.com?q=<script>alert(1)</script>")

    def test_public_docs_url_passes(self):
        url = "https://docs.python.org/3/"
        assert InputValidator.validate_url(url) == url


# ---------------------------------------------------------------------------
# InputValidator.validate_domain
# ---------------------------------------------------------------------------

class TestValidateDomain:
    def test_valid_domain_returned_lower(self):
        result = InputValidator.validate_domain("Example.COM")
        assert result == "example.com"

    def test_empty_domain_raises(self):
        with pytest.raises(SecurityError, match="cannot be empty"):
            InputValidator.validate_domain("")

    def test_domain_exceeding_253_chars_raises(self):
        long_domain = "a" * 254
        with pytest.raises(SecurityError, match="maximum length"):
            InputValidator.validate_domain(long_domain)

    def test_invalid_chars_raises(self):
        with pytest.raises(SecurityError, match="Invalid domain"):
            InputValidator.validate_domain("bad domain with spaces")

    def test_underscore_raises(self):
        with pytest.raises(SecurityError, match="Invalid domain"):
            InputValidator.validate_domain("bad_domain.com")

    def test_valid_subdomain_passes(self):
        result = InputValidator.validate_domain("docs.python.org")
        assert result == "docs.python.org"

    def test_domain_with_hyphens_passes(self):
        result = InputValidator.validate_domain("my-library.readthedocs.io")
        assert result == "my-library.readthedocs.io"


# ---------------------------------------------------------------------------
# InputValidator.sanitize_log_data
# ---------------------------------------------------------------------------

class TestSanitizeLogData:
    def test_github_token_redacted(self):
        data = "Token: ghp_" + "a" * 36
        result = InputValidator.sanitize_log_data(data)
        assert "ghp_[REDACTED]" in result
        assert "ghp_" + "a" * 36 not in result

    def test_openrouter_key_redacted(self):
        data = "Key: sk-or-v1-abcdefghijklmnop"
        result = InputValidator.sanitize_log_data(data)
        assert "sk-or-v1-[REDACTED]" in result

    def test_apify_api_key_redacted(self):
        data = "Using apify_api_ABC123DEF"
        result = InputValidator.sanitize_log_data(data)
        assert "apify_api_[REDACTED]" in result

    def test_bearer_token_redacted(self):
        data = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"
        result = InputValidator.sanitize_log_data(data)
        assert "Bearer [REDACTED]" in result

    def test_dict_with_api_key_redacted(self):
        data = {"api_key": "my-secret-key-123", "other": "safe"}
        result = InputValidator.sanitize_log_data(data)
        assert result["api_key"].endswith("[REDACTED]")
        assert result["other"] == "safe"

    def test_dict_with_github_token_redacted(self):
        data = {"github_token": "some-token-value", "name": "test"}
        result = InputValidator.sanitize_log_data(data)
        assert "[REDACTED]" in result["github_token"]

    def test_short_api_key_not_redacted(self):
        """Keys shorter than 5 chars (len > 4) should not be partially redacted."""
        data = {"api_key": "abc"}
        result = InputValidator.sanitize_log_data(data)
        # under 5 chars — sanitizer leaves it as-is
        assert result["api_key"] == "abc"

    def test_list_items_sanitized_recursively(self):
        data = [{"token": "my-long-secret-token"}, "safe string"]
        result = InputValidator.sanitize_log_data(data)
        assert isinstance(result, list)
        assert "[REDACTED]" in result[0]["token"]

    def test_non_string_non_dict_returned_as_is(self):
        assert InputValidator.sanitize_log_data(42) == 42
        assert InputValidator.sanitize_log_data(None) is None


# ---------------------------------------------------------------------------
# InputValidator.validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:
    def test_valid_config_returned(self):
        config = {"max_sources": 10, "chunk_size": 500}
        result = InputValidator.validate_config(config)
        assert result == config

    def test_max_sources_over_100_raises(self):
        with pytest.raises(SecurityError, match="max_sources"):
            InputValidator.validate_config({"max_sources": 101})

    def test_max_sources_exactly_100_passes(self):
        result = InputValidator.validate_config({"max_sources": 100})
        assert result["max_sources"] == 100

    def test_chunk_size_over_10000_raises(self):
        with pytest.raises(SecurityError, match="chunk_size"):
            InputValidator.validate_config({"chunk_size": 10001})

    def test_chunk_size_exactly_10000_passes(self):
        config = {"chunk_size": 10000}
        result = InputValidator.validate_config(config)
        assert result["chunk_size"] == 10000

    def test_invalid_domain_in_allowed_domains_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_config({"allowed_domains": ["bad domain!"]})

    def test_valid_domains_pass(self):
        config = {"allowed_domains": ["docs.python.org", "github.com"]}
        result = InputValidator.validate_config(config)
        assert result == config

    def test_empty_config_uses_defaults(self):
        result = InputValidator.validate_config({})
        assert result == {}


# ---------------------------------------------------------------------------
# InputValidator.validate_api_key
# ---------------------------------------------------------------------------

class TestValidateApiKey:
    def test_valid_key_returned(self):
        result = InputValidator.validate_api_key("sk-or-v1-mykey123", "openrouter")
        assert result == "sk-or-v1-mykey123"

    def test_key_is_stripped(self):
        result = InputValidator.validate_api_key("  mykey  ")
        assert result == "mykey"

    def test_empty_key_raises(self):
        with pytest.raises(SecurityError, match="cannot be empty"):
            InputValidator.validate_api_key("")

    def test_whitespace_key_raises(self):
        with pytest.raises(SecurityError, match="cannot be empty"):
            InputValidator.validate_api_key("   ")

    def test_key_exceeding_256_chars_raises(self):
        long_key = "k" * 257
        with pytest.raises(SecurityError, match="maximum length"):
            InputValidator.validate_api_key(long_key)

    def test_key_at_256_chars_passes(self):
        key = "k" * 256
        result = InputValidator.validate_api_key(key)
        assert len(result) == 256

    def test_suspicious_pattern_in_key_raises(self):
        with pytest.raises(SecurityError):
            InputValidator.validate_api_key("eval(malicious)")

    def test_custom_provider_name_in_error(self):
        with pytest.raises(SecurityError, match="github"):
            InputValidator.validate_api_key("", provider="github")


# ---------------------------------------------------------------------------
# InputValidator._check_hostname_ssrf
# ---------------------------------------------------------------------------

class TestCheckHostnameSsrf:
    def test_none_hostname_does_not_raise(self):
        InputValidator._check_hostname_ssrf(None)

    def test_empty_hostname_does_not_raise(self):
        # empty string is falsy — same branch as None
        InputValidator._check_hostname_ssrf("")

    def test_localhost_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator._check_hostname_ssrf("localhost")

    def test_localhost_localdomain_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator._check_hostname_ssrf("localhost.localdomain")

    def test_127_0_0_1_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator._check_hostname_ssrf("127.0.0.1")

    def test_10_0_0_1_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator._check_hostname_ssrf("10.0.0.1")

    def test_172_31_255_255_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator._check_hostname_ssrf("172.31.255.255")

    def test_192_168_0_1_raises(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator._check_hostname_ssrf("192.168.0.1")

    def test_169_254_169_254_raises(self):
        """AWS metadata endpoint must be blocked."""
        with pytest.raises(SecurityError, match="internal"):
            InputValidator._check_hostname_ssrf("169.254.169.254")

    def test_public_ip_does_not_raise(self):
        InputValidator._check_hostname_ssrf("8.8.8.8")

    def test_dns_hostname_does_not_raise(self):
        InputValidator._check_hostname_ssrf("docs.python.org")

    def test_case_insensitive_localhost(self):
        with pytest.raises(SecurityError, match="internal"):
            InputValidator._check_hostname_ssrf("LOCALHOST")


# ---------------------------------------------------------------------------
# RateLimiter.validate_rate_limit
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_valid_rps_returned(self):
        assert RateLimiter.validate_rate_limit(10) == 10

    def test_rps_zero_raises(self):
        with pytest.raises(SecurityError):
            RateLimiter.validate_rate_limit(0)

    def test_rps_negative_raises(self):
        with pytest.raises(SecurityError):
            RateLimiter.validate_rate_limit(-5)

    def test_rps_one_passes(self):
        assert RateLimiter.validate_rate_limit(1) == 1

    def test_rps_100_passes(self):
        assert RateLimiter.validate_rate_limit(100) == 100

    def test_rps_101_raises(self):
        with pytest.raises(SecurityError):
            RateLimiter.validate_rate_limit(101)
