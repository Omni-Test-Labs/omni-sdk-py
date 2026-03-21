# Unit tests for the SSH client in omni_sdk.
# This test suite mocks out the paramiko library to exercise all code paths
# in SshClient without making real SSH connections.

import builtins
import types
import pytest
import paramiko
from unittest.mock import Mock, patch

from omni_sdk.clients.ssh_client import SshClient
from omni_sdk.result import Result, ErrorKinds


def _make_common_mocks():
    """Return a minimal mocked SSH client and shell/transport objects."""
    ssh_mock = Mock()
    # SshClient.__init__ calls set_missing_host_key_policy
    ssh_mock.set_missing_host_key_policy = Mock()
    # invoke_shell is called after connect
    shell_mock = Mock()
    shell_mock.settimeout = Mock()
    shell_mock.close = Mock()
    shell_mock.send = Mock()
    shell_mock.recv = Mock()
    ssh_mock.invoke_shell = Mock(return_value=shell_mock)
    # Transport to check is_active
    transport_mock = Mock()
    transport_mock.is_active = Mock(return_value=True)
    ssh_mock.get_transport = Mock(return_value=transport_mock)
    # SFTP mock used by file_transfer
    sftp_mock = Mock()
    sftp_mock.put = Mock()
    sftp_mock.close = Mock()
    ssh_mock.open_sftp = Mock(return_value=sftp_mock)
    return ssh_mock, shell_mock, transport_mock, sftp_mock


def test_initialize_missing_required_fields():
    with patch("paramiko.SSHClient") as MockSSHClient, patch("paramiko.AutoAddPolicy"):
        MockSSHClient.return_value = Mock()
        sc = SshClient()
    res = sc.initialize({"host": "example.com", "port": 22})
    assert not res.is_ok
    err = res.error()
    assert err is not None
    assert err.kind == ErrorKinds.CONFIG_ERROR


def test_initialize_requires_authentication(monkeypatch):
    with patch("paramiko.SSHClient") as MockSSHClient, patch("paramiko.AutoAddPolicy"):
        MockSSHClient.return_value = Mock()
        sc = SshClient()
    res = sc.initialize({"host": "host", "port": 22, "username": "u"})
    assert not res.is_ok
    err = res.error()
    assert err is not None
    assert err.kind == ErrorKinds.AUTHENTICATION_ERROR


def test_connect_success_password_and_is_connected():
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        ssh_mock.connect = Mock()
        # Simulate successful connection
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock

            sc = SshClient()
            cfg = {
                "host": "host",
                "port": 22,
                "username": "user",
                "password": "pwd",
                "timeout_ms": 1000,
            }
            res_init = sc.initialize(cfg)
            assert res_init.is_ok
            res = sc.connect()
            assert res.is_ok
            # Ensure correct call params
            # hostname, port, username, password, timeout
            args = ssh_mock.connect.call_args[1]
            assert args["hostname"] == "host"
            assert args["port"] == 22
            assert args["username"] == "user"
            assert args["password"] == "pwd"
            assert abs(args["timeout"] - 1.0) < 1e-6
            # Shell was created
            assert sc.shell_ is shell_mock
            # is_connected reports True when transport is active
            assert sc.is_connected() is True


def test_connect_authentication_error():
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock = Mock()
        ssh_mock.set_missing_host_key_policy = Mock()
        # connect raises AuthenticationException
        ssh_mock.connect = Mock(side_effect=paramiko.AuthenticationException("auth"))
        ssh_mock.invoke_shell = Mock(return_value=Mock())
        ssh_mock.get_transport = Mock(
            return_value=Mock(is_active=Mock(return_value=True))
        )
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            res_init = sc.initialize(
                {"host": "h", "port": 22, "username": "u", "password": "p"}
            )
            assert res_init.is_ok
            res = sc.connect()
            assert not res.is_ok
            err = res.error()
            assert err is not None
            assert err.kind == ErrorKinds.AUTHENTICATION_ERROR


def test_connect_ssh_exception():
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock = Mock()
        ssh_mock.set_missing_host_key_policy = Mock()
        ssh_mock.connect = Mock(side_effect=paramiko.SSHException("boom"))
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            res_init = sc.initialize(
                {"host": "h", "port": 22, "username": "u", "password": "p"}
            )
            assert res_init.is_ok
            res = sc.connect()
            assert not res.is_ok
            err = res.error()
            assert err is not None
            assert err.kind == ErrorKinds.SSH_ERROR


