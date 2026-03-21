"""
SerialClient: Serial port communication client.

Provides serial port management and data transfer capabilities.
"""

from typing import Dict, Any
import serial as pyserial
from ..client import Client
from ..result import Result, ErrorKinds, create_error_result


class SerialClient(Client):
    """
    Serial port communication client.

    Supports:
    - Various baud rates (9600, 19200, 38400, 57600, 115200, 230400)
    - Configurable data bits, stop bits, parity
    - Timeout configuration
    - Send and receive data
    """

    def __init__(self):
        self.port_: pyserial.Serial = None
        self.config: Dict[str, Any] = {}
        self.connected_: bool = False

    @property
    def name(self) -> str:
        return "serial"

    @property
    def version(self) -> str:
        return "1.0.0"

    def initialize(self, config: Dict[str, Any]) -> Result[None]:
        """
        Initialize serial client with configuration.

        Required config fields:
            port: Serial port path (e.g., "/dev/ttyUSB0", "COM3")

        Optional config fields:
            baud_rate: Baud rate (default: 9600)
            data_bits: Data bits (default: 8)
            stop_bits: Stop bits (default: 1)
            parity: Parity setting - "none", "even", "odd", "mark", "space" (default: "none")
            timeout_ms: Read/write timeout in milliseconds (default: 5000)
        """
        required_fields = ["port"]
        for field in required_fields:
            if field not in config:
                return create_error_result(
                    kind=ErrorKinds.CONFIG_ERROR,
                    message=f"Missing required serial config field: {field}",
                    details={
                        "required_fields": required_fields,
                        "provided": list(config.keys()),
                    },
                )

        self.config = config.copy()

        # Validate baud rate
        baud_rate = int(self.config.get("baud_rate", 9600))
        valid_rates = [9600, 19200, 38400, 57600, 115200, 230400]
        if baud_rate not in valid_rates:
            return create_error_result(
                kind=ErrorKinds.CONFIG_ERROR,
                message=f"Invalid baud rate {baud_rate}. Valid rates: {valid_rates}",
                details={"baud_rate": baud_rate},
            )
        self.config["baud_rate"] = baud_rate

        # Validate parity
        parity = self.config.get("parity", "none").lower()
        parity_map = {
            "none": pyserial.PARITY_NONE,
            "even": pyserial.PARITY_EVEN,
            "odd": pyserial.PARITY_ODD,
            "mark": pyserial.PARITY_MARK,
            "space": pyserial.PARITY_SPACE,
        }
        if parity not in parity_map:
            return create_error_result(
                kind=ErrorKinds.CONFIG_ERROR,
                message=f"Invalid parity '{parity}'. Valid values: none, even, odd, mark, space",
                details={"parity": parity},
            )
        self.config["parity"] = parity_map[parity]

        # Set defaults
        self.config.setdefault("data_bits", 8)
        self.config.setdefault("stop_bits", 1)
        self.config.setdefault("timeout_ms", 5000)

        return Result.ok(None)

    def connect(self) -> Result[None]:
        """
        Establish serial connection.

        Returns:
            Result.ok(None) on success, Result.err on failure
        """
        if self.connected_:
            return Result.ok(None)

        try:
            port = self.config["port"]
            baud_rate = self.config["baud_rate"]
            data_bits = self.config["data_bits"]
            stop_bits = self.config["stop_bits"]
            parity = self.config["parity"]
            timeout = self.config["timeout_ms"] / 1000.0

            self.port_ = pyserial.Serial(
                port=port,
                baudrate=baud_rate,
                bytesize=data_bits,
                stopbits=stop_bits,
                parity=parity,
                timeout=timeout,
                write_timeout=timeout,
            )

            self.connected_ = True
            return Result.ok(None)

        except pyserial.SerialException as e:
            return create_error_result(
                kind=ErrorKinds.SERIAL_ERROR,
                message=f"Serial connection failed: {str(e)}",
                details={"port": self.config["port"], "baud_rate": baud_rate},
            )
        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.DEVICE_ERROR,
                message=f"Serial error: {str(e)}",
                details={"exception_type": type(e).__name__},
            )

    def disconnect(self) -> Result[None]:
        """
        Close serial connection.

        Safe to call multiple times.
        """
        if self.connected_ and self.port_:
            try:
                self.port_.close()
            except Exception:
                pass
            self.connected_ = False
        return Result.ok(None)

    def is_connected(self) -> bool:
        """
        Check if serial port is connected.
        """
        if not self.connected_ or not self.port_:
            return False

        try:
            return self.port_.is_open
        except Exception:
            return False

    def send(self, command: str) -> Result[None]:
        """
        Send data to serial port.

        Args:
            command: Data string to send

        Returns:
            Result.ok(None) on success, Result.err on failure
        """
        if not self.connected_ or not self.port_:
            return create_error_result(
                kind=ErrorKinds.DEVICE_NOT_CONNECTED,
                message="Serial client is not connected",
            )

        try:
            data = command.encode("utf-8")
            bytes_written = self.port_.write(data)
            return Result.ok(None)
        except pyserial.SerialException as e:
            return create_error_result(
                kind=ErrorKinds.SERIAL_ERROR,
                message=f"Serial send failed: {str(e)}",
                details={"command": command},
            )
        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.RUNTIME_ERROR, message=f"Send error: {str(e)}"
            )

    def receive(self, timeout_ms: int = 5000) -> Result[str]:
        """
        Receive data from serial port.

        Args:
            timeout_ms: Timeout in milliseconds

        Returns:
            Result.ok(data_string) on success, Result.err on failure
        """
        if not self.connected_ or not self.port_:
            return create_error_result(
                kind=ErrorKinds.DEVICE_NOT_CONNECTED,
                message="Serial client is not connected",
            )

        try:
            # Set temporary timeout
            old_timeout = self.port_.timeout
            self.port_.timeout = timeout_ms / 1000.0

            # Read all available data
            data = self.port_.read_all()
            self.port_.timeout = old_timeout

            if not data:
                return create_error_result(
                    kind=ErrorKinds.TIMEOUT_ERROR,
                    message="No data received (timeout)",
                    details={"timeout_ms": timeout_ms},
                )

            return Result.ok(data.decode("utf-8", errors="ignore"))

        except pyserial.SerialException as e:
            return create_error_result(
                kind=ErrorKinds.SERIAL_ERROR, message=f"Serial receive failed: {str(e)}"
            )
        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.RUNTIME_ERROR, message=f"Receive error: {str(e)}"
            )

    def send_and_receive(self, command: str, timeout_ms: int = 5000) -> Result[str]:
        """
        Send command and receive response.

        Args:
            command: Data string to send
            timeout_ms: Timeout in milliseconds

        Returns:
            Result.ok(response_string) on success, Result.err on failure
        """
        send_result = self.send(command)
        if not send_result.is_ok:
            return send_result  # Propagate error

        # Small delay to let device respond
        self.port_.write_timeout = 0.1

        return self.receive(timeout_ms)

    def capabilities(self) -> Dict[str, str]:
        """
        Return map of capability_name -> description.

        Available capabilities:
            send: Send data to serial port
            receive: Receive data from serial port
            get_status: Get serial port status
            configure: Reconfigure serial port parameters
        """
        return {
            "send": "Send data to serial port",
            "receive": "Receive data from serial port",
            "get_status": "Get serial port status",
            "configure": "Reconfigure serial port parameters",
        }

    def get_status(self) -> Result[Dict[str, Any]]:
        """
        Get serial port status.

        Returns:
            Result.ok(status_dict) with port information
        """
        if not self.connected_ or not self.port_:
            return Result.ok(
                {"connected": False, "client_name": self.name, "version": self.version}
            )

        return Result.ok(
            {
                "connected": self.connected_,
                "client_name": self.name,
                "version": self.version,
                "port": self.config.get("port"),
                "baud_rate": self.config.get("baud_rate"),
                "data_bits": self.config.get("data_bits"),
                "stop_bits": self.config.get("stop_bits"),
                "is_open": self.port_.is_open,
                "in_waiting": self.port_.in_waiting,
            }
        )

    def configure(self, **kwargs) -> Result[None]:
        """
        Reconfigure serial port parameters.

        Can be called while connected to change settings on-the-fly.

        Args:
            **kwargs: Configuration keys to update (baud_rate, data_bits, etc.)

        Returns:
            Result.ok(None) on success, Result.err on failure
        """
        if not self.connected_ or not self.port_:
            return create_error_result(
                kind=ErrorKinds.DEVICE_NOT_CONNECTED,
                message="Serial client is not connected",
            )

        try:
            if "baud_rate" in kwargs:
                self.port_.baudrate = kwargs["baud_rate"]
            if "data_bits" in kwargs:
                self.port_.bytesize = kwargs["data_bits"]
            if "stop_bits" in kwargs:
                self.port_.stopbits = kwargs["stop_bits"]
            if "timeout_ms" in kwargs:
                timeout = kwargs["timeout_ms"] / 1000.0
                self.port_.timeout = timeout
                self.port_.write_timeout = timeout

            return Result.ok(None)

        except Exception as e:
            return create_error_result(
                kind=ErrorKinds.SERIAL_ERROR,
                message=f"Reconfiguration failed: {str(e)}",
                details={"kwargs": kwargs},
            )

    def __del__(self):
        """Cleanup on destruction."""
        self.disconnect()
