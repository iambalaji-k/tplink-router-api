"""Live-probe the inventoried forms against a real Archer AX12, with read/load/list only.

Static analysis says which URLs the UI builds; only the router says which ones *this* firmware
answers, and what comes back. For every `(module, form)` in the bundle inventory this tool sends
`operation=read`, `load` or `list` -- nothing else, enforced by an assertion on every request -- and
records the verdict plus the response schema: field names, types, a masked sample, and the `others`
sibling that sits beside `data` rather than inside it.

Three safety rules are built in:

* only `read`, `load` and `list` are ever sent; no `write`, `insert`, `update`, `remove`, `go`,
  `reboot`, `upgrade`, `block`, `wakeup`, `connect`, `disconnect`, and no bespoke verbs such as
  the wireless module's `read_spf` (they are recorded as "not probed" instead);
* forms whose *name* is itself an action (`reboot`, `logout`, `cloud_upgrade`, `quick_setup`, ...)
  are skipped, because a CGI that acts on any POST would be the one thing a read-only sweep could
  not take back;
* values for keys matching `psk|passwd|password|key|pin|private` are never recorded or printed.

Logging in evicts the router's previous stok -- the admin page and this tool share one session.

    venv/Scripts/python.exe -m tools.inventory.probe_live --inventory .cache/ax12-ui/inventory-v2.json
    venv/Scripts/python.exe -m tools.inventory.probe_live --only nat --limit 20   # smoke test first
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from tools.inventory.sdk_calls import call_sites
from tplink_modern import ArcherAX12
from tplink_modern.exceptions import RouterError

SAFE_OPERATIONS = ("read", "load", "list")

# Verbs the UI uses that this sweep will not send, so the report can say so honestly.
UNPROBED_VERBS = ("read_spf", "write_spf", "read_match", "read_max", "get", "set", "go", "check", "request")

SECRET_RE = re.compile(r"psk|passwd|password|key|pin|private", re.I)

# Action-shaped names: reading one of these is the one thing that could reboot, flash or log out.
ACTION_FORM_RE = re.compile(
    r"^(reboot|logout|upgrade|factory.*|reset.*|cloud_upgrade|save_upgrade|config_multipart|slave_cmd|"
    r"search_slave|quick_setup|ap_setup|save_log|auto_upgrade|openvpn_cert)$"
)

MAX_DEPTH = 4
MAX_SAMPLE = 48


def load_env_file(path: str = ".env") -> None:
    """Read `KEY=value` lines from the repo's .env into os.environ without printing values."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def schema_of(value: Any, key: str = "", depth: int = 0) -> dict[str, Any]:
    """Type-and-name view of a response value, with secrets reduced to their type."""
    if SECRET_RE.search(key):
        return {"type": type_name(value), "sample": "***masked***"}
    if isinstance(value, dict):
        if depth >= MAX_DEPTH:
            return {"type": "object", "keys": "..."}
        return {"type": "object", "keys": {k: schema_of(value[k], k, depth + 1) for k in sorted(value)}}
    if isinstance(value, list):
        node: dict[str, Any] = {"type": "array", "length": len(value)}
        if value:
            node["item"] = schema_of(value[0], key, depth + 1)
        return node
    if isinstance(value, (str, int, float, bool)) or value is None:
        node = {"type": type_name(value)}
        if isinstance(value, str):
            node["sample"] = value[:MAX_SAMPLE]
        elif value is not None:
            node["sample"] = value
        return node
    return {"type": type_name(value)}


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def summarize(node: Any, indent: int = 0) -> list[str]:
    """Human-readable `name: type = sample` lines for a schema tree."""
    lines: list[str] = []
    if isinstance(node, dict) and node.get("type") == "object":
        keys = node.get("keys")
        if isinstance(keys, str):
            return [f"{'  ' * indent}(truncated)"]
        for key, child in (keys or {}).items():
            lines.append(f"{'  ' * indent}{key}: {child.get('type')}{suffix(child)}")
            lines.extend(summarize(child, indent + 1))
    elif isinstance(node, dict) and node.get("type") == "array":
        item = node.get("item")
        lines.append(f"{'  ' * indent}[{node.get('length')}]" + (" of:" if item else ""))
        if item:
            lines.extend(summarize(item, indent + 1))
    return lines


