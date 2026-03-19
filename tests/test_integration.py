"""
Integration tests for SDK framework using mocked connections.

Tests full workflow from config loading to device communication.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import tomli

from omni_sdk import (
    initialize_from_config,
    connect_device,
    SshClient,
    SerialClient,
    ConfigLoader,
    DeviceConfig,
    SdkConfig,
)
from omni_sdk.result import Result, ErrorKinds, create_error_result


class TestIntegrationWorkflow:
    """Tests for complete SDK workflow."""

    @pytest.fixture
    def sample_config(self):
        """Create sample devices.toml configuration."""
        return """
[global]
log_level = "debug"

[[devices]]
id = "device-001"
name = "Test Router"

[devices.clients.ssh]
  timeout_ms = 5000

[[devices]]
id = "device-002"
name = "Test Serial"

[devices.clients.serial]
  port = "/dev/ttyUSB0"
  baud_rate = 115200
"""

    @pytest.fixture
    def temp_config_file(self, tmp_path, sample_config):
        """Create temporary config file."""
        config_file = tmp_path / "devices.toml"
        config_file.write_text(sample_config, encoding="utf-8")
        return config_file

    def test_initialize_from_config_loads_devices(self, temp_config_file):
        """initialize_from_config loads devices from config file."""
        with patch("omni_sdk.SshClient") as MockSshClient:
            with patch("omni_sdk.SerialClient") as MockSerialClient:
                result = initialize_from_config(str(temp_config_file))

                assert result.is_ok
                devices = result.unwrap()
                assert "device-001" in devices
                assert "device-002" in devices
                assert len(devices) == 2

    def test_initialize_from_config_creates_ssh_client(self, temp_config_file):
        """SSH client is created and configured from config."""
        with patch("omni_sdk.SshClient") as MockSshClient:
            # Track if client is instantiated and initialized
            client_instances = []

            def mock_init(self):
                client_instances.append(self)
                self.initialize.return_value = Result.ok(None)
                self.name = "ssh"
                self.capabilities.return_value = {
                    "execute": "Execute command",
                    "get_status": "Get status",
                }

            MockSshClient.side_effect = lambda: Mock(spec=SshClient)
            MockSshClient.__init__ = mock_init

            result = initialize_from_config(str(temp_config_file))

            assert result.is_ok
            devices = result.unwrap()

            assert "device-001" in devices
            device = devices["device-001"]
            assert "ssh" in device.list_clients()

    @pytest.fixture
    def mock_ssh_client(self):
        """Create a fully mocked SSH client for testing."""
        client = Mock(spec=SshClient)
        client.name = "ssh"
        client.version = "1.0.0"
        client.capabilities.return_value = {
            "execute": "Execute shell command",
            "get_status": "Get SSH status",
        }

        def mock_initialize(config):
            client.config = config
            return Result.ok(None)

        client.initialize = Mock(side_effect=mock_initialize)
        client.connect = Mock(return_value=Result.ok(None))
        client.disconnect = Mock(return_value=Result.ok(None))
        client.is_connected = Mock(return_value=True)
        client.send = Mock(return_value=Result.ok(None))
        client.receive = Mock(return_value=Result.ok("response"))
        client.send_and_receive = Mock(return_value=Result.ok("response"))
        client.execute = Mock(return_value=Result.ok("command output"))

        return client

    def test_connect_device_connects_all_clients(self, mock_ssh_client):
        """connect_device connects all clients on device."""
        with (
            patch("omni_sdk.SshClient") as MockSshClient,
            patch("omni_sdk.SerialClient") as MockSerialClient,
        ):
            MockSerialClient.return_value = Mock(spec=SerialClient)

            # Serial client mock
            serial_client = Mock(spec=SerialClient)
            serial_client.name = "serial"
            serial_client.version = "1.0.0"
            serial_client.capabilities.return_value = {"send": "Send data"}
            serial_client.initialize.return_value = Result.ok(None)
            serial_client.connect.return_value = Result.ok(None)
            MockSerialClient.return_value = serial_client

            # Create device with both clients
            device_config = {
                "id": "test-device",
                "name": "Test Device",
                "clients": {
                    "ssh": {"host": "192.168.1.1"},
                    "serial": {"port": "/dev/ttyUSB0"},
                },
            }

            from omni_sdk import Device

            device = Device("test-device", device_config)
            device.add_client(mock_ssh_client)
            device.add_client(serial_client)

            devices = {"test-device": device}

            result = connect_device("test-device", devices)

            assert result.is_ok
            device = result.unwrap()

            # Both connect() should have been called
            mock_ssh_client.connect.assert_called_once()
            serial_client.connect.assert_called_once()

    def test_device_execute_command_via_ssh(self, mock_ssh_client):
        """Device.execute() dispatches to SSH client's execute method."""
        device_config = {
            "id": "test-device",
            "name": "Test Device",
            "clients": {"ssh": {"host": "192.168.1.1"}},
        }

        from omni_sdk import Device

        device = Device("test-device", device_config)
        device.add_client(mock_ssh_client)

        result = device.execute("execute", "show version")

        assert result.is_ok
        output = result.unwrap()
        assert output == "command output"

        # Ensure the mock's execute was called
        mock_ssh_client.execute.assert_called_once_with("show version")

    def test_device_capability_auto_discovery(self, mock_ssh_client):
        """Capabilities are auto-discovered when client is added."""
        device_config = {
            "id": "test-device",
            "name": "Test Device",
            "clients": {"ssh": {"host": "192.168.1.1"}},
        }

        from omni_sdk import Device

        device = Device("test-device", device_config)

        # Add capability via client
        mock_ssh_client.capabilities.return_value = {
            "execute": "Execute command",
            "file_transfer": "Transfer files",
            "get_status": "Get status",
        }

        result = device.add_client(mock_ssh_client)

        assert result.is_ok
        caps = device.list_capabilities()
        assert "execute" in caps
        assert "file_transfer" in caps
        assert "get_status" in caps

        # Verify capability metadata
        execute_info = device.capabilities["execute"]
        assert execute_info["client"] == "ssh"
        assert execute_info["description"] == "Execute command"

    def test_result_error_propagation_in_chain(self):
        """Result errors propagate correctly through operation chain."""

        def load_config(path: str) -> Result[dict]:
            return create_error_result(
                kind=ErrorKinds.CONFIG_NOT_FOUND_ERROR, message="Config file not found"
            )

        result = (
            load_config("nonexistent.toml")
            .and_then(lambda cfg: initialize_from_config("config.toml"))
            .and_then(lambda devices: connect_device("device-001", devices))
        )

        # Should fail at first step
        assert result.is_err
        assert result._error.kind == ErrorKinds.CONFIG_NOT_FOUND_ERROR

    def test_config_validation_error_propagation(self):
        """Config validation errors propagate correctly."""
        invalid_config = """
[global]
log_level = "invalid"

[[devices]]
id = "invalid device!"  # Invalid ID
name = "Test"

[devices.clients.unknown_type]
  foo = "bar"
"""

        result = ConfigLoader.validate(tomli.loads(invalid_config))

        assert result.is_err
        # Could be either validation error for ID or unknown client type
        assert result._error.kind in [
            ErrorKinds.CONFIG_VALIDATION_ERROR,
            ErrorKinds.CONFIG_ERROR,
        ]

    def test_multiple_clients_on_single_device(self, mock_ssh_client):
        """Single device can have multiple clients."""
        with patch("omni_sdk.SerialClient") as MockSerialClient:
            serial_client = Mock(spec=SerialClient)
            serial_client.name = "serial"
            serial_client.version = "1.0.0"
            serial_client.capabilities.return_value = {
                "send": "Send data",
                "receive": "Receive data",
            }
            serial_client.initialize.return_value = Result.ok(None)
            serial_client.connect.return_value = Result.ok(None)
            serial_client.is_connected = Mock(return_value=True)
            SerialClient.return_value = serial_client

            device_config = {
                "id": "multi-client-device",
                "name": "Multi-Protocol Gateway",
                "clients": {
                    "ssh": {"host": "192.168.1.1"},
                    "serial": {"port": "/dev/ttyUSB0"},
                },
            }

            from omni_sdk import Device

            device = Device("multi-client-device", device_config)
            device.add_client(mock_ssh_client)
            device.add_client(serial_client)

            clients = device.list_clients()
            assert len(clients) == 2
            assert "ssh" in clients
            assert "serial" in clients

            # Combine capabilities
            all_caps = device.list_capabilities()
            assert "execute" in all_caps  # From SSH
            assert "send" in all_caps  # From Serial
            assert "receive" in all_caps


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
