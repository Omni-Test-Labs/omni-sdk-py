"""
Unit tests for SDK framework components (Device, Config, Client interface).

Mock-based tests that don't require real devices.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from omni_sdk.device import Device
from omni_sdk.client import Client
from omni_sdk.config import (
    ConfigLoader,
    DeviceConfig,
    SshConfig,
    SerialConfig,
    GlobalConfig,
    SdkConfig,
)
from omni_sdk.result import Result, ErrorKinds, create_error_result


class TestClientInterface:
    """Tests for Client ABC interface."""

    def test_client_is_abstract(self):
        """Client interface cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Client()

    def test_client_has_required_methods(self):
        """Client interface defines all required methods."""
        required_methods = [
            "name",
            "version",
            "initialize",
            "connect",
            "disconnect",
            "is_connected",
            "send",
            "receive",
            "send_and_receive",
            "capabilities",
        ]
        for method in required_methods:
            assert hasattr(Client, method)


class TestDevice:
    """Tests for Device container."""

    def setup_method(self):
        """Setup: Create a device object."""
        self.device_config = {
            "id": "test-device",
            "name": "Test Device",
            "clients": {},
            "metadata": {"location": "Lab"},
        }
        self.device = Device("test-device", self.device_config)

    def test_device_creation(self):
        """Device can be created with config."""
        assert self.device.device_id == "test-device"
        assert self.device.name == "Test Device"
        assert self.device.clients == {}

    def test_device_repr(self):
        """Device has meaningful repr."""
        repr_str = repr(self.device)
        assert "test-device" in repr_str
        assert "Test Device" in repr_str

    def test_list_clients(self):
        """list_clients returns list of client names."""
        assert self.device.list_clients() == []

    def test_list_capabilities(self):
        """list_capabilities returns empty list initially."""
        assert self.device.list_capabilities() == []

    def test_get_client_not_found(self):
        """get_client returns error for non-existent client."""
        result = self.device.get_client("ssh")
        assert result.is_err
        assert result._error.kind == ErrorKinds.DEVICE_ERROR
        assert "not found" in result._error.message.lower()

    def test_add_client_duplicate(self):
        """Adding duplicate client returns error."""
        mock_client = Mock(spec=Client)
        mock_client.name = "ssh"

        config = {}
        mock_client.initialize.return_value = Result.ok(None)

        # First add succeeds
        result = self.device.add_client(mock_client)
        assert result.is_ok

        # Second add fails
        result = self.device.add_client(mock_client)
        assert result.is_err
        assert "already exists" in result._error.message.lower()

    def test_add_client_capability_auto_discovery(self):
        """Capabilities are auto-discovered from client."""
        mock_client = Mock(spec=Client)
        mock_client.name = "ssh"
        mock_client.initialize.return_value = Result.ok(None)
        mock_client.capabilities.return_value = {
            "execute": "Execute command",
            "file_transfer": "Transfer files",
        }

        config = {"host": "192.168.1.1"}
        mock_client.initialize.return_value = Result.ok(None)

        result = self.device.add_client(mock_client)
        assert result.is_ok

        # Check capabilities
        caps = self.device.list_capabilities()
        assert "execute" in caps
        assert "file_transfer" in caps

    def test_execute_capability_not_found(self):
        """Executing non-existent capability returns error."""
        result = self.device.execute("nonexistent", "arg")
        assert result.is_err
        assert result._error.kind == ErrorKinds.DEVICE_ERROR

    def test_execute_capability_client_not_found(self):
        """Executing capability when client not found returns error."""
        # Manually add capability without client (shouldn't happen but test robustness)
        self.device.capabilities["execute"] = {
            "client": "missing_client",
            "description": "Test",
        }

        result = self.device.execute("execute", "command")
        assert result.is_err
        assert result._error.kind == ErrorKinds.DEVICE_ERROR

    def test_connect_all_no_clients(self):
        """connect_all succeeds with no clients."""
        result = self.device.connect_all()
        assert result.is_ok

    def test_disconnect_all_succeeds_always(self):
        """disconnect_all always succeeds (logs errors but continues)."""
        result = self.device.disconnect_all()
        assert result.is_ok

    def test_get_status(self):
        """get_status returns device and client status."""
        status = self.device.get_status()
        assert status["device_id"] == "test-device"
        assert status["name"] == "Test Device"
        assert status["clients"] == {}
        assert status["capabilities"] == []

    def test_add_client_initialize_failure(self):
        """When client initialization fails, add_client propagates error."""
        mock_client = Mock(spec=Client)
        mock_client.name = "ssh"

        error = create_error_result(
            kind=ErrorKinds.CONFIG_ERROR, message="Initialize failed"
        )

        mock_client.initialize.return_value = error
        mock_client.capabilities.return_value = {}

        config = {"host": "192.168.1.1"}

        result = self.device.add_client(mock_client)
        assert result.is_err
        assert result == error

        # Client should not be added
        assert "ssh" not in self.device.clients