def suffix(node: dict[str, Any]) -> str:
    sample = node.get("sample")
    if sample is None:
        return ""
    text = str(sample).replace("\n", " ")
    return f" = {text[:MAX_SAMPLE]}" if text else ""


@dataclass
class Probe:
    module: str
    form: str
    observed: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    answered_by: list[str] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)
    schemas: dict[str, dict[str, Any]] = field(default_factory=dict)
    verdict: str = "not probed"
    reason: str = ""
    top_level_keys: list[str] = field(default_factory=list)
    data: dict[str, Any] | None = None
    others: dict[str, Any] | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "form": self.form,
            "observed_in_ui": self.observed,
            "verdict": self.verdict,
            "reason": self.reason,
            "answered_by": self.answered_by,
            "failures": self.failures,
            "attempts": self.attempts,
            "top_level_keys": self.top_level_keys,
            "data_schema": self.data,
            "others_schema": self.others,
            "schema_by_operation": self.schemas,
        }

    def settle(self) -> None:
        """Answered wins over a later failed verb; a form is only rejected if nothing answered."""
        if self.answered_by:
            self.verdict = "answered"
            self.reason = "; ".join(f"{op}: {why}" for op, why in self.failures.items())
            return
        if self.failures:
            self.verdict = "transport error" if any(why.startswith("HTTP") for why in self.failures.values()) else "rejected"
            self.reason = "; ".join(f"{op}: {why}" for op, why in self.failures.items())


def operations_to_try(observed: list[str]) -> list[str]:
    """Approved verbs only, preferring the ones the UI itself uses, and `load`/`list` before `read`."""
    approved = [op for op in observed if op in SAFE_OPERATIONS]
    rest = [op for op in SAFE_OPERATIONS if op not in approved]
    preferred = [op for op in approved + rest if op in ("load", "list")]
    remaining = [op for op in approved + rest if op not in preferred]
    seen: list[str] = []
    for op in preferred + remaining:
        if op not in seen:
            seen.append(op)
    return seen


def is_action_shaped(form: str) -> bool:
    return bool(ACTION_FORM_RE.match(form))


ANSWERED = "answered"
NOT_IMPLEMENTED = "not-implemented"
NEEDS_PARAMETERS = "exists-needs-parameters"
NON_JSON = "non-json-or-server-error"
NOT_SERVED = "not-served-404"
NOT_PROBED = "not-probed"


def verdict_category(record: dict[str, Any]) -> str:
    """One category per probed form, so a generated table cannot drift from the report.

    `no such callback` for every approved verb means this firmware has no handler. Anything else
    it refuses with (`invalid proto_name`, `invalid parameter vpntype`) means it *does* have one and
    wants something this read-only sweep will not guess at.
    """
    if record["verdict"] == "skipped":
        return NOT_PROBED
    if record["verdict"] == "answered":
        return ANSWERED
    codes = list(record["failures"].values())
    if not codes:
        return NOT_PROBED
    if all(code.startswith("HTTP 404") for code in codes):
        return NOT_SERVED
    if all(code == "no such callback" for code in codes):
        return NOT_IMPLEMENTED
    if any(code.startswith("HTTP") or "JSONDecode" in code or "transport" in code for code in codes):
        return NON_JSON
    return NEEDS_PARAMETERS


