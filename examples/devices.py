import asyncio
import os
import sys

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from login import load_env_file

from tplink_modern import ArcherAX12
from tplink_modern.exceptions import RouterError


async def main():
    load_env_file()
    host = os.environ.get("TPLINK_HOST", "192.168.0.1")
    password = os.environ.get("TPLINK_PASSWORD")

    if not password:
        print("Error: TPLINK_PASSWORD environment variable not set.")
        sys.exit(1)

    print(f"Connecting to TP-Link router at {host} ...")
    
    try:
        async with ArcherAX12(host=host, password=password) as router:
            await router.login()
            print("[+] Login Successful!")

            # Fetch connected clients via the clients resource module
            devices = await router.clients.get_all()
            
            print(f"\n[+] Found {len(devices)} connected devices:")
            print(f"{'Hostname':<25} {'IP Address':<15} {'MAC Address':<20} {'Connection Type':<15}")
            print("-" * 78)
            for dev in devices:
                hostname = dev.hostname if dev.hostname else "<unknown>"
                print(f"{hostname:<25} {dev.ipaddr:<15} {dev.macaddr:<20} {dev.wire_type:<15}")
            
    except RouterError as e:
        print(f"[-] Router error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
