"""Custom exceptions for better error handling."""


class ActorError(Exception):
    """Base exception for all actor errors."""


class InputValidationError(ActorError):
    """Raised when input validation fails."""


class SearchError(ActorError):
    """Raised when search operations fail."""


class CrawlError(ActorError):
    """Raised when crawling fails."""


class ExtractionError(ActorError):
    """Raised when content extraction fails."""


class GitHubAPIError(ActorError):
    """Raised when GitHub API calls fail."""


class StackOverflowAPIError(ActorError):
    """Raised when StackOverflow API calls fail."""


class CacheError(ActorError):
    """Raised when cache operations fail."""


class RateLimitError(ActorError):
    """Raised when rate limits are exceeded."""


class ConfigurationError(ActorError):
    """Raised when configuration is invalid."""


class ActorTimeoutError(ActorError):
    """Raised when operations timeout.

    Named ActorTimeoutError to avoid shadowing the built-in TimeoutError.
    """


class SecurityError(ActorError):
    """Raised when security validation fails."""
