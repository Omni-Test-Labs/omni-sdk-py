#!/usr/bin/env python3
"""Quick test runner that bypasses pytest plugin conflicts."""

import sys

sys.path.insert(0, "/home/gh503/Code/Omni-Test-Labs/omni-sdk-py")
sys.path.insert(0, "/home/gh503/Code/Omni-Test-Labs/omni-sdk-py/tests")

# Import test module directly
from test_ssh_client import (
    test_initialize_missing_required_fields,
    test_initialize_requires_authentication,
    test_connect_success_password_and_is_connected,
    test_connect_authentication_error,
    test_connect_ssh_exception,
    test_disconnect_cleans_up,
    test_send_and_receive_behaviors,
    test_file_transfer_success_and_failure,
    test_get_status_and_capabilities,
    test_receive_timeout_error,
    # New tests
    test_execute_simple_command_success,
    test_execute_command_with_multiline_output,
    test_execute_command_with_stderr,
    test_execute_command_failure_nonzero_exit,
    test_execute_command_failure_with_stderr,
    test_execute_command_timeout,
    test_execute_not_connected,
    test_execute_custom_timeout,
    test_execute_empty_command,
    test_execute_command_with_unicode_output,
    test_send_raw_simple_text,
    test_send_raw_multiline_text,
    test_send_raw_special_characters,
    test_send_raw_empty_string,
    test_send_raw_not_connected,
    test_send_raw_no_shell,
    test_send_raw_shell_exception,
    test_execute_after_disconnect,
    test_send_raw_after_disconnect,
    test_multiple_execute_same_connection,
    test_multiple_send_raw_same_connection,
)

# List of all test functions
all_tests = [
    (
        "test_initialize_missing_required_fields",
        test_initialize_missing_required_fields,
    ),
    (
        "test_initialize_requires_authentication",
        test_initialize_requires_authentication,
    ),
    (
        "test_connect_success_password_and_is_connected",
        test_connect_success_password_and_is_connected,
    ),
    ("test_connect_authentication_error", test_connect_authentication_error),
    ("test_connect_ssh_exception", test_connect_ssh_exception),
    ("test_disconnect_cleans_up", test_disconnect_cleans_up),
    ("test_send_and_receive_behaviors", test_send_and_receive_behaviors),
    ("test_file_transfer_success_and_failure", test_file_transfer_success_and_failure),
    ("test_get_status_and_capabilities", test_get_status_and_capabilities),
    ("test_receive_timeout_error", test_receive_timeout_error),
    ("test_execute_simple_command_success", test_execute_simple_command_success),
    (
        "test_execute_command_with_multiline_output",
        test_execute_command_with_multiline_output,
    ),
    ("test_execute_command_with_stderr", test_execute_command_with_stderr),
    (
        "test_execute_command_failure_nonzero_exit",
        test_execute_command_failure_nonzero_exit,
    ),
    (
        "test_execute_command_failure_with_stderr",
        test_execute_command_failure_with_stderr,
    ),
    ("test_execute_command_timeout", test_execute_command_timeout),
    ("test_execute_not_connected", test_execute_not_connected),
    ("test_execute_custom_timeout", test_execute_custom_timeout),
    ("test_execute_empty_command", test_execute_empty_command),
    (
        "test_execute_command_with_unicode_output",
        test_execute_command_with_unicode_output,
    ),
    ("test_send_raw_simple_text", test_send_raw_simple_text),
    ("test_send_raw_multiline_text", test_send_raw_multiline_text),
    ("test_send_raw_special_characters", test_send_raw_special_characters),
    ("test_send_raw_empty_string", test_send_raw_empty_string),
    ("test_send_raw_not_connected", test_send_raw_not_connected),
    ("test_send_raw_no_shell", test_send_raw_no_shell),
    ("test_send_raw_shell_exception", test_send_raw_shell_exception),
    ("test_execute_after_disconnect", test_execute_after_disconnect),
    ("test_send_raw_after_disconnect", test_send_raw_after_disconnect),
    ("test_multiple_execute_same_connection", test_multiple_execute_same_connection),
    ("test_multiple_send_raw_same_connection", test_multiple_send_raw_same_connection),
]

# Run all tests
run_count = 0
passed_count = 0
failed_count = 0
error_count = 0

print(f"Running {len(all_tests)} tests...")
print("=" * 70)

for name, test_func in all_tests:
    run_count += 1
    try:
        print(f"[{run_count}/{len(all_tests)}] Running {name}...", end=" ")
        test_func()
        print("✓ PASSED")
        passed_count += 1
    except AssertionError as e:
        print(f"✗ FAILED")
        print(f"  Assertion: {e}")
        failed_count += 1
    except Exception as e:
        print(f"✗ ERROR")
        print(f"  Exception: {type(e).__name__}: {e}")
        error_count += 1

print("=" * 70)
print(f"Results: {run_count} tests ran")
print(f"  Passed: {passed_count}")
print(f"  Failed: {failed_count}")
print(f"  Errors: {error_count}")
print(f"  Total issues: {failed_count + error_count}")

if failed_count + error_count == 0:
    print("\n✓ All tests passed!")
    sys.exit(0)
else:
    print(f"\n✗ {failed_count + error_count} test(s) failed")
    sys.exit(1)
