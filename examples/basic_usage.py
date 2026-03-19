"""
Basic usage example for Omni SDK.

Demonstrates how to use the SDK to manage devices with SSH client.
"""

import sys
from omni_sdk import initialize_from_config, connect_device


def main():
    """
    Main example demonstrating SDK usage.

    1. Load configuration from devices.toml
    2. Connect to device
    3. Execute commands via SSH
    4. Get device status
    5. Cleanup and disconnect
    """
    print("=" * 60)
    print("Omni SDK - Basic Usage Example")
    print("=" * 60)

    # Step 1: Load configuration
    print("\n[1] Loading configuration from devices.toml...")
    devices_result = initialize_from_config("devices.toml")

    if not devices_result.is_ok:
        print(f"✗ Failed to load config: {devices_result._error.message}")
        sys.exit(1)

    devices = devices_result.unwrap()
    print(f"✓ Loaded {len(devices)} device(s)")

    # List all devices
    for device_id, device in devices.items():
        print(f"  - {device_id}: {device.name}")
        print(f"    Clients: {device.list_clients()}")
        print(f"    Capabilities: {device.list_capabilities()}")

    # Step 2: Connect to first device
    if not devices:
        print("\n✗ No devices configured")
        sys.exit(1)

    first_device_id = list(devices.keys())[0]
    print(f"\n[2] Connecting to device: {first_device_id}...")

    connect_result = connect_device(first_device_id, devices)
    if not connect_result.is_ok:
        print(f"✗ Failed to connect: {connect_result._error.message}")
        sys.exit(1)

    device = connect_result.unwrap()
    print(f"✓ Connected to {device.name}")

    # Step 3: Get device status
    print("\n[3] Getting device status...")
    status = device.get_status()
    print(f"  Device ID: {status['device_id']}")
    print(f"  Name: {status['name']}")
    for client_name, client_info in status["clients"].items():
        conn_status = "connected" if client_info["connected"] else "disconnected"
        print(f"  Client: {client_name} v{client_info['version']} ({conn_status})")
    print(f"  Total capabilities: {len(status['capabilities'])}")

    # Step 4: Execute commands via SSH (if available)
    print(f"\n[4] Executing commands via SSH...")
    print(f"  Available capabilities: {device.list_capabilities()}")

    if "execute" in device.list_capabilities():
        # Execute a simple command
        print("\n  Executing: 'echo Hello from OmniSDK'")
        execute_result = device.execute("execute", 'echo "Hello from OmniSDK"')

        if execute_result.is_ok:
            output = execute_result.unwrap()
            print(f"  ✓ Output:\n{output}")
        else:
            print(f"  ✗ Command failed: {execute_result._error.message}")

        # Try another command
        print("\n  Executing: 'uname -a'")
        execute_result = device.execute("execute", "uname -a")

        if execute_result.is_ok:
            output = execute_result.unwrap()
            print(f"  ✓ Output:\n{output}")
        else:
            print(f"  ✗ Command failed: {execute_result._error.message}")
    else:
        print("  Note: 'execute' capability not available (no SSH client)")

    # Step 5: Cleanup
    print(f"\n[5] Disconnecting from device...")
    disconnect_result = device.disconnect_all()
    if disconnect_result.is_ok:
        print("✓ Disconnected successfully")
    else:
        print(f"✗ Disconnect warning: {disconnect_result._error.message}")

    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


def main_mock_mode():
    """
    Example running in mock mode (no real devices).

    Demonstrates error handling and Result<T> pattern.
    """
    print("\n" + "=" * 60)
    print("Omni SDK - Mock Mode Example")
    print("=" * 60)

    # Example of error handling with Result<T>
    from omni_sdk.result import Result, ErrorKinds, create_error_result

    print("\n[1] Demonstrating Result<T> error handling...")

    # Simulate operation that might fail
    def risky_operation(status: str) -> Result[str]:
        if status == "fail":
            return create_error_result(
                kind=ErrorKinds.NETWORK_ERROR, message="Simulated network error"
            )
        return Result.ok(f"Operation succeeded with status: {status}")

    # Try successful operation
    result = risky_operation("success")
    if result.is_ok:
        print(f"  ✓ {result.unwrap()}")
    else:
        print(f"  ✗ {result._error.message}")

    # Try failed operation
    result = risky_operation("fail")
    if result.is_ok:
        print(f"  ✓ {result.unwrap()}")
    else:
        print(f"  ✗ {result._error.message}")

    # Example of chaining with and_then
    print("\n[2] Demonstrating Result<T> chaining with and_then...")

    def step1(value: int) -> Result[int]:
        return Result.ok(value * 2)

    def step2(value: int) -> Result[int]:
        return Result.ok(value + 10)

    def step3(value: int) -> Result[int]:
        return Result.ok(value * value)

    # Chain operations
    result = Result.ok(5).and_then(step1).and_then(step2).and_then(step3)

    if result.is_ok:
        print(f"  ✓ Chain result: 5 -> {result.unwrap()} (expected (5*2+10)^2 = 400)")
    else:
        print(f"  ✗ Chain failed: {result._error.message}")

    # Chain with error
    def failing_step(value: int) -> Result[int]:
        return create_error_result(
            kind=ErrorKinds.RUNTIME_ERROR, message="Step failed intentionally"
        )

    result = Result.ok(5).and_then(step1).and_then(failing_step).and_then(step3)

    if result.is_ok:
        print(f"  ✓ Chain result: {result.unwrap()}")
    else:
        print(f"  ✓ Chain stopped at error: {result._error.message}")

    print("\n" + "=" * 60)
    print("Mock mode example completed!")
    print("=" * 60)


if __name__ == "__main__":
    # Run mock mode first (doesn't require real device)
    main_mock_mode()

    # Uncomment below to run with real device
    # Requires devices.toml configuration file
    # main()
