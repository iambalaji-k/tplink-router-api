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

    print(f"Connecting to TP-Link router at {host} ...")
    
    try:
        async with ArcherAX12(host=host, password=password) as router:
            await router.login()
            print("[+] Login Successful!")

            # Fetch status via the status resource module
            status = await router.status.get()
            
            print("\nSystem Resources:")
            print(f"  CPU Usage: {status.system.cpu_usage * 100:.1f}%")
            print(f"  Memory Usage: {status.system.mem_usage * 100:.1f}%")
            
            print("\nLAN Configuration:")
            print(f"  IPv4 Address: {status.lan.ipaddr}")
            print(f"  Netmask: {status.lan.netmask}")
            print(f"  MAC Address: {status.lan.macaddr}")
            print(f"  DHCP Enabled: {status.lan.dhcp_enable}")
            
            print("\nWAN Interface:")
            print(f"  IP Address: {status.wan.ipaddr}")
            print(f"  Gateway: {status.wan.gateway}")
            print(f"  DNS Servers: Primary={status.wan.pridns}, Secondary={status.wan.snddns or 'N/A'}")
            print(f"  Connection Type: {status.wan.conntype}")
            print(f"  Uptime: {status.wan.uptime} seconds")

            print("\nWi-Fi SSIDs:")
            print(f"  2.4GHz: {status.wireless_2g.ssid} (Enabled={status.wireless_2g.enable}, Channel={status.wireless_2g.current_channel or 'N/A'})")
            print(f"  5GHz: {status.wireless_5g.ssid} (Enabled={status.wireless_5g.enable}, Channel={status.wireless_5g.current_channel or 'N/A'})")
            
    except RouterError as e:
        print(f"[-] Router error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
