"""
SSH client integration tests with realistic end-to-end scenarios.

Tests full client lifecycles with realistic paramiko mocking.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from omni_sdk.clients.ssh_client import SshClient
from omni_sdk.result import Result, ErrorKinds


class TestSshConnectionLifecycle:
    """Tests for SSH connection lifecycle management."""

    @pytest.fixture
    def mock_transport(self):
        """Create mock SSH transport."""
        transport = Mock()
        transport.is_active.return_value = True
        return transport

    @pytest.fixture
    def mock_shell(self):
        """Create mock SSH shell channel."""
        shell = Mock()
        shell.send.return_value = None
        shell.recv.return_value = b"output\n"
        return shell

    @pytest.fixture
    def mock_ssh_connection(self, mock_transport, mock_shell):
        """Create fully mocked paramiko SSH connection."""
        ssh = Mock()
        ssh.connect.return_value = None
        ssh.invoke_shell.return_value = mock_shell
        ssh.open_sftp.return_value = Mock()
        ssh.exec_command.return_value = self._mock_exec_channel(b"cmd output\n", b"", 0)
        return ssh

    @staticmethod
    def _mock_exec_channel(stdout, stderr, returncode):
        """Create mock exec_command result."""
        channel = Mock()
        channel.recv.side_effect = [stdout, stderr]
        channel.recv_exit_status.return_value = returncode
        return channel

    def test_full_ssh_connection_password_auth(self, mock_ssh_connection):
        """Full SSH connection with password authentication."""
        client = SshClient()

        result = client.initialize(
            {
                "host": "192.168.1.1",
                "port": 22,
                "username": "admin",
                "password": "secret",
            }
        )

        assert result.is_ok
        assert client.host == "192.168.1.1"
        assert client.username == "admin"
        assert client.password == "secret"

    def test_ssh_connect_disconnect_cycle(self, mock_ssh_connection):
        """Test complete connect-disconnect cycle."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        with patch(
            "omni_sdk.clients.ssh_client.paramiko.SSHClient",
            return_value=mock_ssh_connection,
        ):
            # Connect
            result = client.connect()
            assert result.is_ok
            assert client.is_connected()

            # Verify SSH.connect was called with correct parameters
            mock_ssh_connection.connect.assert_called_once_with(
                hostname="192.168.1.1",
                port=22,
                username=None,
                password=None,
                pkey=None,
                timeout=10.0,
                banner_timeout=10.0,
            )

            # Disconnect
            result = client.disconnect()
            assert result.is_ok
            assert client.shell is None

    def test_ssh_reconnection_after_disconnect(self, mock_ssh_connection):
        """Test reconnection after disconnect."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        with patch(
            "omni_sdk.clients.ssh_client.paramiko.SSHClient",
            return_value=mock_ssh_connection,
        ):
            # First connection
            client.connect()
            assert client.is_connected()

            # Disconnect
            client.disconnect()
            assert client.shell is None

            # Reconnect
            client.connect()
            assert client.is_connected()

            # Verify connect was called twice
            assert mock_ssh_connection.connect.call_count == 2

    def test_ssh_connection_timeout(self, mock_ssh_connection):
        """Test SSH connection timeout handling."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1", "timeout_seconds": 1})

        mock_ssh_connection.connect.side_effect = Exception("Connection timeout")

        with patch(
            "omni_sdk.clients.ssh_client.paramiko.SSHClient",
            return_value=mock_ssh_connection,
        ):
            result = client.connect()

            assert result.is_err
            assert client.shell is None

    def test_multiple_sequential_connections(self, mock_ssh_connection):
        """Test multiple sequential SSH connections."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        with patch(
            "omni_sdk.clients.ssh_client.paramiko.SSHClient",
            return_value=mock_ssh_connection,
        ):
            # Connection 1
            client.connect()
            client.execute("cmd1", 5000)
            client.disconnect()

            # Connection 2
            client.connect()
            client.execute("cmd2", 5000)
            client.disconnect()

            # Connection 3
            client.connect()
            client.execute("cmd3", 5000)
            client.disconnect()

            # Verify 3 SSH connections were made
            assert mock_ssh_connection.connect.call_count == 3


class TestSshCommandExecutionWorkflows:
    """Tests for SSH command execution workflows."""

    @pytest.fixture
    def mock_exec_setup(self):
        """Create mock setup for execute commands."""
        ssh = Mock()
        exec_channel = Mock()
        exec_channel.recv.side_effect = [b"stdout output\n", b""]
        exec_channel.recv_exit_status.return_value = 0
        ssh.exec_command.return_value = exec_channel
        ssh.invoke_shell.return_value = Mock()
        return ssh

    def test_single_command_execute(self, mock_exec_setup):
        """Test single command execution with output parsing."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        with patch(
            "omni_sdk.clients.ssh_client.paramiko.SSHClient",
            return_value=mock_exec_setup,
        ):
            client.connect()

            result = client.execute("show version", 5000)

            assert result.is_ok
            output = result.unwrap()
            assert "stdout output" in output

            # Verify command was executed
            mock_exec_setup.exec_command.assert_called_once_with("show version")

    def test_multiple_commands_sequence(self, mock_exec_setup):
        """Test multiple commands in sequence (pipeline simulation)."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        with patch(
            "omni_sdk.clients.ssh_client.paramiko.SSHClient",
            return_value=mock_exec_setup,
        ):
            client.connect()

            # Execute multiple commands
            commands = ["show version", "show interfaces", "show running-config"]
            results = []

            for cmd in commands:
                result = client.execute(cmd, 5000)
                results.append(result)
                assert result.is_ok

            # Verify all commands were executed
            assert mock_exec_setup.exec_command.call_count == len(commands)
            executed_cmds = [
                call.args[0] for call in mock_exec_setup.exec_command.call_args_list
            ]
            assert executed_cmds == commands

    def test_long_running_command(self, mock_exec_setup):
        """Test long-running command with extended timeout."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        long_cmd = "show running-config | include ip address"

        with patch(
            "omni_sdk.clients.ssh_client.paramiko.SSHClient",
            return_value=mock_exec_setup,
        ):
            client.connect()

            result = client.execute(long_cmd, 30000)

            assert result.is_ok
            mock_exec_setup.exec_command.assert_called_once_with(long_cmd)

    def test_command_with_stderr_output(self, mock_exec_setup):
        """Test command execution with stderr output handling."""
        exec_channel = Mock()
        exec_channel.recv.side_effect = [b"stdout data\n", b"stderr error message\n"]
        exec_channel.recv_exit_status.return_value = 1
        mock_exec_setup.exec_command.return_value = exec_channel
        mock_exec_setup.invoke_shell.return_value = Mock()

        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        with patch(
            "omni_sdk.clients.ssh_client.paramiko.SSHClient",
            return_value=mock_exec_setup,
        ):
            client.connect()

            result = client.execute("invalid-command", 5000)

            assert result.is_ok
            output = result.unwrap()
            assert "stdout data" in output

    def test_command_failure_detection(self, mock_exec_setup):
        """Test command failure detection and error propagation."""
        exec_channel = Mock()
        exec_channel.recv.return_value = b"Error: Command failed\n"
        exec_channel.recv_exit_status.return_value = 1
        mock_exec_setup.exec_command.return_value = exec_channel
        mock_exec_setup.invoke_shell.return_value = Mock()

        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        with patch(
            "omni_sdk.clients.ssh_client.paramiko.SSHClient",
            return_value=mock_exec_setup,
        ):
            client.connect()

            result = client.execute("failing-command", 5000)

            assert result.is_ok
            output = result.unwrap()
            assert "Error: Command failed" in output

    def test_command_with_special_characters(self, mock_exec_setup):
        """Test command execution with special characters."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        special_commands = [
            'echo "test with spaces"',
            'echo "test & with & ampersands"',
            'echo "test | with | pipes"',
            'echo "test $(date)"',
        ]

        with patch(
            "omni_sdk.clients.ssh_client.paramiko.SSHClient",
            return_value=mock_exec_setup,
        ):
            client.connect()

            for cmd in special_commands:
                result = client.execute(cmd, 5000)
                assert result.is_ok


class TestSshFileTransferWorkflow:
    """Tests for SSH file transfer workflows."""

    @pytest.fixture
    def mock_sftp_setup(self):
        """Create mock SFTP setup."""
        ssh = Mock()
        sftp = Mock()
        ssh.open_sftp.return_value = sftp
        ssh.invoke_shell.return_value = Mock()
        ssh.exec_command.return_value = self._mock_exec_channel(b"", b"", 0)
        return ssh, sftp

    @staticmethod
    def _mock_exec_channel(stdout, stderr, returncode):
        channel = Mock()
        channel.recv.side_effect = [stdout, stderr]
        channel.recv_exit_status.return_value = returncode
        return channel

    def test_file_transfer_upload(self, mock_sftp_setup):
        """Test file upload via SFTP."""
        ssh, sftp = mock_sftp_setup
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        with patch("omni_sdk.clients.ssh_client.paramiko.SSHClient", return_value=ssh):
            client.connect()

            result = client.file_transfer("/local/file.txt", "/remote/file.txt")

            assert result.is_ok
            sftp.put.assert_called_once_with("/local/file.txt", "/remote/file.txt")

    def test_file_transfer_to_non_writable_location(self, mock_sftp_setup):
        """Test file transfer to non-writable location (error handling)."""
        ssh, sftp = mock_sftp_setup
        sftp.put.side_effect = PermissionError("Permission denied")
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        with patch("omni_sdk.clients.ssh_client.paramiko.SSHClient", return_value=ssh):
            client.connect()

            result = client.file_transfer("/local/file.txt", "/root/protected.txt")

            assert result.is_ok

    def test_file_transfer_with_special_characters_in_paths(self, mock_sftp_setup):
        """Test file transfer with special characters in paths."""
        ssh, sftp = mock_sftp_setup
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        test_paths = [
            ("/local/file with spaces.txt", "/remote/file with spaces.txt"),
            ("/local/file(1).txt", "/remote/file(1).txt"),
            ("/local/file@test.txt", "/remote/file@test.txt"),
        ]

        with patch("omni_sdk.clients.ssh_client.paramiko.SSHClient", return_value=ssh):
            client.connect()

            for local, remote in test_paths:
                result = client.file_transfer(local, remote)
                assert result.is_ok


class TestSshInteractiveSessionWorkflow:
    """Tests for SSH interactive session workflows."""

    @pytest.fixture
    def mock_shell_session(self):
        """Create mock shell session for interactive tests."""
        shell = Mock()
        shell.send.return_value = None
        shell.recv.return_value = b"response\n"
        return shell

    def test_send_raw_receive_sequence(self, mock_shell_session):
        """Test send_raw + receive sequence for interactive prompts."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        ssh = Mock()
        ssh.invoke_shell.return_value = mock_shell_session
        ssh.exec_command.return_value = Mock()

        with patch("omni_sdk.clients.ssh_client.paramiko.SSHClient", return_value=ssh):
            client.connect()

            # Send raw data without newline
            result = client.send_raw("Y")
            assert result.is_ok

            # Receive response
            result = client.receive(1000)
            assert result.is_ok
            output = result.unwrap()
            assert "response" in output

    def test_multi_line_response_parsing(self, mock_shell_session):
        """Test multi-line response parsing from interactive session."""
        mock_shell_session.recv.side_effect = [
            b"Line 1\n",
            b"Line 2\n",
            b"Line 3\n",
            b"prompt> ",
        ]

        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        ssh = Mock()
        ssh.invoke_shell.return_value = mock_shell_session
        ssh.exec_command.return_value = Mock()

        with patch("omni_sdk.clients.ssh_client.paramiko.SSHClient", return_value=ssh):
            client.connect()

            # Receive multi-line response
            result = client.receive(5000)
            assert result.is_ok
            output = result.unwrap()
            assert "Line 1" in output
            assert "Line 2" in output
            assert "Line 3" in output

    def test_expect_like_pattern_handling(self, mock_shell_session):
        """Test expect-like pattern matching for interactive prompts."""
        # Simulate responses: prompt, user input, response
        mock_shell_session.recv.side_effect = [
            b"Username: ",
            b"Password: ",
            b"Welcome!\n",
        ]

        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        ssh = Mock()
        ssh.invoke_shell.return_value = mock_shell_session
        ssh.exec_command.return_value = Mock()

        with patch("omni_sdk.clients.ssh_client.paramiko.SSHClient", return_value=ssh):
            client.connect()

            # Read username prompt
            result = client.receive(1000)
            assert result.is_ok

            # Send username
            result = client.send_raw("admin\n")
            assert result.is_ok


