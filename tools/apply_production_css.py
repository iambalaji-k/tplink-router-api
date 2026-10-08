"""Replace Tailwind Play CDN with compiled static production CSS and add favicon links across all UI views."""

import re
import os

HTML_FILES = [
    'ui/stitch_preview.html',
    'ui/stitch_api_explorer.html',
    'ui/stitch_clients.html',
    'ui/stitch_security.html',
    'ui/stitch_wireless.html',
]

def update_html_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()

    # 1. Remove Tailwind CDN script tag
    html = re.sub(
        r'<script src="https://cdn\.tailwindcss\.com\?plugins=forms,container-queries"[^>]*>[\s\S]*?</script>',
        '',
        html
    )
    html = re.sub(
        r'<script src="https://cdn\.tailwindcss\.com\?plugins=forms,container-queries"[^>]*>\s*',
        '',
        html
    )

    # 2. Remove <script id="tailwind-config"> blocks
    html = re.sub(
        r'<script id="tailwind-config">[\s\S]*?</script>',
        '',
        html
    )

    # 3. Add favicon links and static tailwind.css link in <head> if not present
    head_injection = '''<link rel="icon" type="image/x-icon" href="/favicon.ico"/>
<link rel="icon" type="image/svg+xml" href="/dashboard/favicon.svg"/>
<link rel="stylesheet" href="/dashboard/tailwind.css"/>'''

    # Ensure no duplicates
    if '/dashboard/tailwind.css' not in html:
        # Insert after <head> or meta charset
        if '<meta charset="utf-8"/>' in html:
            html = html.replace('<meta charset="utf-8"/>', '<meta charset="utf-8"/>\n' + head_injection)
        elif '<head>' in html:
            html = html.replace('<head>', '<head>\n' + head_injection)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Updated {filepath} with production CSS and favicon.")

def main():
    for f in HTML_FILES:
        if os.path.exists(f):
            update_html_file(f)

if __name__ == '__main__':
    main()
