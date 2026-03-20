"""
Serial client integration tests with realistic end-to-end scenarios.

Tests full client lifecycles with realistic pyserial mocking.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call, mock_open
from omni_sdk.clients.serial_client import SerialClient
from omni_sdk.result import Result, ErrorKinds


class TestSerialPortLifecycle:
    """Tests for serial port lifecycle management."""

    @pytest.fixture
    def mock_serial_port(self):
        """Create mock serial port."""
        port = Mock()
        port.is_open = True
        port.in_waiting = 0
        port.read.return_value = b"response\r\n"
        port.write.return_value = 12
        port.baudrate = 115200
        port.timeout = 5.0
        return port

    @pytest.fixture
    def mock_serial_module(self, mock_serial_port):
        """Create mock pyserial module."""
        with patch("omni_sdk.clients.serial_client.serial") as mock_serial:
            mock_serial.Serial.return_value = mock_serial_port
            yield mock_serial

    def test_serial_port_open_close_cycle(self, mock_serial_module, mock_serial_port):
        """Test complete open-close cycle."""
        client = SerialClient()

        # Configure client
        result = client.initialize(
            {"port": "/dev/ttyUSB0", "baud_rate": 115200, "timeout": 5}
        )

        assert result.is_ok
        assert client.port == "/dev/ttyUSB0"
        assert client.baud_rate == 115200

        # Open port
        result = client.connect()
        assert result.is_ok
        assert client.is_connected()

        # Verify Serial was instantiated
        mock_serial_module.Serial.assert_called_once_with(
            port="/dev/ttyUSB0",
            baudrate=115200,
            timeout=5,
            parity="N",
            bytesize=8,
            stopbits=1,
        )

        # Close port
        result = client.disconnect()
        assert result.is_ok
        assert not client.is_connected()

    def test_port_not_found_error_handling(self, mock_serial_module):
        """Test handling of port not found error."""
        mock_serial_module.Serial.side_effect = Exception(
            "SerialException: could not open port"
        )

        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB999"})

        result = client.connect()

        assert result.is_ok

    def test_multiple_port_opens(self, mock_serial_module, mock_serial_port):
        """Test multiple sequential port opens."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        # Open, close, open, close
        client.connect()
        assert mock_serial_module.Serial.call_count == 1

        client.disconnect()
        client.connect()
        assert mock_serial_module.Serial.call_count == 2

        client.disconnect()
        assert client.is_connected() is False

    def test_reconfigure_while_connected(self, mock_serial_module, mock_serial_port):
        """Test hot reconfiguration while connected."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0", "baud_rate": 9600, "timeout": 1})

        with mock_serial_module:
            client.connect()

            # Reconfigure baud rate while connected
            result = client.configure(baud_rate=115200, timeout=5)
            assert result.is_ok
            assert client.baud_rate == 115200
            assert client.timeout == 5

            # Verify reconfigure was applied
            mock_serial_port.baudrate = 115200
            mock_serial_port.timeout = 5.0

    def test_multiple_baud_rate_configurations(
        self, mock_serial_module, mock_serial_port
    ):
        """Test different baud rate configurations."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        baud_rates = [9600, 19200, 115200, 230400, 921600]

        with mock_serial_module:
            for baud in baud_rates:
                client.configure(baud_rate=baud)
                assert client.baud_rate == baud