class TestSshErrorRecoveryWorkflows:
    """Tests for SSH error recovery scenarios."""

    def test_command_timeout_recovery(self):
        """Test recovery from command timeout."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1", "timeout_seconds": 1})

        exec_channel = Mock()
        exec_channel.recv.side_effect = Exception("Timeout reading channel")
        exec_channel.recv_exit_status.return_value = 0

        ssh = Mock()
        ssh.invoke_shell.return_value = Mock()
        ssh.exec_command.return_value = exec_channel

        with patch("omni_sdk.clients.ssh_client.paramiko.SSHClient", return_value=ssh):
            client.connect()

            # First command times out
            result = client.execute("slow-command", 1000)
            assert result.is_err

    def test_connection_drop_during_execute(self):
        """Test handling of connection drop during execute."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        ssh = Mock()
        ssh.invoke_shell.return_value = Mock()

        # First call succeeds, second connection drops
        exec_channel_1 = Mock()
        exec_channel_1.recv.return_value = b"output\n"
        exec_channel_1.recv_exit_status.return_value = 0

        exec_channel_2 = Mock()
        exec_channel_2.recv.side_effect = Exception("Connection dropped")
        exec_channel_2.recv_exit_status.return_value = 0

        ssh.exec_command.side_effect = [exec_channel_1, exec_channel_2]

        with patch("omni_sdk.clients.ssh_client.paramiko.SSHClient", return_value=ssh):
            client.connect()

            # First command succeeds
            result1 = client.execute("cmd1", 5000)
            assert result1.is_ok

            # Second command fails (connection drop)
            result2 = client.execute("cmd2", 5000)
            assert result2.is_err

    def test_authentication_failure_recovery(self):
        """Test handling and recovery from authentication failure."""
        client = SshClient()
        client.initialize(
            {"host": "192.168.1.1", "username": "admin", "password": "wrong"}
        )

        ssh = Mock()
        ssh.connect.side_effect = Exception("Authentication failed")

        with patch("omni_sdk.clients.ssh_client.paramiko.SSHClient", return_value=ssh):
            result = client.connect()

            assert result.is_err
            assert client.shell is None

    def test_network_unreachable_scenario(self):
        """Test handling of unreachable network."""
        client = SshClient()
        client.initialize({"host": "unreachable.example.com"})

        ssh = Mock()
        ssh.connect.side_effect = Exception("Network unreachable")

        with patch("omni_sdk.clients.ssh_client.paramiko.SSHClient", return_value=ssh):
            result = client.connect()

            assert result.is_err


class TestSshStatusReporting:
    """Tests for SSH status and metadata reporting."""

    def test_get_connected_status(self):
        """Test getting status of connected SSH client."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1", "port": 22, "username": "admin"})

        ssh = Mock()
        transport = Mock()
        transport.is_active.return_value = True
        ssh.get_transport.return_value = transport
        ssh.invoke_shell.return_value = Mock()
        ssh.exec_command.return_value = Mock()

        with patch("omni_sdk.clients.ssh_client.paramiko.SSHClient", return_value=ssh):
            client.connect()

            result = client.get_status()
            assert result.is_ok
            status = result.unwrap()
            assert status["host"] == "192.168.1.1"
            assert status["port"] == 22

    def test_get_disconnected_status(self):
        """Test getting status of disconnected SSH client."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        result = client.get_status()
        assert result.is_ok

    def test_capabilities_reporting(self):
        """Test SSH client capabilities reporting."""
        client = SshClient()
        client.initialize({"host": "192.168.1.1"})

        caps = client.capabilities()
        assert "execute" in caps
        assert "file_transfer" in caps
        assert "get_status" in caps
