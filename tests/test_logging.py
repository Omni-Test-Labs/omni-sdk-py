"""Unit tests for logging utilities in omni_sdk.utils.logging."""

import io
import logging
import sys

import pytest

from omni_sdk.utils import logging as logmod
from omni_sdk.result import Result, Error


class TestLoggerSetupAndFormatter:
    def test_setup_logger_has_stream_handler(self):
        logger = logging.getLogger("omni_sdk")
        # Ensure there is at least one StreamHandler attached to stdout
        has_stream = any(
            isinstance(h, logging.StreamHandler)
            and h.stream in (sys.stdout, getattr(sys, "stdout", None))
            for h in logger.handlers
        )
        assert has_stream, "omni_sdk logger should have a StreamHandler to stdout"

    def test_formatter_format_string(self):
        logger = logging.getLogger("omni_sdk")
        # Find the first StreamHandler and inspect its formatter
        stream_handler = next(
            (h for h in logger.handlers if isinstance(h, logging.StreamHandler)), None
        )
        assert stream_handler is not None, "Expected a StreamHandler on omni_sdk logger"
        fmt = getattr(stream_handler.formatter, "_fmt", None)
        assert fmt == "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class TestLoggingFunctionsBasic:
    def test_log_levels_and_messages_caplog(self, caplog):
        caplog.set_level(logging.DEBUG, logger="omni_sdk")
        logmod.log_debug("debug message")
        logmod.log_info("info message")
        logmod.log_warning("warning message")

        # We should at least have these messages captured at appropriate levels
        messages = [rec.getMessage() for rec in caplog.records]
        assert any("debug message" in m for m in messages)
        assert any("info message" in m for m in messages)
        assert any("warning message" in m for m in messages)

    def test_log_debug_not_emitted_when_disabled(self, caplog):
        caplog.set_level(logging.INFO, logger="omni_sdk")
        caplog.clear()
        logmod.log_debug("should not appear")
        assert all(
            "should not appear" not in rec.getMessage() for rec in caplog.records
        )

    def test_log_error_with_error_object(self, caplog):
        caplog.set_level(logging.ERROR, logger="omni_sdk")

        class DummyError:
            kind = "DummyKind"
            message = "dummy message"
            details = {"detail": "v"}

        err = DummyError()
        logmod.log_error("an error occurred", err_obj=err)
        # Expect a structured message containing error fields
        msg = caplog.records[-1].getMessage()
        assert "an error occurred" in msg
        assert "error_kind'" in msg or "error_kind" in msg
        assert "DummyKind" in msg
        assert "dummy message" in msg

    def test_log_result_ok_and_err(self, caplog):
        caplog.set_level(logging.INFO, logger="omni_sdk")
        # OK result
        caplog.clear()
        Result.ok(123)  # create value, but we only log through log_result
        logmod.log_result(Result.ok(123), "sample")
        assert any("sample: succeeded" in rec.getMessage() for rec in caplog.records)

        # Error result
        caplog.clear()
        err = Error(kind="TestError", message="boom", details={"a": 1})
        logmod.log_result(Result.err(err), "sample_error")
        last = caplog.records[-1].getMessage()
        assert "sample_error: failed" in last
        assert "TestError" in last


class TestSetLogLevel:
    def test_set_log_level_debug(self):
        logmod.set_log_level("debug")
        logger = logging.getLogger("omni_sdk")
        assert logger.level == logging.DEBUG

    def test_set_log_level_invalid_returns_error(self):
        result = logmod.set_log_level("notalevel")
        # Result should be an error (is_ok == False)
        assert isinstance(result, Result)
        assert result.is_ok is False
        err = result.error()
        assert err is not None
        assert err.message.startswith("Invalid log level:")
        # Ensure details include valid levels
        assert "valid_levels" in err.details


class TestFileAndConsoleHandlers:
    def test_file_logging_via_filehandler(self, tmp_path):
        logger = logging.getLogger("omni_sdk")
        log_file = tmp_path / "test_logging_file.log"
        fh = logging.FileHandler(str(log_file))
        fh.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(fh)

        try:
            logmod.log_info("hello file")
            fh.flush()
            with open(log_file, "r", encoding="utf-8") as f:
                content = f.read()
            assert "hello file" in content
        finally:
            logger.removeHandler(fh)
            fh.close()

    def test_console_formatter_present(self):
        logger = logging.getLogger("omni_sdk")
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
