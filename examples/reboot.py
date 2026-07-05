import asyncio
import os
import sys

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tplink_modern import ArcherAX12
from tplink_modern.exceptions import RouterError
from login import load_env_file


async def main():
    load_env_file()
    host = os.environ.get("TPLINK_HOST", "192.168.0.1")
    password = os.environ.get("TPLINK_PASSWORD")

    if not password:
        print("Error: TPLINK_PASSWORD environment variable not set.")
        sys.exit(1)

    # Ask for confirmation before rebooting to prevent accidental disruption
    confirm = input("Are you sure you want to reboot the router? (y/N): ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Reboot cancelled.")
        sys.exit(0)

    print(f"Connecting to TP-Link router at {host} ...")
    
    try:
        async with ArcherAX12(host=host, password=password) as router:
            await router.login()
            print("[+] Login Successful!")

            print("[*] Sending reboot command to system...")
            success = await router.system.reboot()
            if success:
                print("[+] Reboot command accepted by the router. It will restart shortly.")
            else:
                print("[-] Router rejected or failed to process the reboot command.")
            
    except RouterError as e:
        print(f"[-] Router error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