class TestConfigModels:
    """Tests for Pydantic config models."""

    def test_ssh_config_valid(self):
        """Valid SSH config passes validation."""
        config = SshConfig(
            host="192.168.1.1", port=22, username="admin", password="secret"
        )
        assert config.host == "192.168.1.1"
        assert config.port == 22

    def test_ssh_config_invalid_port(self):
        """Invalid port raises validation error."""
        with pytest.raises(ValueError, match="Port must be between"):
            SshConfig(host="192.168.1.1", port=70000, username="admin")

    def test_ssh_config_missing_required(self):
        """Missing required fields raise validation error."""
        with pytest.raises(ValueError, match="Missing required"):
            SshConfig(host="192.168.1.1")

    def test_serial_config_valid(self):
        """Valid serial config passes validation."""
        config = SerialConfig(port="/dev/ttyUSB0", baud_rate=115200)
        assert config.port == "/dev/ttyUSB0"
        assert config.baud_rate == 115200

    def test_serial_config_invalid_baud_rate(self):
        """Invalid baud rate raises validation error."""
        with pytest.raises(ValueError, match="Invalid baud rate"):
            SerialConfig(port="/dev/ttyUSB0", baud_rate=12345)

    def test_device_config_valid(self):
        """Valid device config passes validation."""
        config = DeviceConfig(id="device-001", name="Test Device")
        assert config.id == "device-001"

    def test_device_config_invalid_id(self):
        """Invalid device ID raises validation error."""
        with pytest.raises(ValueError, match="Device ID must be"):
            DeviceConfig(id="invalid device!", name="Test Device")

    def test_global_config_defaults(self):
        """Global config has correct defaults."""
        config = GlobalConfig()
        assert config.log_level == "info"
        assert config.default_timeout_ms == 5000
        assert config.retry_attempts == 3

    def test_global_config_invalid_log_level(self):
        """Invalid log level raises validation error."""
        with pytest.raises(ValueError, match="Invalid log level"):
            GlobalConfig(log_level="invalid")

    def test_sdk_config_valid(self):
        """SdkConfig can be created with devices."""
        sdk_config = SdkConfig(
            devices=[
                DeviceConfig(id="device-001", name="Device 1"),
                DeviceConfig(id="device-002", name="Device 2"),
            ]
        )
        assert len(sdk_config.devices) == 2


class TestConfigLoader:
    """Tests for ConfigLoader."""

    def test_load_file_not_found(self):
        """Loading non-existent file returns error."""
        result = ConfigLoader.load("nonexistent.toml")
        assert result.is_err
        assert result._error.kind == ErrorKinds.CONFIG_NOT_FOUND_ERROR

    def test_validate_empty_data(self):
        """Validating empty data returns basic config."""
        data = {"global": {}, "devices": []}
        result = ConfigLoader.validate(data)
        assert result.is_ok
        config = result.unwrap()
        assert len(config.devices) == 0

    def test_validate_devices(self):
        """Validating with devices creates SdkConfig."""
        data = {
            "global": {"log_level": "debug"},
            "devices": [{"id": "device-001", "name": "Device 1", "clients": {}}],
        }
        result = ConfigLoader.validate(data)
        assert result.is_ok
        config = result.unwrap()
        assert len(config.devices) == 1
        assert config.devices[0].id == "device-001"
        assert config.global_config.log_level == "debug"

    def test_validate_invalid_data(self):
        """Invalid data returns validation error."""
        data = {"devices": "not-a-list"}
        result = ConfigLoader.validate(data)
        assert result.is_err
        assert result._error.kind == ErrorKinds.CONFIG_VALIDATION_ERROR

    def test_validate_duplicate_device_ids(self):
        """Duplicate device IDs raise validation error."""
        data = {
            "devices": [
                {"id": "device-001", "name": "Device 1", "clients": {}},
                {"id": "device-001", "name": "Device 2", "clients": {}},
            ]
        }
        result = ConfigLoader.validate(data)
        assert result.is_err
        assert "Duplicate device IDs" in result._error.message

    def test_get_client_config_not_found(self):
        """Getting config for non-existent client returns error."""
        device_config = DeviceConfig(id="device-001", name="Device 1", clients={})
        result = ConfigLoader.get_client_config(device_config, "ssh")
        assert result.is_err
        assert "not found" in result._error.message.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