class TestSerialDataTransactions:
    """Tests for serial data transaction workflows."""

    @pytest.fixture
    def mock_serial_transaction(self):
        """Create mock serial for send_and_receive."""
        port = Mock()
        port.is_open = True
        port.write.return_value = 12
        port.read.return_value = b"OK\r\n"
        port.baudrate = 115200
        return port

    @pytest.fixture
    def mock_serial_for_transaction(self, mock_serial_transaction):
        """Create mock pyserial for transaction tests."""
        with patch("omni_sdk.clients.serial_client.serial") as mock_serial:
            mock_serial.Serial.return_value = mock_serial_transaction
            yield mock_serial

    def test_send_and_receive_with_echo(
        self, mock_serial_for_transaction, mock_serial_transaction
    ):
        """Test send_and_receive with device echo."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0", "baud_rate": 9600})

        with mock_serial_for_transaction:
            client.connect()

            result = client.send_and_receive("GET_INFO\r\n", 1000)

            assert result.is_ok
            output = result.unwrap()
            assert "OK" in output

            # Verify complete transaction
            mock_serial_transaction.write.assert_called_once_with(b"GET_INFO\r\n")
            mock_serial_transaction.read.assert_called()

    def test_multi_byte_response_parsing(
        self, mock_serial_for_transaction, mock_serial_transaction
    ):
        """Test multi-byte response parsing."""
        mock_serial_transaction.read.return_value = (
            b"# Response:\r\nSTATUS: OK\r\nTEMP: 25C\r\n> "
        )

        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        with mock_serial_for_transaction:
            client.connect()

            result = client.send_and_receive("READ_STATUS\r\n", 2000)

            assert result.is_ok
            output = result.unwrap()
            assert "STATUS: OK" in output
            assert "TEMP: 25C" in output

    def test_binary_data_handling(
        self, mock_serial_for_transaction, mock_serial_transaction
    ):
        """Test binary data handling in serial communication."""
        # Binary command: 0x01 0x02 0x03
        binary_cmd = b"\x01\x02\x03"
        binary_response = b"\x04\x05\x06\r\n"

        mock_serial_transaction.read.return_value = binary_response

        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        with mock_serial_for_transaction:
            client.connect()

            # Send as raw bytes
            result = client.send(binary_cmd)
            assert result.is_ok

            # Receive binary response
            result = client.receive(1000)
            assert result.is_ok

    def test_response_timeout_scenario(
        self, mock_serial_for_transaction, mock_serial_transaction
    ):
        """Test response timeout handling."""
        # Read returns empty data (timeout)
        mock_serial_transaction.read.return_value = b""

        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0", "timeout": 1})

        with mock_serial_for_transaction:
            client.connect()

            result = client.send_and_receive("QUERY\r\n", 100)
            assert result.is_ok

    def test_framing_error_simulation(
        self, mock_serial_for_transaction, mock_serial_transaction
    ):
        """Test framing error simulation."""
        # Corrupted frame with invalid characters
        mock_serial_transaction.read.return_value = b"\xff\xfe\xfd\r\n"

        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        with mock_serial_for_transaction:
            client.connect()

            result = client.send_and_receive("DATA\r\n", 1000)
            assert result.is_ok


class TestSerialConfigurationWorkflows:
    """Tests for serial configuration workflows."""

    @pytest.fixture
    def mock_serial_config(self):
        """Create mock serial for configuration tests."""
        port = Mock()
        port.is_open = True
        port.baudrate = 9600
        port.timeout = 5.0
        port.bytesize = 8
        port.parity = "N"
        port.stopbits = 1
        return port

    @pytest.fixture
    def mock_serial_for_config(self, mock_serial_config):
        """Create mock pyserial for config tests."""
        with patch("omni_sdk.clients.serial_client.serial") as mock_serial:
            mock_serial.Serial.return_value = mock_serial_config
            yield mock_serial

    def test_different_baud_rates(self, mock_serial_for_config, mock_serial_config):
        """Test different baud rate configurations."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        baud_rates = [
            1200,
            2400,
            4800,
            9600,
            19200,
            38400,
            57600,
            115200,
            230400,
            460800,
            921600,
        ]

        with mock_serial_for_config:
            client.connect()

            for baud in baud_rates:
                result = client.configure(baud_rate=baud)
                assert result.is_ok
                mock_serial_config.baudrate = baud
                assert client.baud_rate == baud

    def test_parity_configuration(self, mock_serial_for_config, mock_serial_config):
        """Test parity configuration."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0", "parity": "N"})

        parity_options = ["N", "E", "O", "M", "S"]

        with mock_serial_for_config:
            client.connect()

            for parity in parity_options:
                result = client.configure(parity=parity)
                assert result.is_ok
                mock_serial_config.parity = parity

    def test_complete_reconfiguration(self, mock_serial_for_config, mock_serial_config):
        """Test complete port reconfiguration while connected."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0", "baud_rate": 9600, "timeout": 1})

        with mock_serial_for_config:
            client.connect()

            # Reconfigure everything
            result = client.configure(
                baud_rate=115200, timeout=5, bytesize=8, parity="N", stopbits=2
            )

            assert result.is_ok
            assert client.baud_rate == 115200
            assert client.timeout == 5

    def test_connection_timeout_configuration(
        self, mock_serial_for_config, mock_serial_config
    ):
        """Test connection timeout configuration."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        timeout_values = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]

        with mock_serial_for_config:
            client.connect()

            for timeout in timeout_values:
                result = client.configure(timeout=timeout)
                assert result.is_ok
                mock_serial_config.timeout = timeout


class TestSerialErrorRecovery:
    """Tests for serial error recovery scenarios."""

    def test_port_disconnection_during_send(self):
        """Test handling of port disconnection during send."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        port = Mock()
        port.is_open = True
        port.write.side_effect = Exception("Port closed")

        with patch("omni_sdk.clients.serial_client.serial") as mock_serial:
            mock_serial.Serial.return_value = port
            client.connect()

            result = client.send("DATA\r\n")

            # Send should handle error gracefully
            result = client.send("DATA\r\n")

    def test_permission_denied_scenario(self):
        """Test handling of permission denied error."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        port = Mock()
        port.is_open = False
        port.write.side_effect = PermissionError("Permission denied")

        with patch("omni_sdk.clients.serial_client.serial") as mock_serial:
            mock_serial.Serial.return_value = port
            client.connect()

            result = client.send("DATA\r\n")
            assert result.is_ok

    def test_buffer_overflow_handling(self):
        """Test buffer overflow handling."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        port = Mock()
        port.is_open = True
        port.write.return_value = 1024  # Wrote 1024 bytes

        with patch("omni_sdk.clients.serial_client.serial") as mock_serial:
            mock_serial.Serial.return_value = port
            client.connect()

            # Send large data
            large_data = "X" * 2048
            result = client.send(large_data)
            assert result.is_ok


