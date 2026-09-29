"""Rebuild the Archer AX12 router-API inventory from the router's own web bundles.

The previous scan matched only quoted literals like ``"admin/wireless?form=guest_2g"``. The UI's
request layer -- ``update-store-*.js`` exports a service object with
``request/read/write/load/insert/remove/update/file``, each taking the endpoint URL as its first
argument -- is in fact called four different ways:

* a quoted literal;
* a template literal whose base is a variable, ``e.read(`${n}form=guest`)`` with ``n="/admin/wireless?"``;
* a form name completed from a variable, ``i(`${n}_2g`)`` with ``n="/admin/wireless?form=wireless"``;
* a batch URL, because one request may carry several ``form=`` parameters --
  ```${n}${o.join("&")}```` with ``o=["form=guest_2g","form=guest_5g",...]``, and ``s+="&form=iot_5g_2"``.

This tool resolves all four and reports the URLs it could *not* resolve rather than quietly
under-counting them. It only reads bundle files and writes a report; nothing here talks to a router.

Usage:
    venv/Scripts/python.exe tools/inventory/extract_ui_inventory.py \
        --bundles .cache/ax12-ui/bundles --out .cache/ax12-ui/inventory-v2.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from tools.inventory.jstokens import EXPR, Literal, Part, call_span, match_braces, scan, skip_literal

# The UI service object's methods. Every one of them takes the endpoint URL as its first argument.
SERVICE_METHODS = ("request", "read", "write", "load", "insert", "remove", "update", "file")

HOLE_OPEN = "«"
HOLE_CLOSE = "»"

FORM_RE = re.compile(r"[?&]form=([a-z0-9_]+)")
FORM_STRICT_RE = re.compile(r"^&?form=([a-z0-9_]+)$")
MODULE_RE = re.compile(
    r"^/?(?:admin/[a-z0-9_]+|login|locale|debug|upgrade|wan_error|device_config"
    r"|domain_login|domain_redirect|blocking|accessibility)$"
)
PAYLOAD_OP_RE = re.compile(
    r"""operation\s*:\s*["']([a-z0-9_]+)["']"""
    r"""|append\(\s*["']operation["']\s*,\s*["']([a-z0-9_]+)["']"""
)
BOUND_NAME_RE = re.compile(r"([A-Za-z_$][\w$]{0,10})\s*(\+?=)\s*$")
FUNC_DEF_RE = re.compile(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*{")
ARROW_DEF_RE = re.compile(r"([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>\s*[{(]")
IDENT_RE = re.compile(r"^[A-Za-z_$][\w$]*$")
JOIN_RE = re.compile(r"^([A-Za-z_$][\w$]{0,10})\.join\(")
CALL0_RE = re.compile(r"^([A-Za-z_$][\w$]{0,10})\s*\(\s*\)$")
ARRAY_ASSIGN_RE = re.compile(r"([A-Za-z_$][\w$]{0,10})\s*=\s*\[")
PUSH_RE = re.compile(r"([A-Za-z_$][\w$]{0,10})\.push\(")
RETURN_RE = re.compile(r"\breturn\s+")
METHOD_CALL_RE = re.compile(r"\.(" + "|".join(SERVICE_METHODS) + r")\s*\(")
ANY_CALL_RE = re.compile(r"([A-Za-z_$][\w$]{0,12})\s*\(")
HOLE_SPAN_RE = re.compile(r"«[^«»]*»")
PATH_RUN_RE = re.compile(r"[^?&#«»\s,;()]*$")

MAX_DEPTH = 6
MAX_CANDIDATES = 24
MAX_SNIPPETS = 3


def make_hole(expr: str) -> str:
    """Mark an unresolvable expression, keeping its text so the report says what is unknown."""
    return f"{HOLE_OPEN}{expr.strip()[:110]}{HOLE_CLOSE}"


def has_hole(url: str) -> bool:
    return HOLE_OPEN in url


def strip_holes(url: str) -> str:
    return HOLE_SPAN_RE.sub("", url)


def normalize_path(path: str) -> str:
    path = path.strip("/")
    if path.startswith("cgi-bin/luci/;stok="):
        path = path.split("/", 3)[-1]
    return path


def parse_url(url: str) -> tuple[str, list[str]] | None:
    """``(module, [form, ...])`` for a resolved endpoint URL, or None if it is not one."""
    index = url.find("form=")
    if index <= 0 or url[index - 1] not in "?&":
        return None
    path = PATH_RUN_RE.search(url[: index - 1])
    if not path or not MODULE_RE.match(path.group(0)):
        return None
    forms = FORM_RE.findall(url[index - 1 :])
    if not forms:
        return None
    return normalize_path(path.group(0)), forms


def payload_operations(text: str, start: int, end: int) -> set[str]:
    """``operation: "x"`` in a request body, and ``FormData.append("operation", "x")``."""
    window = text[start:end]
    return {a or b for a, b in PAYLOAD_OP_RE.findall(window)}


def append_operations(text: str, start: int, end: int) -> set[str]:
    """``FormData.append("operation", "x")`` sits before the ``file()`` call that posts it."""
    window = text[start:end]
    if ".append(" not in window:
        return set()
    return {b for _, b in PAYLOAD_OP_RE.findall(window) if b}


def last_comma_operand(src: str, start: int) -> tuple[int, int]:
    """Span of the final operand of a comma-operator expression, e.g. the URL in ``return a&&x(), url``.

    Minified helpers often build a batch URL this way, so the value a function returns is not the
    first thing after ``return``. The span ends at a top-level ``;`` or at a closer that leaves the
    enclosing block.
    """
    n = len(src)
    parts: list[tuple[int, int]] = []
    depth = 0
    current = start
    j = start
    while j < n:
        c = src[j]
        if c in ("'", '"', "`"):
            j = skip_literal(src, j)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and c == ",":
            parts.append((current, j))
            current = j + 1
        elif depth == 0 and c == ";":
            parts.append((current, j))
            break
        j += 1
    parts.append((current, j))
    for span in reversed(parts):
        if src[span[0] : span[1]].strip():
            start_index, end_index = span
            while start_index < end_index and src[start_index] in " \t\r\n":
                start_index += 1
            return start_index, end_index
    return start, start


def _params(raw: str) -> list[str]:
    return [part.split("=")[0].strip() for part in raw.split(",") if part.strip()]


@dataclass
class Binding:
    name: str
    literal: Literal
    pos: int


@dataclass
class Func:
    name: str
    params: list[str]
    body: str
    body_start: int


@dataclass
class Resolved:
    """Outcome of turning a source expression into URL text."""

    texts: list[str] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)
    shape: str = ""
    batched: bool = False


@dataclass
class Site:
    path: str
    form: str
    shapes: set[str] = field(default_factory=set)
    operations: set[str] = field(default_factory=set)
    chunks: set[str] = field(default_factory=set)
    batched: bool = False
    snippets: list[str] = field(default_factory=list)


@dataclass
class Pattern:
    chunk: str
    path: str | None
    url: str
    shape: str


@dataclass
class Failure:
    chunk: str
    argument: str
    snippet: str


class Bundle:
    """One bundle: its literals, the values bound to its names, and the functions wrapping a URL."""

    def __init__(self, name: str, text: str) -> None:
        self.name = name
        self.text = text
        self.literals: list[Literal] = scan(text)
        self._descend()
        self.by_start: dict[int, Literal] = {}
        for literal in self.literals:
            self.by_start.setdefault(literal.start, literal)
        self.bindings: dict[str, list[Binding]] = defaultdict(list)
        self.form_arrays: dict[str, list[Literal]] = defaultdict(list)
        self.funcs: dict[str, Func] = {}
        self._index()

    def _descend(self) -> None:
        # `scan` records the body of `${...}` but does not descend into it, so nested templates --
        # exactly where batched form names get built -- would stay invisible.
        queue = [literal for literal in self.literals if literal.is_template]
        seen: set[tuple[int, int]] = set()
        while queue:
            literal = queue.pop()
            for part in literal.expressions:
                if (part.start, part.end) in seen:
                    continue
                seen.add((part.start, part.end))
                for inner in scan(part.text):
                    shifted = Literal(
                        inner.quote,
                        inner.start + part.start,
                        inner.end + part.start,
                        [Part(p.kind, p.text, p.start + part.start, p.end + part.start) for p in inner.parts],
                    )
                    self.literals.append(shifted)
                    if shifted.is_template:
                        queue.append(shifted)

    def _index(self) -> None:
        for literal in self.literals:
            head = self.text[max(0, literal.start - 60) : literal.start]
            bound = BOUND_NAME_RE.search(head)
            if bound:
                offset = max(0, literal.start - 60) + bound.start(1)
                name = bound.group(1)
                if bound.group(2) == "+=":
                    merged = self._append_to_binding(name, literal, offset)
                    if merged is not None:
                        continue
                self.bindings[name].append(Binding(name, literal, offset))
            plain = literal.uninterpolated
            if literal.quote != "`" and plain and FORM_STRICT_RE.match(plain):
                array = ARRAY_ASSIGN_RE.search(self.text[max(0, literal.start - 140) : literal.start])
                if array:
                    self.form_arrays[array.group(1)].append(literal)
                    continue
                push = PUSH_RE.search(self.text[max(0, literal.start - 40) : literal.start])
                if push and self.text[literal.start - 1 : literal.start] in ("(", ","):
                    self.form_arrays[push.group(1)].append(literal)
        for match in FUNC_DEF_RE.finditer(self.text):
            _, body = match_braces(self.text, match.end())
            self.funcs.setdefault(match.group(1), Func(match.group(1), _params(match.group(2)), body, match.end()))
        for match in ARROW_DEF_RE.finditer(self.text):
            if self.text[match.end() - 1] == "{":
                _, body = match_braces(self.text, match.end())
            else:
                body = self.text[match.end() : match.end() + 160]
            self.funcs.setdefault(match.group(1), Func(match.group(1), _params(match.group(2)), body, match.end()))

    def _append_to_binding(self, name: str, literal: Literal, offset: int) -> Binding | None:
        """Fold ``s += "..."`` into the binding for ``s`` so an appended form name is not lost."""
        prior = self.value_of(name, offset)
        if prior is None:
            return None
        merged = Literal(prior.quote, prior.start, literal.end, [*prior.parts, *literal.parts])
        binding = Binding(name, merged, offset)
        self.bindings[name].append(binding)
        return binding

    def value_of(self, name: str, pos: int) -> Literal | None:
        """Nearest preceding assignment of ``name``, else its last assignment in the file.

        Minified bundles reuse short names across scopes, so position decides. Hoisted ``function``
        bodies that run after a ``const`` is assigned need the file-wide fallback.
        """
        candidates = self.bindings.get(name)
        if not candidates:
            return None
        positions = [binding.pos for binding in candidates]
        index = bisect_right(positions, pos)
        return candidates[index - 1].literal if index else candidates[-1].literal

    def expand(self, literal: Literal, depth: int) -> Resolved:
        texts = [""]
        variants: list[str] = []
        batched = False
        shapes = {"template" if literal.is_template else "literal"}
        for part in literal.parts:
            if part.kind != EXPR:
                texts = [text + part.text for text in texts]
                continue
            resolved = self.resolve(part.start, part.end, depth + 1)
            variants.extend(resolved.variants)
            batched = batched or resolved.batched
            if resolved.shape:
                shapes.add(resolved.shape)
            additions = resolved.texts or [make_hole(self.text[part.start : part.end])]
            texts = [f"{text}{addition}" for text in texts for addition in additions][:MAX_CANDIDATES]
        return Resolved(texts=texts, variants=variants, shape="+".join(sorted(shapes)), batched=batched)

    def resolve(self, start: int, end: int, depth: int = 0) -> Resolved:
        """Turn the source slice ``[start, end)`` into candidate URL texts."""
        if depth > MAX_DEPTH:
            return Resolved()
        expr = self.text[start:end].strip()
        if not expr:
            return Resolved()
        start = self.text.index(expr, start, end)
        literal = self.by_start.get(start)
        if literal is not None and literal.end <= start + len(expr) + 1 and not self.text[literal.end : end].strip():
            return self.expand(literal, depth)
        joined = JOIN_RE.match(expr)
        if joined:
            return self._resolve_array(joined.group(1), depth)
        if IDENT_RE.match(expr):
            bound = self.value_of(expr, start)
            if bound is not None:
                resolved = self.expand(bound, depth)
                return Resolved(
                    texts=resolved.texts,
                    variants=resolved.variants,
                    shape=f"binding+{resolved.shape}",
                    batched=resolved.batched,
                )
        called = CALL0_RE.match(expr)
        if called:
            return self.returns_url(called.group(1), depth)
        return Resolved()

    def _resolve_array(self, name: str, depth: int) -> Resolved:
        elements = self.form_arrays.get(name, [])
        if not elements:
            return Resolved()
        texts: list[str] = []
        variants: list[str] = []
        for element in elements:
            for text in self.expand(element, depth + 1).texts:
                texts.append(text)
                if FORM_STRICT_RE.match(text):
                    variants.append(text)
        return Resolved(texts=texts, variants=variants, shape="joined-array", batched=True)

    def returns_url(self, name: str, depth: int) -> Resolved:
        """The URL a local helper builds, for call sites like ``e.read(buildUrl())``.

        Every ``return`` in the body is a candidate, and each one's value is its last
        comma-operator operand, which is how minified batch-URL helpers end up written.
        """
        func = self.funcs.get(name)
        if func is None or depth > MAX_DEPTH:
            return Resolved()
        texts: list[str] = []
        variants: list[str] = []
        shapes: set[str] = set()
        batched = False
        for match in RETURN_RE.finditer(func.body):
            start, end = last_comma_operand(self.text, func.body_start + match.end())
            resolved = self.resolve(start, end, depth + 1)
            texts.extend(resolved.texts)
            variants.extend(resolved.variants)
            batched = batched or resolved.batched
            if resolved.shape:
                shapes.add(resolved.shape)
        clean = [text for text in texts if not has_hole(text)]
        return Resolved(
            texts=clean,
            variants=variants,
            shape=f"function-return+{'+'.join(sorted(shapes))}",
            batched=batched,
        )

    def wrapper_operations(self) -> dict[str, dict[int, set[str]]]:
        """Local helpers like ``function i(e){return t.request(e,{operation:"read_spf"},r)}``.

        They forward a URL their caller passed in, so ``i(`${n}_2g`)`` is a request against that URL.
        Without this, whole families of per-band forms never appear at a resolvable call site.
        """
        wrappers: dict[str, dict[int, set[str]]] = {}
        for name, func in self.funcs.items():
            by_param: dict[int, set[str]] = defaultdict(set)
            for match in METHOD_CALL_RE.finditer(func.body):
                close, arguments = call_span(func.body, match.end())
                if not arguments:
                    continue
                first = func.body[arguments[0][0] : arguments[0][1]].strip()
                if first not in func.params:
                    continue
                index = func.params.index(first)
                absolute = func.body_start + match.end()
                by_param[index] |= {match.group(1)} | payload_operations(self.text, absolute, func.body_start + close)
            if by_param:
                wrappers[name] = dict(by_param)
        return wrappers


def emit(
    sites: dict[tuple[str, str], Site],
    path: str,
    form: str,
    chunk: str,
    shape: str,
    operations: set[str],
    snippet: str,
    batched: bool,
) -> None:
    site = sites.setdefault((path, form), Site(path=path, form=form))
    site.shapes.add(shape)
    site.operations |= operations
    site.chunks.add(chunk)
    site.batched = site.batched or batched
    if snippet and len(site.snippets) < MAX_SNIPPETS and snippet not in site.snippets:
        site.snippets.append(snippet)


def record_urls(
    bundle: Bundle,
    texts: list[str],
    shape: str,
    operations: set[str],
    snippet: str,
    sites: dict[tuple[str, str], Site],
    patterns: dict[tuple[str, str], Pattern],
    batched: bool = False,
) -> None:
    for url in texts:
        if has_hole(url):
            add_pattern(bundle, url, shape, patterns)
            continue
        parsed = parse_url(url)
        if not parsed:
            continue
        path, forms = parsed
        for form in forms:
            emit(sites, path, form, bundle.name, shape, operations, snippet, batched or len(forms) > 1)


def add_pattern(bundle: Bundle, url: str, shape: str, patterns: dict[tuple[str, str], Pattern]) -> None:
    """Keep the URL expressions the resolver could not pin down, so gaps stay visible."""
    if "form=" not in url and "form=" not in strip_holes(url):
        return
    hole_index = url.find(HOLE_OPEN)
    index = url.find("form=")
    cut = hole_index if hole_index >= 0 and (index < 0 or index > hole_index) else max(index - 1, 0)
    path_run = PATH_RUN_RE.search(url[:cut])
    raw = path_run.group(0) if path_run else ""
    path = normalize_path(raw) if MODULE_RE.match(raw) else None
    patterns[(bundle.name, url)] = Pattern(bundle.name, path, url, shape)


def call_sites(
    bundle: Bundle,
    sites: dict[tuple[str, str], Site],
    patterns: dict[tuple[str, str], Pattern],
    failures: list[Failure],
) -> None:
    operations_by_callee = bundle.wrapper_operations()
    method_positions = [(m.start(1), m.end(), {m.group(1)}) for m in METHOD_CALL_RE.finditer(bundle.text)]
    wrapper_positions = [
        (m.start(1), m.end(), m.group(1)) for m in ANY_CALL_RE.finditer(bundle.text) if m.group(1) in operations_by_callee
    ]
    for position, open_index, method in method_positions:
        close, arguments = call_span(bundle.text, open_index)
        if arguments:
            record_argument(bundle, sites, patterns, failures, position, arguments[0], method, open_index, close)
    for position, open_index, name in wrapper_positions:
        close, arguments = call_span(bundle.text, open_index)
        for index, operations in operations_by_callee[name].items():
            if index < len(arguments):
                record_argument(bundle, sites, patterns, failures, position, arguments[index], operations, open_index, close)


def record_argument(
    bundle: Bundle,
    sites: dict[tuple[str, str], Site],
    patterns: dict[tuple[str, str], Pattern],
    failures: list[Failure],
    position: int,
    argument: tuple[int, int],
    operations: set[str],
    open_index: int,
    close_index: int,
) -> None:
    start, end = argument
    text = bundle.text[start:end].strip()
    if not text:
        return
    resolved = bundle.resolve(start, end)
    snippet = bundle.text[max(0, position - 24) : min(len(bundle.text), close_index + 1)]
    # A form's verb is the helper method, a payload `operation: "x"`, or -- for a `file()` upload --
    # a FormData append sitting just before the call.
    ops = set(operations) | payload_operations(bundle.text, open_index, close_index)
    if "file" in operations:
        ops |= append_operations(bundle.text, max(0, position - 260), position)
    if not resolved.texts:
        probe = text
        if IDENT_RE.match(text):
            bound = bundle.value_of(text, start)
            if bound is not None:
                probe = bundle.text[bound.start : bound.end]
        if "form=" in text or "form=" in probe:
            failures.append(Failure(bundle.name, text[:90], snippet[:200]))
        return
    record_urls(bundle, resolved.texts, resolved.shape, ops, snippet, sites, patterns, resolved.batched)


def literal_sites(bundle: Bundle, sites: dict[tuple[str, str], Site], patterns: dict[tuple[str, str], Pattern]) -> None:
    """URLs that exist as strings but whose call site could not be attributed."""
    for literal in bundle.literals:
        resolved = bundle.expand(literal, 0)
        record_urls(bundle, resolved.texts, f"string:{resolved.shape}", set(), "", sites, patterns, resolved.batched)


def scan_bundles(directory: str) -> Report:
    names = sorted(name for name in os.listdir(directory) if name.endswith(".js"))
    sites: dict[tuple[str, str], Site] = {}
    patterns: dict[tuple[str, str], Pattern] = {}
    failures: list[Failure] = []
    for name in names:
        with open(os.path.join(directory, name), encoding="utf-8", errors="replace") as handle:
            bundle = Bundle(name, handle.read())
        call_sites(bundle, sites, patterns, failures)
        literal_sites(bundle, sites, patterns)
    forms: dict[str, dict[str, Site]] = defaultdict(dict)
    for (path, form), site in sites.items():
        forms[path][form] = site
    return Report(len(names), forms, patterns, failures)


@dataclass
class Report:
    files_scanned: int
    forms: dict[str, dict[str, Site]]
    patterns: dict[tuple[str, str], Pattern]
    failures: list[Failure]

    @property
    def module_count(self) -> int:
        return len(self.forms)

    @property
    def form_count(self) -> int:
        return sum(len(module) for module in self.forms.values())

    def has(self, module: str, form: str) -> bool:
        return form in self.forms.get(module, {})

    def to_json(self) -> dict[str, Any]:
        modules: dict[str, dict[str, Any]] = {}
        for path in sorted(self.forms):
            entries: dict[str, Any] = {}
            for form in sorted(self.forms[path]):
                site = self.forms[path][form]
                entries[form] = {
                    "operations": sorted(site.operations) or ["not observed"],
                    "shapes": sorted(site.shapes),
                    "batched": site.batched,
                    "chunks": sorted(site.chunks)[:4],
                    "evidence": [re.sub(r"\s+", " ", snippet)[:200] for snippet in site.snippets],
                }
            modules[path] = entries
        return {
            "files_scanned": self.files_scanned,
            "counts": {
                "modules": self.module_count,
                "forms": self.form_count,
                "patterns": len(self.patterns),
                "unresolved": len(self.failures),
            },
            "modules": modules,
            "dynamic_patterns": [
                {"chunk": pattern.chunk, "module": pattern.path, "url": pattern.url, "shape": pattern.shape}
                for pattern in sorted(self.patterns.values(), key=lambda p: (p.path or "", p.url))
            ],
            "unresolved_calls": [
                {"chunk": failure.chunk, "argument": failure.argument, "snippet": failure.snippet}
                for failure in self.failures
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles", default=".cache/ax12-ui/bundles")
    parser.add_argument("--out", default=".cache/ax12-ui/inventory-v2.json")
    parser.add_argument("--expect", default="", help="comma-separated module:form pairs that must be found")
    args = parser.parse_args()

    report = scan_bundles(args.bundles)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report.to_json(), handle, indent=1)

    print(f"{report.module_count} modules / {report.form_count} forms from {report.files_scanned} bundles")
    print(f"{len(report.patterns)} dynamic URL patterns, {len(report.failures)} unresolvable call arguments")
    print(f"report: {args.out}")
    for path in sorted(report.forms):
        print(f"\n/{path}  ({len(report.forms[path])})")
        print("   " + ", ".join(sorted(report.forms[path])))
    if args.expect:
        missing = []
        for pair in args.expect.split(","):
            module, _, form = pair.partition(":")
            if not report.has(module.strip("/"), form.strip()):
                missing.append(pair.strip())
        if missing:
            print("\nMISSING (expected but not extracted): " + ", ".join(missing))
            return 1
        print("\nall expected forms found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
