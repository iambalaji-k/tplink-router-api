"""Enumerate the AX12 UI's route table and menu tree, and map every page to the forms it can reach.

The form inventory says what the bundles reference; it does not say what a user can navigate to.
This tool reads the Vue router table (``{name, path, component: () => import("./x.js")}``), the
left-hand menu tree, and the bundle import graph, then joins them against the form inventory so a
coverage gap shows up as a *page with no inventoried form* or a *form with no page*.

Read-only over files; nothing here talks to a router.

    venv/Scripts/python.exe -m tools.inventory.ui_routes \
        --bundles .cache/ax12-ui/bundles --inventory .cache/ax12-ui/inventory-v2.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from tools.inventory.jstokens import match_array

ROUTE_RE = re.compile(r'\{name:"([A-Za-z0-9_\-]+)",path:"([^"]*)",component:')
# Whitespace is optional because the bundles are minified, but a hand-written or prettified chunk
# may space the keyword out; both have to resolve to the same import graph.
IMPORT_SPEC_RE = re.compile(r'import\s*\(\s*"([^"]+?)"\s*\)|from\s*"(\.{1,2}/[^"]+?)"|import\s*"(\.{1,2}/[^"]+?)"')
MENU_ENTRY_RE = re.compile(r'\{key:"([A-Za-z0-9_\-]+)"(?:,text:"(menu\.[A-Za-z0-9_.\-]+)")?')
# Menu trees start with a leaf like `[{key:"networkMap",text:"menu.networkMap"}`.
MENU_START_RE = re.compile(r'\[\{key:"[A-Za-z0-9_\-]+",text:"menu\.')


def basename_of(name: str) -> str:
    """`webpages__js__index-BEa7yDFE.js` -> `index-BEa7yDFE.js`, the name sibling imports use.

    The crawler joins path segments with `__`, which is ambiguous: a hashed file name can contain
    `__` itself (`IotNetWorkCard-D0OUY3__.js`). Directory segments never contain `.` or `-` while
    hashed file names always do, so stripping the leading segments that lack both is unambiguous,
    and re-joining the remainder preserves any `__` inside the file name.
    """
    parts = name.split("__")
    while len(parts) > 1 and "-" not in parts[0] and "." not in parts[0]:
        parts = parts[1:]
    return "__".join(parts)


def spec_basename(spec: str) -> str:
    return os.path.basename(spec.replace("\\", "/"))


@dataclass
class Route:
    name: str
    path: str
    chunk: str
    page: str | None


@dataclass
class MenuEntry:
    key: str
    text: str
    depth: int


@dataclass
class Page:
    route: Route
    own_chunks: list[str]
    forms: list[str]
    shared_forms: list[str]
    missing_imports: list[str]


def read_bundles(directory: str) -> dict[str, str]:
    """Bundle file name -> source, for every `.js` the crawler saved."""
    out: dict[str, str] = {}
    for name in sorted(os.listdir(directory)):
        if name.endswith(".js"):
            with open(os.path.join(directory, name), encoding="utf-8", errors="replace") as handle:
                out[name] = handle.read()
    return out


def parse_routes(text: str, chunk: str) -> list[Route]:
    """Every `{name, path, component: () => import("./x.js")}` router entry in a bundle."""
    routes: list[Route] = []
    for match in ROUTE_RE.finditer(text):
        spec = re.search(r'import\("([^"]+)"\)', text[match.end() : match.end() + 200])
        routes.append(Route(match.group(1), match.group(2), chunk, None if spec is None else spec.group(1)))
    return routes


def parse_menu(body: str) -> list[MenuEntry]:
    """Depth-tagged entries of one menu array; depth comes from brace nesting."""
    entries: list[MenuEntry] = []
    for match in MENU_ENTRY_RE.finditer(body):
        head = body[: match.start()]
        entries.append(MenuEntry(match.group(1), match.group(2) or "", max(head.count("{") - head.count("}"), 0)))
    return entries


def menu_trees(text: str) -> list[list[MenuEntry]]:
    """Every real menu array in a bundle.

    Menu *filtering* code writes the same `{key, text}` shape while mapping over a tree, so a bare
    scan over the file counts each key dozens of times. Each array is bounded with a bracket match
    and only arrays carrying several distinct keys are taken as a tree.
    """
    trees: list[list[MenuEntry]] = []
    for match in MENU_START_RE.finditer(text):
        _, body = match_array(text, match.start() + 1)
        entries = parse_menu(body)
        if len({entry.key for entry in entries}) >= 5:
            trees.append(entries)
    return trees


def imports_of(bundles: dict[str, str]) -> dict[str, list[str]]:
    """Chunk -> every module specifier it imports, static or dynamic, unresolved included."""
    out: dict[str, list[str]] = {}
    for name, text in bundles.items():
        specs: list[str] = []
        for match in IMPORT_SPEC_RE.finditer(text):
            spec = match.group(1) or match.group(2) or match.group(3)
            if spec and "${" not in spec:
                specs.append(spec)
        out[name] = specs
    return out


def import_edges(bundles: dict[str, str], specs: dict[str, list[str]], by_base: dict[str, str]) -> dict[str, set[str]]:
    edges: dict[str, set[str]] = defaultdict(set)
    for name in bundles:
        for spec in specs.get(name, []):
            target = by_base.get(spec_basename(spec))
            if target and target != name:
                edges[name].add(target)
    return edges


def in_degree(edges: dict[str, set[str]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for targets in edges.values():
        for target in targets:
            counts[target] += 1
    return counts


def closure(start: str, edges: dict[str, set[str]], limit: int) -> set[str]:
    """Every chunk reachable from `start` within `limit` import hops."""
    seen = {start}
    frontier = {start}
    for _ in range(limit):
        nxt: set[str] = set()
        for chunk in frontier:
            nxt |= {target for target in edges.get(chunk, set()) if target not in seen}
        seen |= nxt
        frontier = nxt
        if not frontier:
            break
    return seen


def forms_by_chunk(inventory: dict[str, Any]) -> dict[str, set[str]]:
    """Chunk file name -> `module?form=` strings the scanner found in it."""
    out: dict[str, set[str]] = defaultdict(set)
    for module, forms in inventory["modules"].items():
        for form, info in forms.items():
            for chunk in info["chunks"]:
                out[chunk].add(f"{module}?form={form}")
    return out


def build_pages(
    routes: list[Route],
    bundles: dict[str, str],
    specs: dict[str, list[str]],
    by_base: dict[str, str],
    edges: dict[str, set[str]],
    shared: set[str],
    chunk_forms: dict[str, set[str]],
    depth: int,
) -> list[Page]:
    pages: list[Page] = []
    for route in routes:
        if route.page is None or route.chunk not in bundles:
            pages.append(Page(route, [], [], [], []))
            continue
        start = by_base.get(spec_basename(route.page))
        if start is None:
            pages.append(Page(route, [], [], [], [spec_basename(route.page)]))
            continue
        reachable = closure(start, edges, depth)
        own = sorted(reachable - shared)
        forms = sorted({form for chunk in own for form in chunk_forms.get(chunk, set())})
        shared_forms = sorted({form for chunk in reachable & shared for form in chunk_forms.get(chunk, set())})
        missing = sorted(
            {
                spec_basename(spec)
                for chunk in reachable
                for spec in specs.get(chunk, [])
                if spec_basename(spec) not in by_base
            }
        )
        pages.append(Page(route, own, forms, shared_forms, missing))
    return pages


def routes_and_menus(bundles: dict[str, str]) -> tuple[list[Route], list[list[MenuEntry]]]:
    """The router table and every real menu tree across all bundles; trees sorted largest first."""
    routes: list[Route] = []
    trees: list[list[MenuEntry]] = []
    for name, text in bundles.items():
        routes.extend(parse_routes(text, name))
        trees.extend(menu_trees(text))
    trees.sort(key=len, reverse=True)
    return routes, trees


def page_form_map(
    bundles: dict[str, str],
    inventory: dict[str, Any],
    depth: int = 1,
    hub_threshold: int | None = None,
) -> list[Page]:
    """Each route, the chunks it owns, and the forms reachable in them.

    `depth` is the number of import hops a page may borrow from. `hub_threshold` decides when a
    chunk is app plumbing rather than a feature module; it defaults to a sixth of the bundle count,
    which on the AX12 separates vendor/store/composables from feature chunks.
    """
    by_base = {basename_of(name): name for name in bundles}
    specs = imports_of(bundles)
    edges = import_edges(bundles, specs, by_base)
    popularity = in_degree(edges)
    threshold = hub_threshold if hub_threshold is not None else max(8, len(bundles) // 12)
    shared = {name for name, count in popularity.items() if count >= threshold}
    routes, _ = routes_and_menus(bundles)
    return build_pages(routes, bundles, specs, by_base, edges, shared, forms_by_chunk(inventory), depth)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles", default=".cache/ax12-ui/bundles")
    parser.add_argument("--inventory", default=".cache/ax12-ui/inventory-v2.json")
    parser.add_argument("--out", default=".cache/ax12-ui/ui-routes.json")
    parser.add_argument("--depth", type=int, default=1, help="import hops a page may borrow forms from")
    args = parser.parse_args()

    bundles = read_bundles(args.bundles)
    with open(args.inventory, encoding="utf-8") as handle:
        inventory = json.load(handle)

    by_base = {basename_of(name): name for name in bundles}
    specs = imports_of(bundles)
    edges = import_edges(bundles, specs, by_base)
    popularity = in_degree(edges)
    # A chunk imported by this many others is app plumbing (vendor, the store, shared composables)
    # rather than a feature module, so its forms are reported as borrowed instead of owned.
    threshold = max(8, len(bundles) // 12)
    shared = {name for name, count in popularity.items() if count >= threshold}

    chunk_forms = forms_by_chunk(inventory)
    all_forms = {form for forms in chunk_forms.values() for form in forms}

    routes, trees = routes_and_menus(bundles)
    menus = trees[0] if trees else []

    pages = build_pages(routes, bundles, specs, by_base, edges, shared, chunk_forms, args.depth)
    reached = {form for page in pages for form in page.forms}
    with_pages = reached | {form for page in pages for form in page.shared_forms}
    hub_only = sorted(all_forms - reached)
    unattributed = sorted(all_forms - with_pages)
    menu_keys = {entry.key for entry in menus}
    route_names = {route.name for route in routes}
    unfetched = sorted({spec_basename(s) for chunk in bundles for s in specs.get(chunk, []) if spec_basename(s) not in by_base})

    report: dict[str, Any] = {
        "counts": {
            "routes": len(routes),
            "routes_without_a_component": sum(1 for page in pages if not page.own_chunks),
            "menu_entries": len(menu_keys),
            "menu_trees": len(trees),
            "menu_trees_extra": len(trees) - 1,
            "menu_keys_without_a_route": len(menu_keys - route_names),
            "shared_chunks": len(shared),
            "forms_total": len(all_forms),
            "forms_reachable_from_a_page": len(reached),
            "forms_only_in_shared_chunks": len(hub_only),
            "forms_no_page_reaches": len(unattributed),
            "imports_never_fetched": len(unfetched),
        },
        "pages": [
            {
                "name": page.route.name,
                "path": page.route.path,
                "component": basename_of(page.route.page or ""),
                "own_chunks": len(page.own_chunks),
                "forms": page.forms,
                "borrowed_from_shared_chunks": page.shared_forms,
                "imports_never_fetched": page.missing_imports,
            }
            for page in sorted(pages, key=lambda p: p.route.name)
        ],
        "menu": [{"key": entry.key, "text": entry.text, "depth": entry.depth} for entry in menus],
        "menu_trees": [[{"key": e.key, "text": e.text, "depth": e.depth} for e in tree] for tree in trees[1:]],
        "menu_keys_without_a_route": sorted(menu_keys - route_names),
        "route_names_without_a_menu_entry": sorted(route_names - menu_keys),
        "forms_only_in_shared_chunks": hub_only,
        "forms_no_page_reaches": unattributed,
        "imports_never_fetched": unfetched,
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)

    counts = report["counts"]
    print(f"{counts['routes']} routes / {counts['menu_entries']} menu entries / {counts['shared_chunks']} shared chunks")
    print(f"{counts['forms_total']} inventoried forms, {counts['forms_reachable_from_a_page']} in a page's own "
          f"feature chunks, {counts['forms_only_in_shared_chunks']} only in shared chunks, "
          f"{counts['forms_no_page_reaches']} no page reaches")
    print(f"\n{'page':<36} {'own':>4} {'forms':>6} {'borrowed':>9}")
    for page in report["pages"]:
        print(f"{page['name']:<36} {page['own_chunks']:>4} {len(page['forms']):>6} {len(page['borrowed_from_shared_chunks']):>9}")
    empty = [page for page in report["pages"] if not page["forms"]]
    print(f"\npages whose own chunks hold no inventoried form ({len(empty)}):")
    for page in empty:
        print(f"  {page['name']:<36} borrowed={len(page['borrowed_from_shared_chunks']):>3} "
              f"component={page['component'] or '-'}")
    print(f"menu keys with no route ({len(report['menu_keys_without_a_route'])}): "
          f"{', '.join(report['menu_keys_without_a_route']) or '-'}")
    print(f"no page reaches ({counts['forms_no_page_reaches']}): {', '.join(report['forms_no_page_reaches']) or '-'}")
    print(f"imports never fetched ({len(unfetched)}): {', '.join(unfetched[:12]) or '-'}")
    print(f"report: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
