"""
Device container: Manages multiple clients and their capabilities.

A device can have multiple clients (e.g., SSH + HTTP, Serial + SNMP).
The Device class manages these clients and auto-discovers their capabilities.
"""

from typing import Dict, List, Optional, Any, Callable
from .client import Client
from .result import Result, ErrorKinds, create_error_result


class Device:
    """
    Device container - holds multiple clients and capabilities.

    Usage:
        device = Device("device-001", config)
        device.add_client(SshClient())   # Add SSH capability
        device.add_client(HttpClient())  # Add HTTP capability

        # Auto-discovered from client capabilities
        caps = device.list_capabilities()

        # Execute capability
        result = device.execute("execute", "show version")
    """

    def __init__(self, device_id: str, config: Dict[str, Any]):
        """
        Initialize device.

        Args:
            device_id: Unique device identifier
            config: Device configuration from devices.toml
        """
        self.device_id = device_id
        self.name = config.get("name", device_id)
        self.clients: Dict[str, Client] = {}
        self.config = config
        self.capabilities: Dict[str, Dict[str, str]] = {}

    def add_client(self, client: Client) -> Result[None]:
        """
        Add client to device - framework discovers capabilities from client.

        Args:
            client: Client instance to add

        Returns:
            Result.ok(None) on success, Result.err on failure
        """
        if client.name in self.clients:
            return create_error_result(
                kind=ErrorKinds.CONFIG_ERROR,
                message=f"Client {client.name} already exists in device {self.device_id}",
                details={"device_id": self.device_id, "client_name": client.name},
            )

        # Initialize client with config from devices.clients.{client_name}
        client_config = self.config.get("clients", {}).get(client.name, {})
        init_result = client.initialize(client_config)

        if not init_result.is_ok:
            return init_result

        self.clients[client.name] = client

        # Auto-register capabilities from client
        for cap_name, cap_desc in client.capabilities().items():
            self.capabilities[cap_name] = {
                "client": client.name,
                "description": cap_desc,
            }

        return Result.ok(None)

    def get_client(self, name: str) -> Result[Client]:
        """
        Get client by name.

        Args:
            name: Client name (e.g., "ssh", "serial")

        Returns:
            Result.ok(client) on success, Result.err on failure
        """
        if name not in self.clients:
            available = list(self.clients.keys())
            return create_error_result(
                kind=ErrorKinds.DEVICE_ERROR,
                message=f"Client '{name}' not found in device {self.device_id}",
                details={
                    "device_id": self.device_id,
                    "requested_client": name,
                    "available_clients": available,
                },
            )
        return Result.ok(self.clients[name])

    def connect_all(self) -> Result[None]:
        """
        Connect all clients.

        Returns:
            Result.ok(None) on success, Result.err on first failure
        """
        for client in self.clients.values():
            result = client.connect()
            if not result.is_ok:
                return result
        return Result.ok(None)

    def disconnect_all(self) -> Result[None]:
        """
        Disconnect all clients.

        Continues disconnecting even if some fail.

        Returns:
            Result.ok(None) (always succeeds for disconnect_all)
        """
        for client in self.clients.values():
            result = client.disconnect()
            # Log but continue disconnecting others
            if not result.is_ok:
                pass
        return Result.ok(None)

    def list_capabilities(self) -> List[str]:
        """
        List all available capabilities across all clients.

        Returns:
            List of capability names
        """
        return list(self.capabilities.keys())

    def list_clients(self) -> List[str]:
        """
        List all client names.

        Returns:
            List of client names
        """
        return list(self.clients.keys())

    def execute(self, capability: str, *args, **kwargs) -> Result[Any]:
        """
        Execute a capability by name.

        Args:
            capability: Capability name (e.g., "execute", "send_message")
            *args: Positional arguments for capability method
            **kwargs: Keyword arguments for capability method

        Returns:
            Result of capability execution

        Example:
            # Execute "show version" via SSH client
            result = device.execute("execute", "show version")
        """
        if capability not in self.capabilities:
            available = list(self.capabilities.keys())
            return create_error_result(
                kind=ErrorKinds.DEVICE_ERROR,
                message=f"Capability '{capability}' not found in device {self.device_id}",
                details={
                    "device_id": self.device_id,
                    "requested_capability": capability,
                    "available_capabilities": available,
                },
            )

        # Find the client that provides this capability
        cap_info = self.capabilities[capability]
        client_name = cap_info["client"]
        client = self.clients.get(client_name)

        if client is None:
            return create_error_result(
                kind=ErrorKinds.DEVICE_ERROR,
                message=f"Client '{client_name}' required for capability '{capability}' not found",
                details={
                    "device_id": self.device_id,
                    "capability": capability,
                    "client_name": client_name,
                },
            )

        # Dynamic method dispatch
        if not hasattr(client, capability):
            return create_error_result(
                kind=ErrorKinds.DEVICE_ERROR,
                message=f"Client '{client.name}' doesn't implement capability '{capability}'",
                details={
                    "device_id": self.device_id,
                    "capability": capability,
                    "client_name": client.name,
                },
            )

        method = getattr(client, capability)
        try:
            result = method(*args, **kwargs)
            if not isinstance(result, Result):
                # Wrap non-Result return in Result.ok
                return Result.ok(result)
            return result
        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.RUNTIME_ERROR,
                message=f"Failed to execute {capability}: {str(e)}",
                details={
                    "capability": capability,
                    "client": client.name,
                    "client_version": client.version,
                    "exception_type": type(e).__name__,
                },
            )

    def __repr__(self) -> str:
        clients_str = ", ".join(self.clients.keys()) if self.clients else "none"
        caps_str = ", ".join(self.capabilities.keys()) if self.capabilities else "none"
        return (
            f"<Device {self.device_id} name='{self.name}' "
            f"clients=[{clients_str}] capabilities=[{caps_str}]>"
        )

    def get_status(self) -> Dict[str, Any]:
        """
        Get device status including all clients.

        Returns:
            Dictionary with device and client status information
        """
        status = {
            "device_id": self.device_id,
            "name": self.name,
            "clients": {},
            "capabilities": list(self.capabilities.keys()),
        }

        for client_name, client in self.clients.items():
            status["clients"][client_name] = {
                "name": client.name,
                "version": client.version,
                "connected": client.is_connected(),
            }

        return status