def test_disconnect_cleans_up():
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            # Pretend connected
            sc.connected_ = True
            sc.shell_ = shell_mock
            res = sc.disconnect()
            assert res.is_ok
            assert sc.connected_ is False
            shell_mock.close.assert_called()
            ssh_mock.close.assert_called()


def test_send_and_receive_behaviors():
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        # Setup for a successful execute path later
        stdin = Mock()
        stdout = Mock()
        stderr = Mock()
        stdout.read = Mock(return_value=b"OK")
        stderr.read = Mock(return_value=b"")
        stdout.channel = Mock()
        stdout.channel.recv_exit_status = Mock(return_value=0)
        ssh_mock.exec_command = Mock(return_value=(stdin, stdout, stderr))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            # Emulate a connected state and a shell
            sc.connected_ = True
            sc.shell_ = shell_mock
            # send
            res_send = sc.send("ls -l")
            assert res_send.is_ok
            shell_mock.send.assert_called_with("ls -l\n")
            # receive via execute path
            res_exec = sc.execute("echo hi", timeout_ms=1000)
            assert res_exec.is_ok
            assert res_exec.unwrap() == b"OK".decode("utf-8")


def test_file_transfer_success_and_failure():
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, _, _, _ = _make_common_mocks()
        # success
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            res = sc.file_transfer("local.txt", "/remote/remote.txt")
            assert res.is_ok
            ssh_mock.open_sftp.return_value.put.assert_called_with(
                "local.txt", "/remote/remote.txt"
            )
        # failure
        ssh_mock.open_sftp.return_value.put.side_effect = Exception("boom")
        res2 = sc.file_transfer("local.txt", "/remote/remote.txt")
        assert not res2.is_ok
        err2 = res2.error()
        assert err2 is not None
        assert err2.kind == ErrorKinds.SSH_ERROR


def test_get_status_and_capabilities():
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, _, _, _ = _make_common_mocks()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize(
                {"host": "host", "port": 22, "username": "user", "password": "pwd"}
            )
            st = sc.get_status()
            assert st.is_ok
            assert st.unwrap()["host"] == "host"
            caps = sc.capabilities()
            assert "execute" in caps and "file_transfer" in caps


def test_receive_timeout_error():
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True
            sc.shell_ = shell_mock
            # make recv raise a timeout-like error
            sc.shell_.recv = Mock(side_effect=paramiko.SSHException("timed out"))
            res = sc.receive(1000)
            assert res.is_ok is False
            err = res.error()
            assert err is not None
            assert err.kind == ErrorKinds.TIMEOUT_ERROR


# ============================================================
# Execute() Method Tests
# ============================================================


def test_execute_simple_command_success():
    """Test execute() with simple command that succeeds."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        stdin = Mock()
        stdout = Mock()
        stderr = Mock()
        stdout.read = Mock(return_value=b"command output")
        stderr.read = Mock(return_value=b"")
        stdout.channel = Mock()
        stdout.channel.recv_exit_status = Mock(return_value=0)
        ssh_mock.exec_command = Mock(return_value=(stdin, stdout, stderr))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True

            res = sc.execute("ls -l")
            assert res.is_ok
            assert res.unwrap() == "command output"
            ssh_mock.exec_command.assert_called()
            # Verify timeout parameter
            call_args = ssh_mock.exec_command.call_args
            assert call_args[0][0] == "ls -l"
            assert call_args[1]["timeout"] == 5.0  # default 5000ms


def test_execute_command_with_multiline_output():
    """Test execute() with command producing multiple lines of output."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        stdin = Mock()
        stdout = Mock()
        stderr = Mock()
        stdout.read = Mock(return_value=b"line1\nline2\nline3\n")
        stderr.read = Mock(return_value=b"")
        stdout.channel = Mock()
        stdout.channel.recv_exit_status = Mock(return_value=0)
        ssh_mock.exec_command = Mock(return_value=(stdin, stdout, stderr))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True

            res = sc.execute("cat file.txt")
            assert res.is_ok
            output = res.unwrap()
            assert "line1" in output
            assert "line2" in output
            assert "line3" in output


