"""
Configuration system using TOML files and pydantic validation.

Defines schemas for device and client configuration, with validation.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, field_validator, ConfigDict
import tomli  # For reading TOML files
from .result import Result, ErrorKinds, create_error_result


class ClientConfig(BaseModel):
    """
    Base client configuration.

    All client types inherit from this and add their specific fields.
    """

    timeout_ms: int = 5000

    model_config = ConfigDict(extra="forbid")  # Strict validation


class SshConfig(ClientConfig):
    """SSH client configuration."""

    host: str
    port: int = 22
    username: str
    password: Optional[str] = None
    password_file: Optional[str] = None
    key_file: Optional[str] = None

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v


class SerialConfig(ClientConfig):
    """Serial client configuration."""

    port: str
    baud_rate: int = 9600
    data_bits: int = 8
    stop_bits: int = 1
    parity: str = "none"

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: str) -> str:
        if not v:
            raise ValueError("Serial port cannot be empty")
        return v

    @field_validator("baud_rate")
    @classmethod
    def validate_baud_rate(cls, v: int) -> int:
        valid_rates = [9600, 19200, 38400, 57600, 115200, 230400]
        if v not in valid_rates:
            raise ValueError(f"Invalid baud rate {v}. Valid rates: {valid_rates}")
        return v

    @field_validator("parity")
    @classmethod
    def validate_parity(cls, v: str) -> str:
        valid_parities = ["none", "even", "odd", "mark", "space"]
        if v.lower() not in valid_parities:
            raise ValueError(f"Invalid parity '{v}'. Valid values: {valid_parities}")
        return v.lower()


class HttpConfig(ClientConfig):
    """HTTP client configuration."""

    base_url: str
    headers: Dict[str, str] = {}

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"URL must start with http:// or https://, got {v}")
        return v


class ClientConfigUnion(BaseModel):
    """
    Union of all client configurations.

    This is the model used in DeviceConfig.clients.
    """

    ssh: Optional[SshConfig] = None
    serial: Optional[SerialConfig] = None
    http: Optional[HttpConfig] = None
    # TODO: Add more client types as implemented (adb, websocket, grpc, snmp, netconf)


class DeviceConfig(BaseModel):
    """
    Device configuration.

    Defines a single device with its clients and metadata.
    """

    id: str
    name: str
    metadata: Dict[str, Any] = {}
    clients: Dict[str, Dict[str, Any]] = {}

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v:
            raise ValueError("Device ID cannot be empty")
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                f"Device ID must be alphanumeric with optional hyphens/underscores, got '{v}'"
            )
        return v

    @field_validator("clients")
    @classmethod
    def validate_clients(
        cls, v: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        valid_types = {"ssh", "serial", "http"}
        for client_type in v.keys():
            if client_type not in valid_types:
                raise ValueError(
                    f"Unknown client type: '{client_type}'. Valid types: {valid_types}"
                )
        return v


class GlobalConfig(BaseModel):
    """Global SDK configuration."""

    log_level: str = "info"
    default_timeout_ms: int = 5000
    retry_attempts: int = 3

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ["debug", "info", "warning", "error", "critical"]
        if v.lower() not in valid_levels:
            raise ValueError(f"Invalid log level '{v}'. Valid levels: {valid_levels}")
        return v.lower()

    @field_validator("default_timeout_ms")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"Timeout must be positive, got {v}")
        return v

    @field_validator("retry_attempts")
    @classmethod
    def validate_retry(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"Retry attempts cannot be negative, got {v}")
        return v


class SdkConfig(BaseModel):
    """
    Top-level SDK configuration.

    Contains global config and list of devices.
    """

    global_config: GlobalConfig = GlobalConfig()
    devices: List[DeviceConfig] = []

    @field_validator("devices")
    @classmethod
    def validate_unique_ids(cls, v: List[DeviceConfig]) -> List[DeviceConfig]:
        ids = [device.id for device in v]
        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            raise ValueError(f"Duplicate device IDs found: {set(duplicates)}")
        return v


class ConfigLoader:
    """
    Load and validate configuration from TOML files.

    Returns Result<T> for all operations, aligning with SDK error handling.
    """

    @staticmethod
    def load(path: str) -> Result[Dict[str, Any]]:
        """
        Load TOML file from path.

        Args:
            path: Path to TOML configuration file

        Returns:
            Result.ok(config_dict) on success, Result.err on failure
        """
        try:
            with open(path, "rb") as f:
                data = tomli.load(f)
            return Result.ok(data)
        except FileNotFoundError:
            return create_error_result(
                kind=ErrorKinds.CONFIG_NOT_FOUND_ERROR,
                message=f"Config file not found: {path}",
                details={"path": path},
            )
        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.CONFIG_ERROR,
                message=f"Failed to load config file: {str(e)}",
                details={"path": path, "exception_type": type(e).__name__},
            )

    @staticmethod
    def validate(data: Dict[str, Any]) -> Result[SdkConfig]:
        """
        Validate configuration data against schema.

        Args:
            data: Configuration dictionary from TOML file

        Returns:
            Result.ok(SdkConfig) on success, Result.err on validation failure
        """
        try:
            # Convert flat structure to nested structure
            config_dict = {
                "global_config": data.get("global", {}),
                "devices": data.get("devices", []),
            }

            config = SdkConfig(**config_dict)
            return Result.ok(config)
        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.CONFIG_VALIDATION_ERROR,
                message=f"Config validation failed: {str(e)}",
                details={"exception_type": type(e).__name__},
            )

    @staticmethod
    def load_and_validate(path: str) -> Result[SdkConfig]:
        """
        Load and validate configuration from file in one step.

        Args:
            path: Path to TOML configuration file

        Returns:
            Result.ok(SdkConfig) on success, Result.err on failure
        """
        load_result = ConfigLoader.load(path)
        if not load_result.is_ok:
            return load_result  # Error propagates

        config_data = load_result.unwrap()
        return ConfigLoader.validate(config_data)

    @staticmethod
    def get_client_config(
        device_config: DeviceConfig, client_name: str
    ) -> Result[Dict[str, str]]:
        """
        Get client configuration for a specific device.

        Args:
            device_config: Device configuration
            client_name: Client name (e.g., "ssh", "serial")

        Returns:
            Result.ok(config_dict) on success, Result.err if client not found
        """
        clients = device_config.clients or {}
        if client_name not in clients:
            available = list(clients.keys())
            return create_error_result(
                kind=ErrorKinds.CONFIG_ERROR,
                message=f"Client '{client_name}' not found in device '{device_config.id}'",
                details={
                    "device_id": device_config.id,
                    "requested_client": client_name,
                    "available_clients": available,
                },
            )

        # Convert all values to strings for Client.initialize()
        client_data = clients[client_name]
        config_dict = {}
        for key, value in client_data.items():
            if isinstance(value, str):
                config_dict[key] = value
            else:
                config_dict[key] = json_fallback(value)

        return Result.ok(config_dict)


def json_fallback(obj: Any) -> str:
    """Fallback JSON serializer for non-string config values."""
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    elif isinstance(obj, list):
        return ",".join(json_fallback(item) for item in obj)
    elif isinstance(obj, dict):
        return ",".join(f"{k}={v}" for k, v in obj.items())
    else:
        return str(obj)


__all__ = [
    "ClientConfig",
    "SshConfig",
    "SerialConfig",
    "HttpConfig",
    "DeviceConfig",
    "GlobalConfig",
    "SdkConfig",
    "ConfigLoader",
]
