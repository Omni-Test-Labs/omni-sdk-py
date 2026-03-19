"""
SshClient: SSH protocol client implementation.

Provides SSH connection management and command execution capabilities.
"""

from typing import Dict, Any
import paramiko
from .client import Client
from .result import Result, ErrorKinds, create_error_result


class SshClient(Client):
    """
    SSH protocol client.

    Supports:
    - Password authentication
    - Key file authentication (RSA, DSA, ECDSA, ED25519)
    - Shell command execution
    - SCP file transfer
    """

    def __init__(self):
        self.client_: paramiko.SSHClient = paramiko.SSHClient()
        self.client_.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        self.config: Dict[str, Any] = {}
        self.connected_: bool = False
        self.shell_ = None

    @property
    def name(self) -> str:
        return "ssh"

    @property
    def version(self) -> str:
        return "1.0.0"

    def initialize(self, config: Dict[str, Any]) -> Result[None]:
        """
        Initialize SSH client with configuration.

        Required config fields:
            host: SSH server hostname or IP
            port: SSH port (default: 22)
            username: SSH username

        Optional config fields:
            password: SSH password
            password_file: Path to file containing password
            key_file: Path to private key file
            timeout_ms: Connection timeout in milliseconds (default: 5000)
        """
        required_fields = ["host", "port", "username"]
        for field in required_fields:
            if field not in config:
                return create_error_result(
                    kind=ErrorKinds.CONFIG_ERROR,
                    message=f"Missing required SSH config field: {field}",
                    details={
                        "required_fields": required_fields,
                        "provided": list(config.keys()),
                    },
                )

        self.config = config.copy()

        # Load password from file if specified
        if "password_file" in config:
            try:
                with open(config["password_file"], "r") as f:
                    self.config["password"] = f.read().strip()
            except Exception as e:
                return create_error_result(
                    kind=ErrorKinds.CONFIG_ERROR,
                    message=f"Failed to read password file: {str(e)}",
                    details={"password_file": config["password_file"]},
                )

        # Validate authentication credentials
        if "password" not in self.config and "key_file" not in self.config:
            return create_error_result(
                kind=ErrorKinds.AUTHENTICATION_ERROR,
                message="SSH authentication requires either password or key_file",
                details={"config_keys": list(config.keys())},
            )

        return Result.ok(None)

    def connect(self) -> Result[None]:
        """
        Establish SSH connection.

        Returns:
            Result.ok(None) on success, Result.err on failure
        """
        if self.connected_:
            return Result.ok(None)

        try:
            host = self.config["host"]
            port = int(self.config["port"])
            username = self.config["username"]
            password = self.config.get("password")
            key_file = self.config.get("key_file")
            timeout_ms = self.config.get("timeout_ms", 5000)
            timeout = timeout_ms / 1000.0

            if key_file:
                private_key = paramiko.RSAKey.from_private_key_file(key_file)
                self.client_.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    pkey=private_key,
                    timeout=timeout,
                    allow_agent=False,
                    look_for_keys=False,
                )
            else:
                self.client_.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password,
                    timeout=timeout,
                )

            # Create shell for interactive commands
            self.shell_ = self.client_.invoke_shell()
            self.shell_.settimeout(timeout)

            self.connected_ = True
            return Result.ok(None)

        except paramiko.AuthenticationException as e:
            return create_error_result(
                kind=ErrorKinds.AUTHENTICATION_ERROR,
                message=f"SSH authentication failed: {str(e)}",
                details={"host": host, "username": username},
            )
        except paramiko.SSHException as e:
            return create_error_result(
                kind=ErrorKinds.SSH_ERROR,
                message=f"SSH connection failed: {str(e)}",
                details={"host": host, "port": port},
            )
        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.CONNECTION_ERROR,
                message=f"Connection error: {str(e)}",
                details={"exception_type": type(e).__name__},
            )

    def disconnect(self) -> Result[None]:
        """
        Close SSH connection.

        Safe to call multiple times.
        """
        if self.connected_:
            try:
                if self.shell_:
                    self.shell_.close()
                self.client_.close()
            except Exception:
                pass  # Ignore errors during disconnect
            self.connected_ = False
        return Result.ok(None)

    def is_connected(self) -> bool:
        """
        Check if SSH client is connected.
        """
        if not self.connected_:
            return False

        # Verify connection is still alive
        try:
            transport = self.client_.get_transport()
            return transport is not None and transport.is_active()
        except Exception:
            return False

    def send(self, command: str) -> Result[None]:
        """
        Send command to SSH shell.

        Args:
            command: Command string to send

        Returns:
            Result.ok(None) on success, Result.err on failure
        """
        if not self.connected_:
            return create_error_result(
                kind=ErrorKinds.DEVICE_NOT_CONNECTED,
                message="SSH client is not connected",
            )

        if not self.shell_:
            return create_error_result(
                kind=ErrorKinds.DEVICE_ERROR, message="SSH shell not available"
            )

        try:
            self.shell_.send(command + "\n")
            return Result.ok(None)
        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.SSH_ERROR,
                message=f"Failed to send command: {str(e)}",
                details={"command": command},
            )

    def receive(self, timeout_ms: int = 5000) -> Result[str]:
        """
        Receive response from SSH shell.

        Args:
            timeout_ms: Timeout in milliseconds

        Returns:
            Result.ok(response_string) on success, Result.err on failure
        """
        if not self.connected_ or not self.shell_:
            return create_error_result(
                kind=ErrorKinds.DEVICE_NOT_CONNECTED,
                message="SSH client is not connected",
            )

        try:
            self.shell_.settimeout(timeout_ms / 1000.0)
            response = self.shell_.recv(65535).decode("utf-8", errors="ignore")
            return Result.ok(response)
        except paramiko.SSHException as e:
            if "timed out" in str(e):
                return create_error_result(
                    kind=ErrorKinds.TIMEOUT_ERROR,
                    message="Receive timeout",
                    details={"timeout_ms": timeout_ms},
                )
            return create_error_result(
                kind=ErrorKinds.SSH_ERROR, message=f"Receive failed: {str(e)}"
            )
        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.SSH_ERROR, message=f"Receive error: {str(e)}"
            )

    def send_and_receive(self, command: str, timeout_ms: int = 5000) -> Result[str]:
        """
        Convenience: send command and receive response.

        Uses exec_command for clean output (more suitable than shell).

        Args:
            command: Command string to execute
            timeout_ms: Timeout in milliseconds

        Returns:
            Result.ok(output) on success, Result.err on failure
        """
        return self.execute(command, timeout_ms)

    def capabilities(self) -> Dict[str, str]:
        """
        Return map of capability_name -> description.

        Available capabilities:
            execute: Execute shell command and return output
            file_transfer: Transfer files using SCP
            send_raw: Send raw text to shell
        """
        return {
            "execute": "Execute shell command and return output",
            "file_transfer": "Transfer files using SCP",
            "get_status": "Get SSH connection status",
        }

    def execute(self, command: str, timeout_ms: int = 5000) -> Result[str]:
        """
        Execute shell command and return output.

        This is the main capability for SSH client.
        Uses exec_command which provides clean output.

        Args:
            command: Shell command to execute
            timeout_ms: Command timeout in milliseconds

        Returns:
            Result.ok(output) on success, Result.err on failure

        Example:
            result = ssh_client.execute("show version")
            if result.is_ok:
                output = result.unwrap()
                print(output)
        """
        if not self.connected_:
            return create_error_result(
                kind=ErrorKinds.DEVICE_NOT_CONNECTED,
                message="SSH client is not connected",
            )

        try:
            timeout = timeout_ms / 1000.0
            stdin, stdout, stderr = self.client_.exec_command(command, timeout=timeout)

            # Read output
            output = stdout.read().decode("utf-8", errors="ignore")
            error = stderr.read().decode("utf-8", errors="ignore")

            exit_status = stdout.channel.recv_exit_status()

            if exit_status != 0:
                return create_error_result(
                    kind=ErrorKinds.SSH_ERROR,
                    message=f"Command failed with exit code {exit_status}",
                    details={
                        "command": command,
                        "exit_status": exit_status,
                        "stderr": error,
                    },
                )

            return Result.ok(output)

        except paramiko.SSHException as e:
            if "timed out" in str(e):
                return create_error_result(
                    kind=ErrorKinds.TIMEOUT_ERROR,
                    message="Command timeout",
                    details={"command": command, "timeout_ms": timeout_ms},
                )
            return create_error_result(
                kind=ErrorKinds.SSH_ERROR,
                message=f"Execute failed: {str(e)}",
                details={"command": command},
            )
        except Exception as e:
            return Result.from_exception(e, ErrorKinds.RUNTIME_ERROR)

    def send_raw(self, text: str) -> Result[None]:
        """
        Send raw text to SSH shell (without newline).

        Used for interactive sessions where you want to send keystrokes.

        Args:
            text: Raw text to send

        Returns:
            Result.ok(None) on success, Result.err on failure
        """
        if not self.connected_ or not self.shell_:
            return create_error_result(
                kind=ErrorKinds.DEVICE_NOT_CONNECTED,
                message="SSH client is not connected",
            )

        try:
            self.shell_.send(text)
            return Result.ok(None)
        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.SSH_ERROR, message=f"Failed to send raw: {str(e)}"
            )

    def file_transfer(self, local_path: str, remote_path: str) -> Result[None]:
        """
        Transfer file to remote host using SFTP.

        Args:
            local_path: Local file path
            remote_path: Remote file path

        Returns:
            Result.ok(None) on success, Result.err on failure
        """
        if not self.connected_:
            return create_error_result(
                kind=ErrorKinds.DEVICE_NOT_CONNECTED,
                message="SSH client is not connected",
            )

        try:
            sftp = self.client_.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            return Result.ok(None)
        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.SSH_ERROR,
                message=f"File transfer failed: {str(e)}",
                details={"local_path": local_path, "remote_path": remote_path},
            )

    def get_status(self) -> Result[Dict[str, Any]]:
        """
        Get SSH connection status.

        Returns:
            Result.ok(status_dict) with connection information
        """
        return Result.ok(
            {
                "connected": self.connected_,
                "client_name": self.name,
                "version": self.version,
                "host": self.config.get("host"),
                "port": self.config.get("port"),
                "username": self.config.get("username"),
            }
        )

    def __del__(self):
        """Cleanup on destruction."""
        self.disconnect()
