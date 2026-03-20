"""
Cross-client integration tests for SSH + Serial coordination.

Tests multi-protocol device workflows and client coordination.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from omni_sdk.clients.ssh_client import SshClient
from omni_sdk.clients.serial_client import SerialClient
from omni_sdk.device import Device
from omni_sdk.result import Result


class TestMultiProtocolDeviceIntegration:
    """Integration tests for device with multiple client types."""

    @pytest.fixture
    def mock_ssh_client(self):
        """Create mock SSH client."""
        ssh = Mock(spec=SshClient)
        ssh.name = "ssh"
        ssh.version = "1.0.0"
        ssh.capabilities.return_value = {
            "execute": "Execute SSH command",
            "file_transfer": "Transfer files",
            "get_status": "Get SSH status",
        }
        ssh.initialize.return_value = Result.ok(None)
        ssh.connect.return_value = Result.ok(None)
        ssh.disconnect.return_value = Result.ok(None)
        ssh.is_connected = Mock(return_value=True)
        ssh.execute = Mock(return_value=Result.ok("SSH output"))
        ssh.send = Mock(return_value=Result.ok(None))
        ssh.receive = Mock(return_value=Result.ok("received"))
        ssh.send_and_receive = Mock(return_value=Result.ok("response"))
        return ssh

    @pytest.fixture
    def mock_serial_client(self):
        """Create mock Serial client."""
        serial = Mock(spec=SerialClient)
        serial.name = "serial"
        serial.version = "1.0.0"
        serial.capabilities.return_value = {
            "send": "Send serial data",
            "receive": "Receive serial data",
            "get_status": "Get serial status",
            "configure": "Configure serial port",
        }
        serial.initialize.return_value = Result.ok(None)
        serial.connect.return_value = Result.ok(None)
        serial.disconnect.return_value = Result.ok(None)
        serial.is_connected = Mock(return_value=True)
        serial.send = Mock(return_value=Result.ok(None))
        serial.receive = Mock(return_value=Result.ok("serial response"))
        serial.send_and_receive = Mock(return_value=Result.ok("serial response"))
        return serial

    @pytest.fixture
    def multi_protocol_device(self, mock_ssh_client, mock_serial_client):
        """Create device with both SSH and Serial clients."""
        device_config = {
            "id": "multi-device",
            "name": "Multi-Protocol Gateway",
            "clients": {
                "ssh": {"host": "192.168.1.1"},
                "serial": {"port": "/dev/ttyUSB0", "baud_rate": 115200},
            },
        }

        device = Device("multi-device", device_config)
        device.add_client(mock_ssh_client)
        device.add_client(mock_serial_client)
        return device

    def test_device_with_multiple_clients(self, multi_protocol_device):
        """Test single device can have multiple clients."""
        clients = multi_protocol_device.list_clients()
        assert len(clients) == 2
        assert "ssh" in clients
        assert "serial" in clients

    def test_combined_capabilities(self, multi_protocol_device):
        """Test capabilities are combined from both clients."""
        all_caps = multi_protocol_device.list_capabilities()

        # SSH capabilities
        assert "execute" in all_caps
        assert "file_transfer" in all_caps

        # Serial capabilities
        assert "send" in all_caps
        assert "receive" in all_caps

    def test_capability_routing_through_device(
        self, multi_protocol_device, mock_ssh_client, mock_serial_client
    ):
        """Test Device.execute() routes to correct client."""
        # SSH capability
        result = multi_protocol_device.execute("execute", "show version")
        assert result.is_ok
        mock_ssh_client.execute.assert_called_once_with("show version")

        # Serial capability
        result = multi_protocol_device.execute("send", "AT+CMD")
        assert result.is_ok
        mock_serial_client.send.assert_called_once_with("AT+CMD")

    def test_connect_all_clients(
        self, multi_protocol_device, mock_ssh_client, mock_serial_client
    ):
        """Test connecting all clients on device."""
        result = multi_protocol_device.connect_all()
        assert result.is_ok

        mock_ssh_client.connect.assert_called_once()
        mock_serial_client.connect.assert_called_once()

    def test_disconnect_all_clients(
        self, multi_protocol_device, mock_ssh_client, mock_serial_client
    ):
        """Test disconnecting all clients on device."""
        multi_protocol_device.connect_all()

        result = multi_protocol_device.disconnect_all()
        assert result.is_ok

        mock_ssh_client.disconnect.assert_called_once()
        mock_serial_client.disconnect.assert_called_once()

    def test_sequential_execution_across_protocols(
        self, multi_protocol_device, mock_ssh_client, mock_serial_client
    ):
        """Test sequential execution across SSH and Serial protocols."""
        # Execute via SSH
        result1 = multi_protocol_device.execute("execute", "ssh command")
        assert result1.is_ok

        # Execute via Serial
        result2 = multi_protocol_device.execute("send_and_receive", "serial command")
        assert result2.is_ok

        # Execute via SSH again
        result3 = multi_protocol_device.execute("execute", "another ssh command")
        assert result3.is_ok

        # Verify each client was called
        assert mock_ssh_client.execute.call_count == 2
        assert mock_serial_client.send_and_receive.call_count == 1


class TestCoordinatedWorkflows:
    """Tests for coordinated SSH + Serial workflows."""

    @pytest.fixture
    def mock_ssh_client(self):
        """Create mock SSH client for coordinated tests."""
        ssh = Mock(spec=SshClient)
        ssh.name = "ssh"
        ssh.capabilities.return_value = {
            "execute": "Execute SSH command",
            "get_status": "Get SSH status",
        }
        ssh.initialize.return_value = Result.ok(None)
        ssh.connect.return_value = Result.ok(None)
        ssh.disconnect.return_value = Result.ok(None)
        ssh.execute = Mock(return_value=Result.ok("SSH: Done"))
        return ssh

    @pytest.fixture
    def mock_serial_client(self):
        """Create mock Serial client for coordinated tests."""
        serial = Mock(spec=SerialClient)
        serial.name = "serial"
        serial.capabilities.return_value = {
            "send": "Send serial data",
            "receive": "Receive serial data",
        }
        serial.initialize.return_value = Result.ok(None)
        serial.connect.return_value = Result.ok(None)
        serial.disconnect.return_value = Result.ok(None)
        serial.send_and_receive = Mock(return_value=Result.ok("Serial: OK"))
        return serial

    @pytest.fixture
    def coordinated_device(self, mock_ssh_client, mock_serial_client):
        """Create device for coordinated tests."""
        device_config = {
            "id": "coordinated-device",
            "name": "Coordinated Test Device",
            "clients": {
                "ssh": {"host": "192.168.1.1"},
                "serial": {"port": "/dev/ttyUSB0"},
            },
        }

        device = Device("coordinated-device", device_config)
        device.add_client(mock_ssh_client)
        device.add_client(mock_serial_client)
        return device

    def test_ssh_serial_task_workflow(
        self, coordinated_device, mock_ssh_client, mock_serial_client
    ):
        """Test complete workflow combining SSH and Serial tasks."""
        # Step 1: Check SSH status
        result1 = coordinated_device.execute("get_status", None)
        assert result1.is_ok

        # Step 2: Send config via Serial
        result2 = coordinated_device.execute("send_and_receive", "SET_CONFIG\r\n")
        assert result2.is_ok

        # Step 3: Execute command via SSH to verify
        result3 = coordinated_device.execute("execute", "verify config")
        assert result3.is_ok

        # Step 4: Get status via Serial
        result4 = coordinated_device.execute("receive", None)
        assert result4.is_ok

        # Verify coordination
        assert mock_ssh_client.execute.call_count == 2
        assert mock_ssh_client.capabilities.call_count == 1
        assert mock_serial_client.send_and_receive.call_count == 1

    def test_dual_client_status_check(
        self, coordinated_device, mock_ssh_client, mock_serial_client
    ):
        """Test checking status of both clients."""
        # SSH status
        result1 = coordinated_device.execute("get_status", None)
        assert result1.is_ok

        # Serial status
        result2 = coordinated_device.execute("get_status", None)
        assert result2.is_ok

        # Both clients should be queried
        assert mock_ssh_client.capabilities.call_count >= 1
        assert mock_serial_client.capabilities.call_count >= 1

    def test_concurrent_ssh_serial_operations(
        self, coordinated_device, mock_ssh_client, mock_serial_client
    ):
        """Test concurrent SSH and Serial operations."""
        # Simulate concurrent operations
        results = []

        # Multiple SSH operations
        for i in range(3):
            result = coordinated_device.execute("execute", f"cmd{i}")
            results.append(result)
            assert result.is_ok

        # Multiple Serial operations
        for i in range(3):
            result = coordinated_device.execute("send_and_receive", f"AT{i}")
            results.append(result)
            assert result.is_ok

        # Verify all operations succeeded
        for result in results:
            assert result.is_ok

        assert mock_ssh_client.execute.call_count == 3
        assert mock_serial_client.send_and_receive.call_count == 3

    def test_error_propagation_from_client(self, coordinated_device, mock_ssh_client):
        """Test error propagation when client operation fails."""
        # Make SSH execute fail
        mock_ssh_client.execute.return_value = Result.err("SSH failed")

        result = coordinated_device.execute("execute", "failing-cmd")

        # Error should propagate
        assert result.is_err


class TestClientReusePatterns:
    """Tests for client connection state management and reuse."""

    @pytest.fixture
    def mock_reusable_ssh(self):
        """Create mock SSH that tracks connection state."""
        ssh = Mock(spec=SshClient)
        ssh.name = "ssh"
        ssh.capabilities.return_value = {"execute": "Execute"}
        ssh.initialize.return_value = Result.ok(None)
        ssh.connect.return_value = Result.ok(None)
        ssh.disconnect.return_value = Result.ok(None)
        ssh.is_connected = Mock(side_effect=[False, True, True, True, True])
        ssh.execute = Mock(return_value=Result.ok("output"))
        return ssh

    @pytest.fixture
    def mock_reusable_serial(self):
        """Create mock Serial that tracks connection state."""
        serial = Mock(spec=SerialClient)
        serial.name = "serial"
        serial.capabilities.return_value = {"send": "Send"}
        serial.initialize.return_value = Result.ok(None)
        serial.connect.return_value = Result.ok(None)
        serial.disconnect.return_value = Result.ok(None)
        serial.is_connected = Mock(side_effect=[False, True, True, True, True])
        serial.send_and_receive = Mock(return_value=Result.ok("response"))
        return serial

    @pytest.fixture
    def reuse_device(self, mock_reusable_ssh, mock_reusable_serial):
        """Create device for reuse pattern tests."""
        device_config = {
            "id": "reuse-device",
            "name": "Client Reuse Test Device",
            "clients": {
                "ssh": {"host": "192.168.1.1"},
                "serial": {"port": "/dev/ttyUSB0"},
            },
        }

        device = Device("reuse-device", device_config)
        device.add_client(mock_reusable_ssh)
        device.add_client(mock_reusable_serial)
        return device

    def test_client_connection_states(self, reuse_device):
        """Test client connection states through lifecycle."""
        # Initially disconnected
        assert not reuse_device.is_connected("ssh")
        assert not reuse_device.is_connected("serial")

        # Connect all
        result = reuse_device.connect_all()
        assert result.is_ok

        # Verify connected
        assert reuse_device.is_connected("ssh")
        assert reuse_device.is_connected("serial")

        # Disconnect all
        result = reuse_device.disconnect_all()
        assert result.is_ok

    def test_client_reuse_for_multiple_operations(
        self, reuse_device, mock_reusable_ssh, mock_reusable_serial
    ):
        """Test client reuse for multiple operations."""
        # Connect once
        reuse_device.connect_all()

        # Perform multiple operations without reconnecting
        for i in range(5):
            result = reuse_device.execute("execute", f"cmd{i}")
            assert result.is_ok

            result = reuse_device.execute("send_and_receive", f"AT{i}")
            assert result.is_ok

        # Verify only one connection each
        assert mock_reusable_ssh.connect.call_count == 1
        assert mock_reusable_serial.connect.call_count == 1

    def test_client_state_after_operations(self, reuse_device):
        """Test client state remains valid after operations."""
        reuse_device.connect_all()

        # Perform operations
        reuse_device.execute("execute", "cmd1")
        reuse_device.execute("send_and_receive", "AT1")
        reuse_device.execute("execute", "cmd2")
        reuse_device.execute("send_and_receive", "AT2")

        # Clients should still be connected
        assert reuse_device.is_connected("ssh")
        assert reuse_device.is_connected("serial")

    def test_client_cleanup_on_device_destruction(
        self, reuse_device, mock_reusable_ssh, mock_reusable_serial
    ):
        """Test clients are properly cleaned up."""
        reuse_device.connect_all()

        # Trigger disconnect
        reuse_device.disconnect_all()

        # Verify disconnect was called
        mock_reusable_ssh.disconnect.assert_called_once()
        mock_reusable_serial.disconnect.assert_called_once()


class TestCrossClientErrorHandling:
    """Tests for error handling in cross-client scenarios."""

    @pytest.fixture
    def mock_failing_ssh(self):
        """Create mock SSH that sometimes fails."""
        ssh = Mock(spec=SshClient)
        ssh.name = "ssh"
        ssh.capabilities.return_value = {"execute": "Execute"}
        ssh.initialize.return_value = Result.ok(None)
        ssh.connect.return_value = Result.ok(None)
        ssh.disconnect.return_value = Result.ok(None)
        # Every other execute fails
        ssh.execute.side_effect = [
            Result.ok("output1"),
            Result.err("SSH failure"),
            Result.ok("output3"),
            Result.ok("output4"),
        ]
        return ssh

    @pytest.fixture
    def mock_failing_serial(self):
        """Create mock Serial that sometimes fails."""
        serial = Mock(spec=SerialClient)
        serial.name = "serial"
        serial.capabilities.return_value = {"send": "Send"}
        serial.initialize.return_value = Result.ok(None)
        serial.connect.return_value = Result.ok(None)
        serial.disconnect.return_value = Result.ok(None)
        # First send fails, others succeed
        serial.send_and_receive.side_effect = [
            Result.err("Serial error"),
            Result.ok("response2"),
            Result.ok("response3"),
        ]
        return serial

    @pytest.fixture
    def failing_device(self, mock_failing_ssh, mock_failing_serial):
        """Create device with failing clients."""
        device_config = {
            "id": "failing-device",
            "name": "Error Recovery Test Device",
            "clients": {
                "ssh": {"host": "192.168.1.1"},
                "serial": {"port": "/dev/ttyUSB0"},
            },
        }

        device = Device("failing-device", device_config)
        device.add_client(mock_failing_ssh)
        device.add_client(mock_failing_serial)
        return device

    def test_one_client_failure_doesnt_affect_other(self, failing_device):
        """Test failure in one client doesn't affect the other client."""
        # SSH command fails
        result1 = failing_device.execute("execute", "fail-cmd")
        assert result1.is_err

        # Serial command succeeds
        result2 = failing_device.execute("send_and_receive", "AT-CMD")
        assert result2.is_ok

    def test_continue_after_client_failure(self, failing_device):
        """Test continuing operations after client failure."""
        # SSH command fails
        result1 = failing_device.execute("execute", "fail-cmd")
        assert result1.is_err

        # Next SSH command succeeds
        result2 = failing_device.execute("execute", "good-cmd")
        assert result2.is_ok

        # Serial command succeeds
        result3 = failing_device.execute("send_and_receive", "AT-CMD2")
        assert result3.is_ok

    def test_error_isolation_between_clients(self, failing_device):
        """Test errors are isolated between SSH and Serial clients."""
        results = []

        # Mix of failing and succeeding operations
        results.append(failing_device.execute("execute", "fail-cmd"))
        results.append(failing_device.execute("execute", "good-cmd"))
        results.append(failing_device.execute("send_and_receive", "AT-fail"))
        results.append(failing_device.execute("send_and_receive", "AT-good"))

        # Only two should succeed
        successes = sum(1 for r in results if r.is_ok)
        assert successes == 2

    def test_device_status_with_failing_clients(self, failing_device):
        """Test device status even when clients are failing."""
        # Get capabilities (should work even if operations fail)
        caps = failing_device.list_capabilities()
        assert "execute" in caps
        assert "send" in caps

    def test_disconnect_all_handles_partial_failures(self, failing_device):
        """Test disconnect_all handles partial connection failures."""
        # Connect some clients
        failing_device.connect_all()

        # Disconnect all (should complete even if one fails)
        result = failing_device.disconnect_all()
        assert result.is_ok


