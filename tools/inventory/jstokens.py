"""A small JavaScript literal scanner, enough to recover string and template literals from minified bundles.

The router UI ships minified ESM where endpoint URLs are built with template literals and
``Array.join("&")`` rather than plain ``"..."`` strings, so a regex over quoted literals
under-counts endpoints. This module tokenizes literals the way a parser would: it tracks
``${...}`` interpolation, treats nested templates as their own sites, and skips over nested
literals when matching a closing brace.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TEXT = "text"
EXPR = "expr"


@dataclass
class Part:
    """One piece of a literal: either raw text or the body of a ``${...}`` interpolation."""

    kind: str
    text: str
    start: int
    end: int


@dataclass
class Literal:
    quote: str
    start: int
    end: int
    parts: list[Part] = field(default_factory=list)

    @property
    def is_template(self) -> bool:
        return self.quote == "`"

    @property
    def uninterpolated(self) -> str:
        """The literal's text, or empty when it interpolates anything."""
        if any(part.kind == EXPR for part in self.parts):
            return ""
        return "".join(part.text for part in self.parts)

    @property
    def expressions(self) -> list[Part]:
        return [part for part in self.parts if part.kind == EXPR]


def _scan_quoted(src: str, i: int, quote: str) -> int:
    """Index just past a `'` or `"` literal that starts at `i`."""
    n = len(src)
    j = i + 1
    while j < n:
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == quote:
            return j + 1
        j += 1
    return n


def _scan_template(src: str, i: int, parts: list[Part]) -> int:
    """Tokenize the backtick literal at `i` into `parts`; return the index just past it."""
    n = len(src)
    j = i + 1
    seg_start = j
    seg: list[str] = []

    def flush(end: int) -> None:
        if seg:
            parts.append(Part(TEXT, "".join(seg), seg_start, end))
            seg.clear()

    while j < n:
        c = src[j]
        if c == "\\":
            seg.append(src[j : j + 2])
            j += 2
            continue
        if c == "`":
            flush(j)
            return j + 1
        if c == "$" and j + 1 < n and src[j + 1] == "{":
            flush(j)
            body_start = j + 2
            close, body = _scan_expression(src, body_start)
            parts.append(Part(EXPR, body, body_start, close))
            j = close + 1
            seg_start = j
            continue
        seg.append(c)
        j += 1
    flush(n)
    return n


def _scan_expression(src: str, j: int) -> tuple[int, str]:
    """Scan a ``${...}`` body from its first character; return (index of `}`, body text)."""
    n = len(src)
    depth = 1
    k = j
    while k < n:
        c = src[k]
        if c in ("'", '"'):
            k = _scan_quoted(src, k, c)
            continue
        if c == "`":
            k = _scan_template(src, k, [])
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return k, src[j:k]
        k += 1
    return n, src[j:n]


def skip_literal(src: str, i: int) -> int:
    """Index just past the literal that starts at `i`, whatever the quote style."""
    c = src[i]
    if c in ("'", '"'):
        return _scan_quoted(src, i, c)
    if c == "`":
        return _scan_template(src, i, [])
    return i + 1


def match_braces(src: str, open_index: int) -> tuple[int, str]:
    """Body of the `{...}` block whose `{` sits at `open_index - 1`, plus the index of its `}`."""
    return _match(src, open_index, "{", "}")


def match_array(src: str, open_index: int) -> tuple[int, str]:
    """Body of the `[...]` array whose `[` sits at `open_index - 1`, plus the index of its `]`."""
    return _match(src, open_index, "[", "]")


def call_span(src: str, open_index: int) -> tuple[int, list[tuple[int, int]]]:
    """`(closing index, [(start, end) per argument])` of the call whose `(` sits at `open_index - 1`.

    Nesting is respected and nested literals are skipped, so a `,` inside a payload object or a
    template body does not split the argument list.
    """
    n = len(src)
    args: list[tuple[int, int]] = []
    start = open_index
    depth = 0
    j = open_index
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
        elif c == "," and depth == 0:
            args.append((start, j))
            start = j + 1
        j += 1
    if src[start:j].strip():
        args.append((start, j))
    return j, args


def _match(src: str, open_index: int, opener: str, closer: str) -> tuple[int, str]:
    n = len(src)
    depth = 1
    j = open_index
    while j < n:
        c = src[j]
        if c in ("'", '"', "`"):
            j = skip_literal(src, j)
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return j, src[open_index:j]
        j += 1
    return n, src[open_index:n]


def scan(src: str) -> list[Literal]:
    """Every string and template literal in `src`, in source order."""
    literals: list[Literal] = []
    n = len(src)
    i = 0
    while i < n:
        c = src[i]
        if c in ("'", '"'):
            end = _scan_quoted(src, i, c)
            body = src[i + 1 : max(i + 1, end - 1)]
            literals.append(Literal(c, i, end, [Part(TEXT, body, i + 1, end - 1)]))
            i = end
            continue
        if c == "`":
            parts: list[Part] = []
            end = _scan_template(src, i, parts)
            literals.append(Literal("`", i, end, parts))
            i = end
            continue
        i += 1
    return literals