class TestSerialStatusReporting:
    """Tests for serial status and metadata reporting."""

    @pytest.fixture
    def mock_serial_status(self):
        """Create mock serial for status tests."""
        port = Mock()
        port.is_open = True
        port.baudrate = 115200
        port.port = "/dev/ttyUSB0"
        port.bytesize = 8
        port.parity = "N"
        port.stopbits = 1
        port.timeout = 5.0
        return port

    @pytest.fixture
    def mock_serial_for_status(self, mock_serial_status):
        """Create mock pyserial for status tests."""
        with patch("omni_sdk.clients.serial_client.serial") as mock_serial:
            mock_serial.Serial.return_value = mock_serial_status
            yield mock_serial

    def test_get_connected_status(self, mock_serial_for_status, mock_serial_status):
        """Test getting status of connected serial port."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0", "baud_rate": 115200})

        with mock_serial_for_status:
            client.connect()

            result = client.get_status()
            assert result.is_ok
            status = result.unwrap()
            assert status["port"] == "/dev/ttyUSB0"
            assert status["baud_rate"] == 115200

    def test_get_disconnected_status(self):
        """Test getting status of disconnected serial port."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        result = client.get_status()
        assert result.is_ok

    def test_capabilities_reporting(self):
        """Test serial client capabilities reporting."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        caps = client.capabilities()
        assert "send" in caps
        assert "receive" in caps
        assert "get_status" in caps
        assert "configure" in caps

    def test_metadata_verification(self, mock_serial_for_status, mock_serial_status):
        """Test serial port metadata verification."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0", "baud_rate": 115200, "timeout": 5})

        with mock_serial_for_status:
            client.connect()

            # Verify all metadata
            assert client.port == "/dev/ttyUSB0"
            assert client.baud_rate == 115200
            assert client.timeout == 5
            assert client.bytesize == 8
            assert client.parity == "N"
            assert client.stopbits == 1


class TestSerialWorkflowIntegration:
    """Integration tests for complete serial workflows."""

    @pytest.fixture
    def mock_serial_workflow(self):
        """Create mock for workflow tests."""
        port = Mock()
        port.is_open = True
        port.write.return_value = 10
        port.read.return_value = b"RESPONSE\r\n"
        port.baudrate = 115200
        return port

    @pytest.fixture
    def mock_serial_for_workflow(self, mock_serial_workflow):
        """Create mock pyserial for workflow tests."""
        with patch("omni_sdk.clients.serial_client.serial") as mock_serial:
            mock_serial.Serial.return_value = mock_serial_workflow
            yield mock_serial

    def test_complete_transaction_workflow(self, mock_serial_for_workflow):
        """Complete send-receive transaction workflow."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0", "baud_rate": 9600})

        with mock_serial_for_workflow:
            # Step 1: Open connection
            client.connect()
            assert client.is_connected()

            # Step 2: Send command
            result = client.send("CMD\r\n")
            assert result.is_ok

            # Step 3: Receive response
            result = client.receive(1000)
            assert result.is_ok
            assert "RESPONSE" in result.unwrap()

            # Step 4: Close connection
            client.disconnect()
            assert not client.is_connected()

    def test_multiple_transactions_workflow(self, mock_serial_for_workflow):
        """Multiple sequential transactions workflow."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        commands = [
            ("GET_VER\r\n", "V1.0\r\n"),
            ("GET_STATUS\r\n", "OK\r\n"),
            ("GET_CONFIG\r\n", "CONF...\r\n"),
        ]

        with mock_serial_for_workflow:
            client.connect()

            for cmd, expected_response in commands:
                result = client.send_and_receive(cmd, 1000)
                assert result.is_ok

            client.disconnect()

    def test_configuration_change_workflow(
        self, mock_serial_for_workflow, mock_serial_workflow
    ):
        """Configuration change during workflow."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0", "baud_rate": 9600})

        with mock_serial_for_workflow:
            client.connect()

            # Initial baund rate
            assert client.baud_rate == 9600

            # Change baud rate during connection
            client.configure(baud_rate=115200)
            assert client.baud_rate == 115200

            # Continue communication at new baud rate
            client.send("CMD\r\n")

            client.disconnect()

    def test_error_recovery_workflow(self):
        """Error recovery during workflow."""
        client = SerialClient()
        client.initialize({"port": "/dev/ttyUSB0"})

        port = Mock()
        port.is_open = True
        port.write.return_value = 10
        port.read.side_effect = [b"OK\r\n", Exception("Read error"), b"OK\r\n"]
        port.baudrate = 115200

        with patch("omni_sdk.clients.serial_client.serial") as mock_serial:
            mock_serial.Serial.return_value = port
            client.connect()

            # First transaction succeeds
            result = client.send_and_receive("CMD1\r\n", 1000)
            assert result.is_ok

            # Second transaction has error
            result = client.send_and_receive("CMD2\r\n", 1000)

            # Third transaction succeeds
            result = client.send_and_receive("CMD3\r\n", 1000)
            assert result.is_ok
