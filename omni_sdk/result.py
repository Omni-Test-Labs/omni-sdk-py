"""
Result<T>: Unified error handling for SDK using monadic pattern.

All SDK methods return Result<T> instead of raising exceptions.
Forces explicit error handling while maintaining clean code with chaining.

Example:
    result = connect_to_device("192.168.1.1")

    if result.is_ok:
        device = result.unwrap()
        print(f"Connected: {device}")
    else:
        err = result._error
        print(f"Failed: {err.kind} - {err.message}")

    # Chaining with and_then
    result = load_config("config.toml") \
        .and_then(lambda cfg: initialize_clients(cfg)) \
        .and_then(lambda clients: connect_device(clients))

    if result.is_ok:
        print("Success!")
    else:
        print(f"Error: {result._error.message}")
"""

from dataclasses import dataclass, field
from typing import Generic, TypeVar, Optional, Callable, Any, TYPE_CHECKING

T = TypeVar("T")
if TYPE_CHECKING:
    from typing_extensions import Self  # Python 3.11+
else:
    try:
        from typing import Self
    except ImportError:
        Self = "Result[T]"  # Fallback for older Python


@dataclass
class Error:
    """
    Error information with context and optional cause.

    Attributes:
        kind: Error type (e.g., "NetworkError", "DeviceError", "ConfigError")
        message: Human-readable error description
        details: Additional context as key-value pairs (empty dict by default)
        cause: Optional error that caused this error (for error chaining)
    """

    kind: str
    message: str
    details: dict = field(default_factory=dict)
    cause: Optional["Error"] = None

    def __str__(self) -> str:
        s = f"{self.kind}: {self.message}"
        if self.details:
            s += f" (details: {self.details})"
        if self.cause:
            s += f"\n  Caused by: {self.cause}"
        return s

    def to_dict(self) -> dict:
        """Convert error to dictionary for serialization."""
        result = {
            "kind": self.kind,
            "message": self.message,
            "details": self.details or {},
        }
        if self.cause:
            result["cause"] = self.cause.to_dict()
        return result


@dataclass
class Result(Generic[T]):
    """
    Result<T>: Monadic type for error handling.

    Represents either success (ok) or failure (err). Forces explicit
    error handling while maintaining clean code with method chaining.

    Type Parameters:
        T: Success value type
    """

    is_ok: bool
    _value: Optional[T] = None
    _error: Optional[Error] = None

    @property
    def is_err(self) -> bool:
        """Return True if this is an error result."""
        return not self.is_ok

    @staticmethod
    def ok(value: T) -> "Result[T]":
        """
        Create a successful result.

        Args:
            value: The success value

        Returns:
            Result containing value
        """
        return Result(is_ok=True, _value=value)

    @staticmethod
    def err(error: Error) -> "Result[T]":
        """
        Create an error result.

        Args:
            error: The error information

        Returns:
            Result containing error
        """
        return Result(is_ok=False, _error=error)

    @staticmethod
    def from_exception(exception: Exception, kind: str = "RuntimeError") -> "Result[T]":
        """
        Create an error result from an exception.

        Args:
            exception: The exception to convert
            kind: Error kind (defaults to "RuntimeError")

        Returns:
            Result containing error derived from exception
        """
        return Result.err(
            Error(
                kind=kind,
                message=str(exception),
                details={"exception_type": type(exception).__name__},
            )
        )

    def unwrap(self) -> T:
        """
        Unwrap the value or raise RuntimeError if error.

        Use this only when you're certain the result is ok.
        Otherwise, check is_ok first.

        Returns:
            The success value

        Raises:
            RuntimeError: If result is err
        """
        if not self.is_ok:
            raise RuntimeError(f"Attempted to unwrap error: {self._error}")
        return self._value

    def unwrap_or(self, default: T) -> T:
        """
        Unwrap the value or return default if error.

        Args:
            default: Default value to return on error

        Returns:
            The success value or default
        """
        return self._value if self.is_ok else default  # type: ignore[return-value]

    def unwrap_or_else(self, fn: Callable[[Error], T]) -> T:
        """
        Unwrap the value or compute it from error.

        Args:
            fn: Function that takes error and returns default value

        Returns:
            The success value or computed default
        """
        if self.is_ok:
            assert self._value is not None
            return self._value
        # fn receives Error, not Optional[Error]
        return fn(self._error)  # type: ignore[arg-type]

    def map(self, fn: Callable[[T], Any]) -> "Result[Any]":
        """
        Transform the success value using a function.

        If result is ok, applies fn to value and returns result.
        If result is err, propagates the error.

        Args:
            fn: Function to apply to success value

        Returns:
            New Result with transformed value
        """
        if not self.is_ok:
            return self  # Preserve error

        try:
            assert self._value is not None
            return Result.ok(fn(self._value))
        except Exception as e:
            return Result.err(
                Error(
                    "RuntimeError",
                    f"map function failed: {str(e)}",
                    details={"exception_type": type(e).__name__},
                )
            )

    def and_then(self, fn: Callable[[T], "Result[Any]"]) -> "Result[Any]":
        """
        Chain operations: only calls fn if result is ok.

        Short-circuits on first error. Use this to chain multiple
        operations where each depends on the previous.

        Args:
            fn: Function that takes value and returns Result

        Returns:
            Result of fn if ok, or this error
        """
        if not self.is_ok:
            return self  # Preserve error

        try:
            assert self._value is not None
            return fn(self._value)
        except Exception as e:
            return Result.err(
                Error(
                    "RuntimeError",
                    f"and_then function failed: {str(e)}",
                    details={"exception_type": type(e).__name__},
                )
            )

    def or_else(self, fn: Callable[[Error], "Result[T]"]) -> "Result[T]":
        """
        Provide fallback if result is err.

        Args:
            fn: Function that takes error and returns Result

        Returns:
            This result if ok, or result from fn
        """
        if self.is_ok:
            return self

        try:
            assert self._error is not None
            return fn(self._error)
        except Exception as e:
            return Result.err(
                Error(
                    "RuntimeError",
                    f"or_else function failed: {str(e)}",
                    details={"exception_type": type(e).__name__},
                )
            )

    def error(self) -> Optional[Error]:
        """
        Get the error if result is err.

        Returns:
            Error or None
        """
        return self._error if not self.is_ok else None

    def value(self) -> Optional[T]:
        """
        Get the value (None if err).

        Returns:
            Value or None
        """
        return self._value

    def __repr__(self) -> str:
        if self.is_ok:
            return f"Result.ok({self._value})"
        else:
            return f"Result.err({self._error})"


