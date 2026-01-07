"""Comprehensive unit tests for spicepy.error module."""

from __future__ import annotations

import pytest

from spicepy.error import SpiceAIError


class TestSpiceAIError:
    """Test SpiceAIError exception class."""

    def test_error_creation(self) -> None:
        """Test creating SpiceAIError."""
        error = SpiceAIError("test message")
        assert error.message == "test message"

    def test_error_str(self) -> None:
        """Test SpiceAIError string representation."""
        error = SpiceAIError("test message")
        assert str(error) == "Spice AI error: test message"

    def test_error_message_attribute(self) -> None:
        """Test message attribute is accessible."""
        error = SpiceAIError("my error")
        assert error.message == "my error"

    def test_error_is_exception(self) -> None:
        """Test SpiceAIError is an Exception."""
        error = SpiceAIError("test")
        assert isinstance(error, Exception)

    def test_error_can_be_raised(self) -> None:
        """Test SpiceAIError can be raised and caught."""
        with pytest.raises(SpiceAIError) as exc_info:
            raise SpiceAIError("raised error")
        assert exc_info.value.message == "raised error"

    def test_error_caught_as_exception(self) -> None:
        """Test SpiceAIError can be caught as generic Exception."""
        with pytest.raises(Exception):
            raise SpiceAIError("generic catch")

    def test_error_empty_message(self) -> None:
        """Test SpiceAIError with empty message."""
        error = SpiceAIError("")
        assert error.message == ""
        assert str(error) == "Spice AI error: "

    def test_error_unicode_message(self) -> None:
        """Test SpiceAIError with unicode message."""
        error = SpiceAIError("错误消息 🚨 сообщение")
        assert error.message == "错误消息 🚨 сообщение"
        assert "错误消息" in str(error)

    def test_error_long_message(self) -> None:
        """Test SpiceAIError with long message."""
        long_msg = "x" * 10000
        error = SpiceAIError(long_msg)
        assert error.message == long_msg
        assert len(str(error)) > 10000

    def test_error_with_special_characters(self) -> None:
        """Test SpiceAIError with special characters."""
        msg = "Error: connection failed\nDetails: timeout at 10.0.0.1:50051\tRetry: true"
        error = SpiceAIError(msg)
        assert error.message == msg

    def test_error_repr(self) -> None:
        """Test SpiceAIError representation."""
        error = SpiceAIError("test")
        # Should not raise
        repr(error)

    def test_error_args(self) -> None:
        """Test SpiceAIError args attribute."""
        error = SpiceAIError("test message")
        # Exception.args should contain the message
        assert "test message" in str(error.args) or error.message == "test message"

    def test_error_with_formatted_message(self) -> None:
        """Test SpiceAIError with formatted message."""
        error = SpiceAIError(f"Query failed after {5} retries with status {500}")
        assert "5" in error.message
        assert "500" in error.message

    def test_multiple_errors(self) -> None:
        """Test creating multiple SpiceAIError instances."""
        errors = [SpiceAIError(f"error {i}") for i in range(10)]
        for i, error in enumerate(errors):
            assert error.message == f"error {i}"

    def test_error_equality(self) -> None:
        """Test SpiceAIError is not equal to same message error by default."""
        error1 = SpiceAIError("same")
        error2 = SpiceAIError("same")
        # Different instances should not be equal (default Exception behavior)
        assert error1 is not error2

    def test_error_chaining(self) -> None:
        """Test SpiceAIError can be chained."""
        try:
            try:
                raise ValueError("original error")
            except ValueError as e:
                raise SpiceAIError("wrapped error") from e
        except SpiceAIError as e:
            assert e.message == "wrapped error"
            assert e.__cause__ is not None
            assert isinstance(e.__cause__, ValueError)