class TestClientCoordinationAdvanced:
    """Advanced tests for complex client coordination scenarios."""

    @pytest.fixture
    def mock_advanced_ssh(self):
        """Create advanced mock SSH for complex scenarios."""
        ssh = Mock(spec=SshClient)
        ssh.name = "ssh"
        ssh.capabilities.return_value = {
            "execute": "Execute",
            "file_transfer": "Transfer",
            "get_status": "Status",
        }
        ssh.initialize.return_value = Result.ok(None)
        ssh.connect.return_value = Result.ok(None)
        ssh.disconnect.return_value = Result.ok(None)
        ssh.execute = Mock(return_value=Result.ok("SSH output"))
        ssh.file_transfer = Mock(return_value=Result.ok(None))
        return ssh

    @pytest.fixture
    def mock_advanced_serial(self):
        """Create advanced mock Serial for complex scenarios."""
        serial = Mock(spec=SerialClient)
        serial.name = "serial"
        serial.capabilities.return_value = {
            "send": "Send",
            "receive": "Receive",
            "configure": "Configure",
            "get_status": "Status",
        }
        serial.initialize.return_value = Result.ok(None)
        serial.connect.return_value = Result.ok(None)
        serial.disconnect.return_value = Result.ok(None)
        serial.send_and_receive = Mock(return_value=Result.ok("Serial response"))
        serial.configure = Mock(return_value=Result.ok(None))
        return serial

    @pytest.fixture
    def advanced_device(self, mock_advanced_ssh, mock_advanced_serial):
        """Create device for advanced coordination tests."""
        device_config = {
            "id": "advanced-device",
            "name": "Advanced Coordination Test",
            "clients": {
                "ssh": {"host": "192.168.1.1"},
                "serial": {"port": "/dev/ttyUSB0"},
            },
        }

        device = Device("advanced-device", device_config)
        device.add_client(mock_advanced_ssh)
        device.add_client(mock_advanced_serial)
        return device

    def test_capability_discovery_and_routing(self, advanced_device):
        """Test automatic capability discovery and routing."""
        # List all discovered capabilities
        caps = advanced_device.list_capabilities()

        # Verify all SSH capabilities
        assert "execute" in caps
        assert "file_transfer" in caps
        assert "get_status" in caps

        # Verify all Serial capabilities
        assert "send" in caps
        assert "receive" in caps
        assert "configure" in caps

    def test_complex_workflow_mixed_protocols(self, advanced_device):
        """Test complex workflow mixing SSH and Serial operations."""
        # Step 1: Get SSH status
        result1 = advanced_device.execute("get_status", None)
        assert result1.is_ok

        # Step 2: Configure via Serial
        result2 = advanced_device.execute("configure", {"baud_rate": 115200})
        assert result2.is_ok

        # Step 3: Execute SSH command with new config
        result3 = advanced_device.execute("execute", "verify-config")
        assert result3.is_ok

        # Step 4: Transfer file via SSH
        result4 = advanced_device.execute(
            "file_transfer", {"local": "a.txt", "remote": "/tmp/a.txt"}
        )
        assert result4.is_ok

        # Step 5: Query via Serial
        result5 = advanced_device.execute("send_and_receive", "GET_STATUS")
        assert result5.is_ok

    def test_capability_metadata_verification(
        self, advanced_device, mock_advanced_ssh, mock_advanced_serial
    ):
        """Test capability metadata is correctly tracked."""
        # Check SSH execute capability
        caps = advanced_device.list_capabilities()
        execute_cap = caps["execute"]
        assert execute_cap["client"] == "ssh"

        # Check Serial send capability
        send_cap = caps["send"]
        assert send_cap["client"] == "serial"

    def test_state_consistency_across_protocols(self, advanced_device):
        """Test client state consistency across both protocols."""
        # Connect all
        advanced_device.connect_all()

        # Verify both are connected
        assert advanced_device.is_connected("ssh")
        assert advanced_device.is_connected("serial")

        # Perform operations
        advanced_device.execute("execute", "cmd")
        advanced_device.execute("send_and_receive", "AT")

        # State should remain consistent
        assert advanced_device.is_connected("ssh")
        assert advanced_device.is_connected("serial")

        # Disconnect all
        advanced_device.disconnect_all()

        # State should be consistent
        assert not advanced_device.is_connected("ssh")
        assert not advanced_device.is_connected("serial")

    def test_capability_order_independence(self, advanced_device):
        """Test capability invocation order is independent."""
        # Try different invocation orders
        orders = [
            ["execute", "send"],
            ["send", "execute"],
            ["configure", "execute", "send"],
            ["execute", "configure", "send"],
        ]

        for order in orders:
            # Disconnect to reset state
            advanced_device.disconnect_all()
            # Reconnect
            advanced_device.connect_all()

            # Execute in specified order
            for capability in order:
                if capability in ["execute", "file_transfer", "get_status"]:
                    result = advanced_device.execute(capability, "test-arg")
                    assert result.is_ok
                elif capability in ["send", "receive", "configure", "get_status"]:
                    result = advanced_device.execute(capability, None)
                    assert result.is_ok