def describe(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data")
    view: dict[str, Any] = {
        "top_level_keys": sorted(key for key in response if key not in ("success", "data")),
        "data": schema_of(data, "data"),
    }
    if isinstance(response.get("others"), (dict, list)) or "others" in response:
        view["others"] = schema_of(response.get("others"), "others")
    elif isinstance(data, dict) and "others" in data:
        view["others"] = schema_of(data["others"], "others")
    return view


async def probe(router: ArcherAX12, module: str, form: str, observed: list[str], delay: float) -> Probe:
    record = Probe(module=module, form=form, observed=observed)
    if is_action_shaped(form):
        record.verdict = "skipped"
        record.reason = "form name is an action; not probed even with a read verb"
        return record

    # Every approved verb is tried, not just the first to answer: `read` and `load` describe a row
    # form differently, and "which of the three does this firmware accept" is the answer the
    # inventory has to state.
    for op in operations_to_try(observed):
        if op not in SAFE_OPERATIONS:
            raise RuntimeError(f"refusing to send operation={op} to {module}?form={form}")
        try:
            response = await router.api(module, form, op)
        except RouterError as error:
            code = getattr(error, "errorcode", None)
            record.attempts.append({"operation": op, "ok": False, "errorcode": code})
            record.failures[op] = str(code) if code is not None else str(error)
            continue
        except httpx.HTTPStatusError as error:
            record.attempts.append({"operation": op, "ok": False, "status": error.response.status_code})
            record.failures[op] = f"HTTP {error.response.status_code}"
            continue
        except (httpx.HTTPError, json.JSONDecodeError) as error:  # a CGI that hangs up or answers non-JSON
            record.attempts.append({"operation": op, "ok": False, "error": type(error).__name__})
            record.failures[op] = f"transport: {type(error).__name__}"
            continue

        view = describe(response)
        record.attempts.append({"operation": op, "ok": True})
        record.answered_by.append(op)
        record.schemas[op] = view
        if record.data is None:
            record.top_level_keys = view["top_level_keys"]
            record.data = view["data"]
            record.others = view.get("others")
        await asyncio.sleep(delay)

    record.settle()
    await asyncio.sleep(delay)
    return record


async def run(args: argparse.Namespace) -> int:
    load_env_file()
    host = os.environ.get("TPLINK_HOST", args.host)
    password = os.environ.get("TPLINK_PASSWORD", "")
    if not password:
        print("TPLINK_PASSWORD is not set; cannot probe.", file=sys.stderr)
        return 2

    with open(args.inventory, encoding="utf-8") as handle:
        inventory: dict[str, Any] = json.load(handle)

    targets: list[tuple[str, str, list[str]]] = []
    for module in sorted(inventory["modules"]):
        if args.only and args.only not in module:
            continue
        for form in sorted(inventory["modules"][module]):
            info = inventory["modules"][module][form]
            observed = [op for op in info["operations"] if op != "not observed"]
            targets.append((module, form, observed))

    # Forms this package itself addresses but the bundles never name. Without this they would carry
    # forward as folklore from an earlier session instead of being re-verified.
    known = {(module, form) for module, form, _ in targets}
    root = Path(__file__).resolve().parents[2]
    for site in call_sites(root / "tplink_modern", root / "app.py"):
        if site.is_literal and (site.module, site.prefix) not in known:
            known.add((site.module, site.prefix))
            targets.append((site.module, site.prefix, []))
    if args.limit:
        targets = targets[: args.limit]

    print(f"probing {len(targets)} forms against {host} with read/load/list only")
    router = ArcherAX12(host=host, password=password)
    await router.login()

    probes: list[Probe] = []
    try:
        for index, (module, form, observed) in enumerate(targets, start=1):
            probe_record = await probe(router, module, form, observed, args.delay)
            probes.append(probe_record)
            mark = {"answered": "OK  ", "rejected": "NO  ", "skipped": "SKIP", "transport error": "ERR "}.get(
                probe_record.verdict, "??  "
            )
            detail = f"via {'+'.join(probe_record.answered_by)}" if probe_record.answered_by else probe_record.reason
            if probe_record.answered_by and probe_record.failures:
                detail += f"  (also failed: {probe_record.reason[:60]})"
            print(f"{mark} {module}?form={form:<28} {detail[:96]}")
            if index % 25 == 0:
                print(f"   ... {index}/{len(targets)}")
    finally:
        await router.close()

    report: dict[str, Any] = {
        "firmware_note": "read/load/list only; values masked",
        "counts": {
            "probed": len(probes),
            "answered": sum(1 for p in probes if p.verdict == "answered"),
            "rejected": sum(1 for p in probes if p.verdict == "rejected"),
            "skipped": sum(1 for p in probes if p.verdict == "skipped"),
            "transport_error": sum(1 for p in probes if p.verdict == "transport error"),
            "with_others": sum(1 for p in probes if p.others is not None),
        },
        "probes": [p.as_json() for p in probes],
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)

    counts = report["counts"]
    print(f"\n{counts['answered']} answered, {counts['rejected']} rejected, {counts['skipped']} skipped, "
          f"{counts['transport_error']} transport errors; {counts['with_others']} carried an `others` sibling")
    print(f"report: {args.out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default=".cache/ax12-ui/inventory-v2.json")
    parser.add_argument("--out", default=".cache/ax12-ui/live-probe.json")
    parser.add_argument("--host", default="192.168.0.1")
    parser.add_argument("--only", default="", help="probe only modules containing this substring")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many forms")
    parser.add_argument("--delay", type=float, default=0.05, help="seconds between requests")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
