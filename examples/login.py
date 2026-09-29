import asyncio
import os
import sys

# Add parent directory to sys.path so we can import the local module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx

from tplink_modern import ArcherAX12
from tplink_modern.exceptions import RouterError


def load_env_file():
    """Load variables from .env file into os.environ if it exists."""
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")


async def main():
    # Load .env file
    load_env_file()
    
    # Read host and password from environment variables
    host = os.environ.get("TPLINK_HOST", "192.168.0.1")
    password = os.environ.get("TPLINK_PASSWORD")

    if not password:
        print("Error: TPLINK_PASSWORD environment variable not set.")
        print("Please set it in your environment before running, for example:")
        print("  PowerShell: $env:TPLINK_PASSWORD='your_password'")
        print("  Command Prompt: set TPLINK_PASSWORD=your_password")
        print("  Bash: export TPLINK_PASSWORD='your_password'")
        sys.exit(1)

    print(f"Connecting to TP-Link router at {host} ...")
    
    try:
        async with ArcherAX12(host=host, password=password) as router:
            print("Performing authentication handshake...")
            await router.login()
            print("[+] Authentication Successful!")
            print(f"[+] Retrieved Session Token (stok): {router.session.stok}")

            # Verify by printing some basic information from status
            status = await router.get_status()
            print("\nVerification Details:")
            print(f"  LAN MAC Address: {status.lan.macaddr}")
            print(f"  Wireless 2.4G Encryption: {status.wireless_2g.encryption}")
            
    except RouterError as e:
        print(f"[-] Router error occurred: {e}")
        sys.exit(1)
    except (httpx.HTTPError, OSError) as e:
        # Router unreachable, DNS failure, connection reset -- expected in a CLI tool.
        print(f"[-] Transport error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