# Error kind constants for consistency across SDK
class ErrorKinds:
    """Standard error kinds used across the SDK."""

    # Network errors
    NETWORK_ERROR = "NetworkError"
    CONNECTION_ERROR = "ConnectionError"
    TIMEOUT_ERROR = "TimeoutError"
    AUTHENTICATION_ERROR = "AuthenticationError"

    # Device errors
    DEVICE_ERROR = "DeviceError"
    DEVICE_NOT_FOUND_ERROR = "DeviceNotFoundError"
    DEVICE_BUSY_ERROR = "DeviceBusyError"
    DEVICE_NOT_CONNECTED = "DeviceNotConnected"

    # Configuration errors
    CONFIG_ERROR = "ConfigError"
    CONFIG_NOT_FOUND_ERROR = "ConfigNotFoundError"
    CONFIG_VALIDATION_ERROR = "ConfigValidationError"
    UNKNOWN_CLIENT_TYPE_ERROR = "UnknownClientTypeError"

    # Runtime errors
    RUNTIME_ERROR = "RuntimeError"
    INVALID_OPERATION_ERROR = "InvalidOperationError"
    SERIALIZATION_ERROR = "SerializationError"

    # Client-specific errors
    SSH_ERROR = "SshError"
    SERIAL_ERROR = "SerialError"
    ADB_ERROR = "AdbError"
    HTTP_ERROR = "HttpError"
    WEBSOCKET_ERROR = "WebSocketError"
    GRPC_ERROR = "GrpcError"
    SNMP_ERROR = "SnmpError"
    NETCONF_ERROR = "NetconfError"


def create_error(
    kind: str,
    message: str,
    details: Optional[dict] = None,
    cause: Optional[Error] = None,
) -> Error:
    """
    Helper function to create error with consistent formatting.

    Args:
        kind: Error kind (use ErrorKinds constants)
        message: Error message
        details: Optional additional context
        cause: Optional causing error

    Returns:
        Error instance
    """
    return Error(kind=kind, message=message, details=details or {}, cause=cause)


def create_error_result(
    kind: str,
    message: str,
    details: Optional[dict] = None,
    cause: Optional[Error] = None,
) -> Result:
    """
    Helper function to create error result directly.

    Args:
        kind: Error kind (use ErrorKinds constants)
        message: Error message
        details: Optional additional context
        cause: Optional causing error

    Returns:
        Result.err with created error
    """
    return Result.err(create_error(kind, message, details, cause))


__all__ = [
    "Result",
    "Error",
    "ErrorKinds",
    "create_error",
    "create_error_result",
]
