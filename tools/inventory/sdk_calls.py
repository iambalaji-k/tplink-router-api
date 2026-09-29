"""Static scan of the endpoints this package's own code addresses.

The bundle inventory says what the router's UI can ask for. It cannot say what *this SDK* asks for,
and the two sets differ: `admin/wireless?form=statistics` is answered by the firmware and used by
`wifi.statistics()`, yet appears nowhere in the bundles. Feeding these call sites to the live probe
means such forms are verified instead of inherited from an earlier session's notes, and a test can
fail when a call site addresses a form nobody has confirmed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

STRING_ARG = r"(?:f?\"(?:[^\"{}]|\{[^}]*\})*\")"
CALL_RE = re.compile(
    r"\.(?P<method>read|write|api)\(\s*(?P<module>\"[a-z0-9_/]+\"|PATH)\s*,\s*(?P<form>" + STRING_ARG + r"|[a-z_][a-z0-9_]*)",
    re.S,
)
VERB_RE = re.compile(
    r"\.(?:read|write|api)\(\s*(?:\"[a-z0-9_/]+\"|PATH)\s*,\s*(?:" + STRING_ARG + r"|[a-z_][a-z0-9_]*)\s*,\s*\"([a-z_]+)\""
)
PATH_ASSIGN_RE = re.compile(r'^PATH\s*=\s*"([a-z0-9_/]+)"', re.M)
BRACE_RE = re.compile(r"\{[^}]*\}")


@dataclass(frozen=True)
class CallSite:
    """One request this package can make.

    `prefix`/`suffix` are the fixed parts of the form name; an empty pair means the name arrives as
    a variable, so only the module is pinned.
    """

    module: str
    prefix: str
    suffix: str
    verb: str
    source: Path

    @property
    def is_literal(self) -> bool:
        return bool(self.prefix) and self.prefix == self.suffix

    def matches(self, module: str, form: str) -> bool:
        return module == self.module and form.startswith(self.prefix) and form.endswith(self.suffix)


def form_pattern(arg: str) -> tuple[str, str]:
    """`(prefix, suffix)` a form argument can match.

    A literal is pinned exactly. An f-string is pinned to what is written around its interpolation,
    which still catches a wrong merged-view form name. A bare identifier pins nothing: the helper
    receiving it is called with a literal elsewhere in the same file.
    """
    if not arg.startswith(('"', 'f"')):
        return "", ""
    body = arg[1:] if arg.startswith("f") else arg
    body = body.strip('"')
    parts = BRACE_RE.split(body)
    if len(parts) == 1:
        return body, body
    return parts[0], parts[-1]


def call_sites(package_dir: Path, app_module: Path) -> list[CallSite]:
    """Every `client.read(...)` / `client.write(...)` / `client.api(...)` in the shipped code."""
    files = sorted(package_dir.rglob("*.py"))
    if app_module.is_file():
        files.append(app_module)
    found: list[CallSite] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        declared = PATH_ASSIGN_RE.findall(text)
        default_path = declared[0] if declared else ""
        verbs = [(m.start(), m.group(1)) for m in VERB_RE.finditer(text)]
        for match in CALL_RE.finditer(text):
            raw_module = match.group("module")
            module = default_path if raw_module == "PATH" else raw_module.strip('"')
            if not module:
                continue
            verb = match.group("method")
            if verb == "api":
                verb = next((v for position, v in verbs if position >= match.start()), "read")
            elif verb == "write":
                verb = "write"
            else:
                verb = "read"
            prefix, suffix = form_pattern(match.group("form"))
            found.append(CallSite(module=module, prefix=prefix, suffix=suffix, verb=verb, source=path))
    return found
