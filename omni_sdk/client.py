"""
Client interface: Unified interface for all communication clients.

All client implementations (SshClient, SerialClient, etc.) must implement this interface.
This provides a flat, maintainable structure without deep inheritance.

Standard capability names:
- execute: Execute command/request (e.g., "show version")
- send_message: Send message (e.g., HTTP POST)
- get_status: Get client status/health
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from .result import Result, ErrorKinds


class Client(ABC):
    """
    Base interface for all communication clients.

    All client implementations must implement these 9 methods.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Client name: 'ssh', 'serial', 'adb', 'http', 'websocket', 'grpc', 'snmp', 'netconf'.

        Returns:
            Client name string
        """
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """
        Client version string.

        Returns:
            Version string (e.g., "1.0.0")
        """
        pass

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> Result[None]:
        """
        Initialize client with configuration.

        Args:
            config: Client configuration from devices.toml
                    (e.g., devices.clients.ssh section)

        Returns:
            Result.ok(None) on success, Result.err on failure

        Example Ssh config:
            {
                "host": "192.168.1.1",
                "port": 22,
                "username": "admin",
                "password": "secret",
                "timeout_ms": 5000
            }
        """
        pass

    @abstractmethod
    def connect(self) -> Result[None]:
        """
        Establish connection to endpoint.

        Must be called before send/receive.

        Returns:
            Result.ok(None) on success, Result.err on failure
        """
        pass

    @abstractmethod
    def disconnect(self) -> Result[None]:
        """
        Close connection.

        Safe to call multiple times.

        Returns:
            Result.ok(None) on success, Result.err on failure
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if client is currently connected.

        Returns:
            True if connected, False otherwise
        """
        pass

    @abstractmethod
    def send(self, command: str) -> Result[None]:
        """
        Send command/request to endpoint.

        Args:
            command: Command string to send

        Returns:
            Result.ok(None) on success, Result.err on failure
        """
        pass

    @abstractmethod
    def receive(self, timeout_ms: int = 5000) -> Result[str]:
        """
        Receive response from endpoint.

        Args:
            timeout_ms: Timeout in milliseconds (default: 5000)

        Returns:
            Result.ok(response_string) on success, Result.err on failure
        """
        pass

    @abstractmethod
    def send_and_receive(self, command: str, timeout_ms: int = 5000) -> Result[str]:
        """
        Convenience: send command and receive response.

        Args:
            command: Command string to send
            timeout_ms: Timeout in milliseconds (default: 5000)

        Returns:
            Result.ok(response_string) on success, Result.err on failure
        """
        pass

    @abstractmethod
    def capabilities(self) -> Dict[str, str]:
        """
        Return map of capability_name -> description.

        Device framework auto-discovers capabilities from clients.
        Each capability is a method on the client object.

        Returns:
            Dict mapping capability names to descriptions

        Example SshClient capabilities:
            {
                "execute": "Execute shell command and return output",
                "file_transfer": "Transfer files using SCP",
                "get_status": "Get SSH connection status"
            }
        """
        pass

    def __repr__(self) -> str:
        connected = "connected" if self.is_connected() else "disconnected"
        return f"<Client {self.name} v{self.version} ({connected})>"
