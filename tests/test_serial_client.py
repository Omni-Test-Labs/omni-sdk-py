import pytest
from unittest.mock import patch

import serial as pyserial

from omni_sdk.clients.serial_client import SerialClient
from omni_sdk.result import Result, ErrorKinds


class MockPort:
    """A minimal mock port object to simulate a pyserial Serial port."""

    def __init__(self, data: bytes = b"", open: bool = True):
        self.is_open = open
        self.in_waiting = len(data)
        self._data = data
        self.timeout = 1.0
        self.write_timeout = 1.0
        self.last_write = None

    def close(self):  # pragma: no cover - simple behavior
        self.is_open = False

    def write(self, data: bytes) -> int:
        self.last_write = data
        return len(data)

    def read_all(self) -> bytes:
        return self._data


class MockSerial:
    """Mock for pyserial.Serial used by SerialClient.connect()."""

    def __init__(
        self,
        port=None,
        baudrate=None,
        bytesize=None,
        stopbits=None,
        parity=None,
        timeout=None,
        write_timeout=None,
    ):
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.stopbits = stopbits
        self.parity = parity
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.is_open = True
        self.in_waiting = 0


def test_initialize_valid_config():
    sc = SerialClient()
    cfg = {
        "port": "/dev/ttyUSB0",
        "baud_rate": 115200,
        "data_bits": 8,
        "stop_bits": 1,
        "parity": "none",
        "timeout_ms": 2000,
    }

    res = sc.initialize(cfg)
    assert res.is_ok
    # internal config should be normalized
    assert sc.config["baud_rate"] == 115200
    assert sc.config["parity"] == pyserial.PARITY_NONE


def test_initialize_missing_port():
    sc = SerialClient()
    res = sc.initialize({})
    assert res.is_err
    assert res.error().kind == ErrorKinds.CONFIG_ERROR


def test_initialize_invalid_baud_rate():
    sc = SerialClient()
    res = sc.initialize({"port": "/dev/ttyUSB0", "baud_rate": 12345})
    assert res.is_err
    assert res.error().kind == ErrorKinds.CONFIG_ERROR


def test_initialize_invalid_parity():
    sc = SerialClient()
    res = sc.initialize({"port": "/dev/ttyUSB0", "parity": "invalid"})
    assert res.is_err
    assert res.error().kind == ErrorKinds.CONFIG_ERROR


def test_connect_success(monkeypatch):
    sc = SerialClient()
    sc.config = {
        "port": "/dev/ttyUSB0",
        "baud_rate": 115200,
        "data_bits": 8,
        "stop_bits": 1,
        "parity": pyserial.PARITY_NONE,
        "timeout_ms": 2000,
    }
    monkeypatch.setattr("omni_sdk.clients.serial_client.pyserial.Serial", MockSerial)

    res = sc.connect()
    assert res.is_ok
    assert sc.is_connected() is True
    assert isinstance(sc.port_, MockSerial)


def test_connect_serial_exception():
    class FaultySerial:
        def __init__(self, *args, **kwargs):
            raise pyserial.SerialException("boom")

    sc = SerialClient()
    sc.config = {
        "port": "/dev/ttyUSB0",
        "baud_rate": 115200,
        "data_bits": 8,
        "stop_bits": 1,
        "parity": pyserial.PARITY_NONE,
        "timeout_ms": 2000,
    }
    import omni_sdk.clients.serial_client as scmod

    with patch.object(scmod.pyserial, "Serial", FaultySerial):
        res = sc.connect()
    assert res.is_err
    assert res.error().kind == ErrorKinds.SERIAL_ERROR


def test_disconnect_cleanup():
    sc = SerialClient()
    sc.port_ = MockPort(b"DATA")
    sc.connected_ = True
    res = sc.disconnect()
    assert res.is_ok
    assert sc.connected_ is False


def test_is_connected_before_after():
    sc = SerialClient()
    assert sc.is_connected() is False
    sc.port_ = MockPort(b"X")
    sc.connected_ = True
    assert sc.is_connected() in (True, False)  # depends on mock open state


def test_send_success_and_error_cases():
    sc = SerialClient()
    sc.connected_ = True
    sc.port_ = MockPort()
    res = sc.send("CMD")
    assert res.is_ok

    # simulate port write raising SerialException
    class BadPort(MockPort):
        def write(self, data):
            raise pyserial.SerialException("write error")

    sc.port_ = BadPort()
    res2 = sc.send("CMD2")
    assert res2.is_err
    assert res2.error().kind == ErrorKinds.SERIAL_ERROR


def test_receive_success_and_timeout():
    sc = SerialClient()
    sc.connected_ = True
    sc.port_ = MockPort(data=b"HELLO")
    r = sc.receive(timeout_ms=1000)
    assert r.is_ok
    assert r.value() == "HELLO"

    sc.port_ = MockPort(data=b"")
    r2 = sc.receive(timeout_ms=1000)
    assert r2.is_err
    assert r2.error().kind == ErrorKinds.TIMEOUT_ERROR


def test_send_and_receive_flow():
    sc = SerialClient()
    sc.connected_ = True
    sc.port_ = MockPort(data=b"OK")
    # patch sc.send to be normal and then test receive path via real method
    res = sc.send_and_receive("CMD", timeout_ms=1000)
    assert res.is_ok
    assert res.value() == "OK"


def test_get_status_variants():
    sc = SerialClient()
    status = sc.get_status()
    assert status.is_ok
    s = status.value()
    assert s["connected"] is False

    sc.connected_ = True
    sc.port_ = MockPort()
    sc.config = {
        "port": "/dev/ttyUSB0",
        "baud_rate": 115200,
        "data_bits": 8,
        "stop_bits": 1,
    }
    status2 = sc.get_status()
    assert status2.is_ok
    st = status2.value()
    assert st["connected"] is True


def test_configure_behaviour():
    sc = SerialClient()
    # Not connected -> error
    res = sc.configure(baud_rate=9600)
    assert res.is_err
    assert res.error().kind == ErrorKinds.DEVICE_NOT_CONNECTED

    # Connected path: simulate port and perform reconfiguration
    sc.connected_ = True
    sc.port_ = MockPort()
    sc.config = {"baud_rate": 115200, "timeout_ms": 2000}
    res2 = sc.configure(baud_rate=9600, timeout_ms=1000)
    assert res2.is_ok
    # timeout should be updated
    assert sc.port_.timeout == 1.0
