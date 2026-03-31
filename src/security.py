"""Security utilities for input validation and sanitization."""

import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

from .exceptions import SecurityError

# RFC 1918 private networks + link-local + loopback
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),       # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),      # IPv6 link-local
]


class InputValidator:
    """Validates and sanitizes user inputs."""

    # Suspicious patterns that might indicate injection attempts
    SUSPICIOUS_PATTERNS = [
        r"<script[^>]*>.*?</script>",  # Script tags
        r"javascript:",  # JavaScript protocol
        r"data:text/html",  # Data URIs with HTML
        r"vbscript:",  # VBScript protocol
        r"\bon\w+\s*=",  # Event handlers (onclick, onerror, etc.)
        r"eval\(",  # eval() calls
        r"exec\(",  # exec() calls
        r"__import__",  # Python imports
        r"""open\(\s*['"]""",  # File operations like open("file") — not bare "open("
    ]

    # Allowed URL schemes
    ALLOWED_SCHEMES = ["http", "https"]

    # Maximum lengths to prevent DoS
    MAX_TASK_LENGTH = 1000
    MAX_DOMAIN_LENGTH = 253  # RFC 1035
    MAX_URL_LENGTH = 2048

    @classmethod
    def validate_task(cls, task: str) -> str:
        """Validate and sanitize task description.

        Args:
            task: Task description from user

        Returns:
            Sanitized task string

        Raises:
            SecurityError: If task contains suspicious patterns
        """
        if not task or not task.strip():
            raise SecurityError("Task cannot be empty")

        if len(task) > cls.MAX_TASK_LENGTH:
            raise SecurityError(f"Task exceeds maximum length of {cls.MAX_TASK_LENGTH}")

        # Check for suspicious patterns
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, task, re.IGNORECASE):
                raise SecurityError(f"Task contains suspicious pattern: {pattern}")

        return task.strip()

    @classmethod
    def _check_hostname_ssrf(cls, hostname: str | None) -> None:
        """Check that a parsed hostname is not a private/internal address (SSRF)."""
        if not hostname:
            return
        hostname = hostname.lower()
        if hostname in ("localhost", "localhost.localdomain"):
            raise SecurityError("Access to internal hosts is forbidden")
        try:
            addr = ipaddress.ip_address(hostname)
            for network in _PRIVATE_NETWORKS:
                if addr in network:
                    raise SecurityError("Access to internal hosts is forbidden")
        except ValueError:
            # hostname is a DNS name, not a raw IP — that's fine
            pass

    @classmethod
    def validate_url(cls, url: str) -> str:
        """Validate URL for security issues.

        Args:
            url: URL to validate

        Returns:
            Validated URL

        Raises:
            SecurityError: If URL is invalid or suspicious
        """
        if not url or not url.strip():
            raise SecurityError("URL cannot be empty")

        if len(url) > cls.MAX_URL_LENGTH:
            raise SecurityError(f"URL exceeds maximum length of {cls.MAX_URL_LENGTH}")

        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise SecurityError(f"Invalid URL format: {e}") from e

        # Validate scheme
        if parsed.scheme not in cls.ALLOWED_SCHEMES:
            raise SecurityError(
                f"URL scheme '{parsed.scheme}' not allowed. Must be one of: {cls.ALLOWED_SCHEMES}"
            )

        # Check for suspicious patterns
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                raise SecurityError("URL contains suspicious pattern")

        # Prevent SSRF attempts
        cls._check_hostname_ssrf(parsed.hostname)

        return url

    @classmethod
    def validate_domain(cls, domain: str) -> str:
        """Validate domain name.

        Args:
            domain: Domain name to validate

        Returns:
            Validated domain

        Raises:
            SecurityError: If domain is invalid
        """
        if not domain or not domain.strip():
            raise SecurityError("Domain cannot be empty")

        if len(domain) > cls.MAX_DOMAIN_LENGTH:
            raise SecurityError(f"Domain exceeds maximum length of {cls.MAX_DOMAIN_LENGTH}")

        # Basic domain validation regex
        domain_pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$"
        if not re.match(domain_pattern, domain):
            raise SecurityError("Invalid domain format")

        return domain.lower().strip()

    @classmethod
    def sanitize_log_data(cls, data: Any) -> Any:
        """Sanitize data before logging to prevent token leakage.

        Args:
            data: Data to sanitize

        Returns:
            Sanitized data with secrets redacted
        """
        if isinstance(data, str):
            # Redact common token patterns
            data = re.sub(r"ghp_[a-zA-Z0-9]{36}", "ghp_[REDACTED]", data)
            data = re.sub(r"apify_api_[a-zA-Z0-9]+", "apify_api_[REDACTED]", data)
            data = re.sub(r"sk-or-v1-[a-zA-Z0-9]+", "sk-or-v1-[REDACTED]", data)
            data = re.sub(r"Bearer [a-zA-Z0-9_\-\.]+", "Bearer [REDACTED]", data)
            data = re.sub(r"token[\"']?\s*[:=]\s*[\"']?[a-zA-Z0-9_\-\.]+", "token=[REDACTED]", data)
        elif isinstance(data, dict):
            # Redact known secret keys
            secret_keys = {"api_key", "token", "secret", "password", "openrouter_api_key", "github_token"}
            sanitized = {}
            for k, v in data.items():
                if k.lower() in secret_keys and isinstance(v, str) and len(v) > 4:
                    sanitized[k] = v[:4] + "...[REDACTED]"
                else:
                    sanitized[k] = cls.sanitize_log_data(v)
            return sanitized
        elif isinstance(data, list):
            # Recursively sanitize list items
            return [cls.sanitize_log_data(item) for item in data]

        return data

    @classmethod
    def validate_config(cls, config: dict) -> dict:
        """Validate actor configuration for security issues.

        Args:
            config: Configuration dictionary

        Returns:
            Validated configuration

        Raises:
            SecurityError: If configuration has security issues
        """
        # Validate max_sources isn't absurdly high (DoS prevention)
        max_sources = config.get("max_sources", 10)
        if max_sources > 100:
            raise SecurityError("max_sources exceeds safe limit of 100")

        # Validate chunk_size
        chunk_size = config.get("chunk_size", 500)
        if chunk_size > 10000:
            raise SecurityError("chunk_size exceeds safe limit of 10000")

        # Validate domains if whitelist provided
        allowed_domains = config.get("allowed_domains", [])
        if allowed_domains:
            for domain in allowed_domains:
                cls.validate_domain(domain)

        return config

    @classmethod
    def validate_api_key(cls, key: str, provider: str = "openrouter") -> str:
        """Validate API key format.

        Args:
            key: API key string to validate.
            provider: Provider name for error messages.

        Returns:
            Validated API key.

        Raises:
            SecurityError: If key format is invalid.
        """
        if not key or not key.strip():
            raise SecurityError(f"{provider} API key cannot be empty")

        # Prevent obviously injected values
        for pattern in cls.SUSPICIOUS_PATTERNS:
            if re.search(pattern, key, re.IGNORECASE):
                raise SecurityError(f"{provider} API key contains suspicious pattern")

        if len(key) > 256:
            raise SecurityError(f"{provider} API key exceeds maximum length")

        return key.strip()


class RateLimiter:
    """Rate limiting utilities."""

    @staticmethod
    def validate_rate_limit(requests_per_second: int) -> int:
        """Validate rate limit value.

        Args:
            requests_per_second: Desired RPS

        Returns:
            Validated RPS

        Raises:
            SecurityError: If RPS is invalid
        """
        if requests_per_second < 1:
            raise SecurityError("Rate limit must be at least 1 request per second")

        if requests_per_second > 100:
            raise SecurityError("Rate limit exceeds maximum of 100 requests per second")

        return requests_per_second