def test_execute_command_with_stderr():
    """Test execute() with command that produces stderr output (but succeeds)."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        stdin = Mock()
        stdout = Mock()
        stderr = Mock()
        stdout.read = Mock(return_value=b"normal output")
        stderr.read = Mock(return_value=b"warning message")
        stdout.channel = Mock()
        stdout.channel.recv_exit_status = Mock(return_value=0)
        ssh_mock.exec_command = Mock(return_value=(stdin, stdout, stderr))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True

            res = sc.execute("some command")
            assert res.is_ok
            assert res.unwrap() == "normal output"
            # stderr is captured but ignored on success


def test_execute_command_failure_nonzero_exit():
    """Test execute() with command that fails (non-zero exit code)."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        stdin = Mock()
        stdout = Mock()
        stderr = Mock()
        stdout.read = Mock(return_value=b"")
        stderr.read = Mock(return_value=b"command failed")
        stdout.channel = Mock()
        stdout.channel.recv_exit_status = Mock(return_value=1)
        ssh_mock.exec_command = Mock(return_value=(stdin, stdout, stderr))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True

            res = sc.execute("false")
            assert not res.is_ok
            err = res.error()
            assert err is not None
            assert err.kind == ErrorKinds.SSH_ERROR
            assert "exit status 1" in err.message


def test_execute_command_failure_with_stderr():
    """Test execute() with failing command that has stderr output."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        stdin = Mock()
        stdout = Mock()
        stderr = Mock()
        stdout.read = Mock(return_value=b"")
        stderr.read = Mock(return_value=b"Error: file not found")
        stdout.channel = Mock()
        stdout.channel.recv_exit_status = Mock(return_value=2)
        ssh_mock.exec_command = Mock(return_value=(stdin, stdout, stderr))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True

            res = sc.execute("cat nonexistent.txt")
            assert not res.is_ok
            err = res.error()
            assert err is not None
            assert err.kind == ErrorKinds.SSH_ERROR
            # Verify stderr is in error details
            details = err.details
            assert details is not None
            assert "stderr" in details
            assert "Error: file not found" in details["stderr"]


def test_execute_command_timeout():
    """Test execute() with command that times out."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        ssh_mock.connect = Mock()
        # exec_command raises SSHException with "timed out"
        ssh_mock.exec_command = Mock(side_effect=paramiko.SSHException("timed out"))
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True

            res = sc.execute("sleep 60", timeout_ms=1000)
            assert not res.is_ok
            err = res.error()
            assert err is not None
            assert err.kind == ErrorKinds.TIMEOUT_ERROR
            assert "Command timeout" in err.message


def test_execute_not_connected():
    """Test execute() when client is not connected."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            # Don't connect - connected_ remains False

            res = sc.execute("ls")
            assert not res.is_ok
            err = res.error()
            assert err is not None
            assert err.kind == ErrorKinds.DEVICE_NOT_CONNECTED


def test_execute_custom_timeout():
    """Test execute() with custom timeout value."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        stdin = Mock()
        stdout = Mock()
        stderr = Mock()
        stdout.read = Mock(return_value=b"output")
        stderr.read = Mock(return_value=b"")
        stdout.channel = Mock()
        stdout.channel.recv_exit_status = Mock(return_value=0)
        ssh_mock.exec_command = Mock(return_value=(stdin, stdout, stderr))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True

            res = sc.execute("ls", timeout_ms=10000)
            assert res.is_ok
            # Verify timeout was passed correctly
            call_args = ssh_mock.exec_command.call_args
            assert call_args[1]["timeout"] == 10.0  # 10000ms = 10s


def test_execute_empty_command():
    """Test execute() with empty command string."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        stdin = Mock()
        stdout = Mock()
        stderr = Mock()
        stdout.read = Mock(return_value=b"")
        stderr.read = Mock(return_value=b"")
        stdout.channel = Mock()
        stdout.channel.recv_exit_status = Mock(return_value=0)
        ssh_mock.exec_command = Mock(return_value=(stdin, stdout, stderr))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True

            # Empty command should be handled (shell behavior depends on implementation)
            res = sc.execute("")
            assert res.is_ok  # Empty command executes successfully


def test_execute_command_with_unicode_output():
    """Test execute() with command producing UTF-8 encoded output."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        stdin = Mock()
        stdout = Mock()
        stderr = Mock()
        # UTF-8 encoded string: "café"
        stdout.read = Mock(return_value=b"caf\xc3\xa9\n")
        stderr.read = Mock(return_value=b"")
        stdout.channel = Mock()
        stdout.channel.recv_exit_status = Mock(return_value=0)
        ssh_mock.exec_command = Mock(return_value=(stdin, stdout, stderr))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True

            res = sc.execute("unicode command")
            assert res.is_ok
            output = res.unwrap()
            assert "caf" in output


# ============================================================
# send_raw() Method Tests
# ============================================================


def test_send_raw_simple_text():
    """Test send_raw() with simple text."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True
            sc.shell_ = shell_mock

            res = sc.send_raw("test command")
            assert res.is_ok
            # Verify shell.send() was called WITHOUT newline
            shell_mock.send.assert_called_once_with("test command")


def test_send_raw_multiline_text():
    """Test send_raw() with multi-line text."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True
            sc.shell_ = shell_mock

            text = "line1\nline2\nline3"
            res = sc.send_raw(text)
            assert res.is_ok
            shell_mock.send.assert_called_once_with(text)


