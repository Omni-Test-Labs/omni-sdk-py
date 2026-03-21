"""
Omni SDK - Unified device management across multiple protocols.

Public API for managing devices with SSH, Serial, HTTP, and other protocols.
"""

from typing import Dict, TYPE_CHECKING, cast
from .result import Result, ErrorKinds, create_error_result
from .device import Device
from .config import (
    ConfigLoader,
    SdkConfig,
    DeviceConfig,
    SshConfig,
    SerialConfig,
    ClientConfig,
)
from .clients.ssh_client import SshClient
from .clients.serial_client import SerialClient
from .client import Client as ClientInterface

if TYPE_CHECKING:
    from .client import Client


def initialize_from_config(config_path: str) -> Result[Dict[str, Device]]:
    """
    Initialize SDK from configuration file.

    This is the main entry point for using the SDK.
    Loads devices, creates clients, and returns device map.

    Args:
        config_path: Path to TOML configuration file (e.g., "devices.toml")

    Returns:
        Result.ok(device_map) where device_map maps device_id -> Device
        Result.err on configuration or initialization failure

    Example:
        devices_result = initialize_from_config("devices.toml")

        if not devices_result.is_ok:
            print(f"Failed to load config: {devices_result._error.message}")
            return

        devices = devices_result.unwrap()

        # Connect to device
        device = devices["device-001"]
        connect_result = device.connect_all()
    """
    # Load and validate config
    config_result = ConfigLoader.load_and_validate(config_path)
    if not config_result.is_ok:
        return cast(Result[Dict[str, Device]], config_result)

    config = config_result.unwrap()

    # Create devices
    devices: Dict[str, Device] = {}

    # Client registry
    client_registry: Dict[str, ClientInterface] = {
        "ssh": SshClient(),
        "serial": SerialClient(),
    }
    # client_registry['http'] = HttpClient()  # Will be added when implemented

    for device_config in config.devices:
        # Create device with plain config dict (Device expects dict, not pydantic model)
        device_dict = {
            "id": device_config.id,
            "name": device_config.name,
            "clients": device_config.clients,
            "metadata": device_config.metadata,
        }
        device = Device(device_config.id, device_dict)

        # Add clients
        for client_type, client_data in device_config.clients.items():
            if client_type not in client_registry:
                return create_error_result(
                    kind=ErrorKinds.UNKNOWN_CLIENT_TYPE_ERROR,
                    message=f"Client type '{client_type}' not registered",
                    details={
                        "device_id": device_config.id,
                        "client_type": client_type,
                        "available_clients": list(client_registry.keys()),
                        "note": "Client will be implemented in future version",
                    },
                )

            client = client_registry[client_type]
            add_result = device.add_client(client)
            if not add_result.is_ok:
                return cast(Result[Dict[str, Device]], add_result)

        devices[device_config.id] = device

    return Result.ok(devices)


def connect_device(device_id: str, devices: Dict[str, Device]) -> Result[Device]:
    """
    Connect to a specific device.

    Args:
        device_id: Device identifier
        devices: Device map from initialize_from_config

    Returns:
        Result.ok(device) on success, Result.err if device not found or connection fails
    """
    if device_id not in devices:
        available = list(devices.keys())
        return create_error_result(
            kind=ErrorKinds.DEVICE_NOT_FOUND_ERROR,
            message=f"Device '{device_id}' not found",
            details={"device_id": device_id, "available_devices": available},
        )

    device = devices[device_id]
    connect_result = device.connect_all()
    if not connect_result.is_ok:
        err = connect_result._error
        assert err is not None, "Error should exist when is_ok=False"
        return Result.err(err)

    return Result.ok(device)


__all__ = [
    "Result",
    "ErrorKinds",
    "Device",
    "ConfigLoader",
    "SdkConfig",
    "DeviceConfig",
    "SshConfig",
    "SerialConfig",
    "ClientConfig",
    "SshClient",
    "SerialClient",
    "initialize_from_config",
    "connect_device",
]
