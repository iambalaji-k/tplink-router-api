import os
import re

files = [
    'ui/stitch_preview.html',
    'ui/stitch_clients.html',
    'ui/stitch_wireless.html',
    'ui/stitch_security.html',
    'ui/stitch_api_explorer.html',
]

def update_nav(content: str) -> str:
    # 1. Overview
    content = re.sub(
        r'<a([^>]*?)href="#"([^>]*?)>\s*<span[^>]*data-icon="router"[^>]*>router</span>\s*<span>Overview</span>',
        r'<a\1href="stitch_preview.html"\2><span class="material-symbols-outlined" data-icon="router">router</span><span>Overview</span>',
        content
    )
    # 2. Clients
    content = re.sub(
        r'<a([^>]*?)href="#"([^>]*?)>\s*<div[^>]*>\s*<span[^>]*data-icon="devices"[^>]*>devices</span>\s*<span>Clients</span>',
        r'<a\1href="stitch_clients.html"\2><div class="flex items-center gap-space-sm"><span class="material-symbols-outlined" data-icon="devices">devices</span><span>Clients</span>',
        content
    )
    # 3. Wireless
    content = re.sub(
        r'<a([^>]*?)href="#"([^>]*?)>\s*<span[^>]*data-icon="wifi"[^>]*>wifi</span>\s*<span>Wireless Radios</span>',
        r'<a\1href="stitch_wireless.html"\2><span class="material-symbols-outlined" data-icon="wifi">wifi</span><span>Wireless Radios</span>',
        content
    )
    # 4. Security
    content = re.sub(
        r'<a([^>]*?)href="#"([^>]*?)>\s*<span[^>]*data-icon="shield"[^>]*>shield</span>\s*<span>Security &amp; DHCP</span>',
        r'<a\1href="stitch_security.html"\2><span class="material-symbols-outlined" data-icon="shield">shield</span><span>Security &amp; DHCP</span>',
        content
    )
    # 5. API Explorer
    content = re.sub(
        r'<a([^>]*?)href="#"([^>]*?)>\s*<div[^>]*>\s*<span[^>]*data-icon="terminal"[^>]*>terminal</span>\s*<span>API Explorer</span>',
        r'<a\1href="stitch_api_explorer.html"\2><div class="flex items-center gap-space-sm"><span class="material-symbols-outlined text-primary fill-icon" data-icon="terminal">terminal</span><span>API Explorer</span>',
        content
    )
    content = re.sub(
        r'<a([^>]*?)href="#"([^>]*?)>\s*<span[^>]*data-icon="terminal"[^>]*>terminal</span>\s*<span>API Explorer</span>',
        r'<a\1href="stitch_api_explorer.html"\2><span class="material-symbols-outlined" data-icon="terminal">terminal</span><span>API Explorer</span>',
        content
    )
    return content

for fn in files:
    if os.path.exists(fn):
        with open(fn, 'r', encoding='utf-8') as f:
            c = f.read()
        updated = update_nav(c)
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(updated)
        print(f"Updated nav links in {fn}")