def test_send_raw_special_characters():
    """Test send_raw() with special characters (tabs, newlines, etc)."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True
            sc.shell_ = shell_mock

            text = "cmd\targ1\targ2\n"
            res = sc.send_raw(text)
            assert res.is_ok
            shell_mock.send.assert_called_once_with(text)


def test_send_raw_empty_string():
    """Test send_raw() with empty string."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True
            sc.shell_ = shell_mock

            res = sc.send_raw("")
            assert res.is_ok
            shell_mock.send.assert_called_once_with("")


def test_send_raw_not_connected():
    """Test send_raw() when client is not connected."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            # Don't connect - connected_ remains False

            res = sc.send_raw("command")
            assert not res.is_ok
            err = res.error()
            assert err is not None
            assert err.kind == ErrorKinds.DEVICE_NOT_CONNECTED


def test_send_raw_no_shell():
    """Test send_raw() when shell is None (connected but no shell)."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True
            sc.shell_ = None  # Shell not available

            res = sc.send_raw("command")
            assert not res.is_ok
            err = res.error()
            assert err is not None
            assert err.kind == ErrorKinds.DEVICE_NOT_CONNECTED


def test_send_raw_shell_exception():
    """Test send_raw() when shell.send() raises an exception."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        shell_mock.send = Mock(side_effect=Exception("shell send failed"))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True
            sc.shell_ = shell_mock

            res = sc.send_raw("command")
            assert not res.is_ok
            err = res.error()
            assert err is not None
            assert err.kind == ErrorKinds.SSH_ERROR


# ============================================================
# Connection Boundary Tests
# ============================================================


def test_execute_after_disconnect():
    """Test execute() after disconnecting."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        stdin = Mock()
        stdout = Mock()
        stderr = Mock()
        stdout.read = Mock(return_value=b"output")
        stderr.read = Mock(return_value=b"")
        stdout.channel = Mock()
        stdout.channel.recv_exit_status = Mock(return_value=0)
        ssh_mock.exec_command = Mock(return_value=(stdin, stdout, stderr))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True
            sc.shell_ = shell_mock

            # Execute once while connected
            res1 = sc.execute("ls")
            assert res1.is_ok

            # Disconnect
            sc.disconnect()

            # Try to execute after disconnect
            res2 = sc.execute("ls")
            assert not res2.is_ok
            err = res2.error()
            assert err.kind == ErrorKinds.DEVICE_NOT_CONNECTED


def test_send_raw_after_disconnect():
    """Test send_raw() after disconnecting."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True
            sc.shell_ = shell_mock

            # Send once while connected
            res1 = sc.send_raw("cmd")
            assert res1.is_ok

            # Disconnect
            sc.disconnect()

            # Try to send after disconnect
            res2 = sc.send_raw("cmd")
            assert not res2.is_ok
            err = res2.error()
            assert err.kind == ErrorKinds.DEVICE_NOT_CONNECTED


def test_multiple_execute_same_connection():
    """Test multiple execute() calls on the same connection."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        stdin = Mock()
        stdout = Mock()
        stderr = Mock()
        stdout.read = Mock(return_value=b"output")
        stderr.read = Mock(return_value=b"")
        stdout.channel = Mock()
        stdout.channel.recv_exit_status = Mock(return_value=0)
        ssh_mock.exec_command = Mock(return_value=(stdin, stdout, stderr))
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True

            # Execute multiple commands
            for i in range(5):
                res = sc.execute(f"cmd{i}")
                assert res.is_ok

            # Verify exec_command was called 5 times
            assert ssh_mock.exec_command.call_count == 5


def test_multiple_send_raw_same_connection():
    """Test multiple send_raw() calls on the same connection."""
    with patch("paramiko.AutoAddPolicy"):
        ssh_mock, shell_mock, transport_mock, _ = _make_common_mocks()
        ssh_mock.connect = Mock()
        with patch("paramiko.SSHClient") as MockSSHClient:
            MockSSHClient.return_value = ssh_mock
            sc = SshClient()
            sc.initialize({"host": "h", "port": 22, "username": "u", "password": "p"})
            sc.connected_ = True
            sc.shell_ = shell_mock

            # Send multiple times
            for i in range(5):
                res = sc.send_raw(f"cmd{i}")
                assert res.is_ok

            # Verify shell.send() was called 5 times
            assert shell_mock.send.call_count == 5
