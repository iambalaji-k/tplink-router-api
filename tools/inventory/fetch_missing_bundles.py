"""Fetch bundle files the crawler missed, without logging in.

Static assets under `/webpages/` are served without a stok, so this tool issues plain GETs: it
never authenticates and therefore cannot evict the single admin session the router keeps. It exists
because the coverage report found one *feature* chunk (`IotNetWorkCard-*.js`) that was never
downloaded, and a missing chunk is a silent gap in the inventory.

    venv/Scripts/python.exe -m tools.inventory.fetch_missing_bundles \
        --bundles .cache/ax12-ui/bundles --host 192.168.0.1
"""

from __future__ import annotations

import argparse
import os
import re

import httpx

from tools.inventory.ui_routes import basename_of, read_bundles, spec_basename

# Only relative specifiers: absolute ones point at the router's own runtime, not at a bundle.
SPEC_RE = re.compile(
    r'import\s*\(\s*"(\.{1,2}/[^"]+?\.js)"\s*\)|from\s*"(\.{1,2}/[^"]+?\.js)"|import\s*"(\.{1,2}/[^"]+?\.js)"'
)


def web_path(chunk_name: str) -> str:
    """`webpages__js__index-abc.js` -> `webpages/js/index-abc.js`."""
    return chunk_name.replace("__", "/")


def resolve(spec: str, from_chunk: str) -> str:
    """Bundle-relative import specifier -> repo-style bundle path."""
    base = os.path.dirname(web_path(from_chunk))
    joined = os.path.normpath(os.path.join(base, spec)).replace("\\", "/")
    return joined.lstrip("./")


def missing_specifiers(bundles: dict[str, str]) -> list[tuple[str, str]]:
    """`(bundle, specifier)` pairs whose target is not on disk."""
    present = {basename_of(name) for name in bundles}
    out: list[tuple[str, str]] = []
    for name, text in bundles.items():
        for match in SPEC_RE.finditer(text):
            spec = match.group(1) or match.group(2) or match.group(3)
            if spec and "${" not in spec and spec_basename(spec) not in present:
                out.append((name, spec))
    return sorted(set(out))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles", default=".cache/ax12-ui/bundles")
    parser.add_argument("--host", required=True, help="router address, e.g. 192.168.0.1")
    parser.add_argument("--fetch", action="store_true", help="download the missing bundles (default: list only)")
    parser.add_argument("--include-locale", action="store_true", help="also fetch translation bundles (no endpoints)")
    args = parser.parse_args()

    bundles = read_bundles(args.bundles)
    missing = missing_specifiers(bundles)
    locale = [(chunk, spec) for chunk, spec in missing if "/locale/" in resolve(spec, chunk)]
    feature = [(chunk, spec) for chunk, spec in missing if "/locale/" not in resolve(spec, chunk)]
    for chunk, spec in missing:
        label = "locale" if "/locale/" in resolve(spec, chunk) else "FEATURE"
        print(f"MISSING [{label}]  {resolve(spec, chunk):<58} <- {basename_of(chunk)}")
    print(f"\n{len(missing)} specifiers not on disk: {len(feature)} feature, {len(locale)} locale")

    targets = feature + locale if args.include_locale else feature
    if not args.fetch:
        print("pass --fetch to download the feature bundles (plain GET, no login)")
        return 0
    if not targets:
        print("nothing to fetch")
        return 0

    base = args.host if args.host.startswith("http") else f"http://{args.host}"
    saved = 0
    with httpx.Client(base_url=base, timeout=20.0) as client:
        for chunk, spec in targets:
            target = resolve(spec, chunk)
            if not target.startswith("webpages/"):
                continue
            response = client.get(f"/{target}")
            if response.status_code != 200 or not response.text:
                print(f"  {response.status_code}  {target}")
                continue
            path = os.path.join(args.bundles, target.replace("/", "__"))
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(response.text)
            print(f"  saved {target} ({len(response.text)} bytes)")
            saved += 1
    print(f"\nfetched {saved} bundles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
