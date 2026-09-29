"""Recover row-form field names from the UI's own table and form models.

An empty list form answers `{}` -- the router only reveals a row's fields when rows exist, and
creating one to find out would be a write. The UI has to know the field names anyway to render the
table and validate the add-row form, so they are readable in the page's bundle:

* column definitions: ``{text: t("portForwarding.internalPort"), value: "internalPort"}``
* form defaults: ``{key: o, name: "", ip: "", externalPort: "", protocol: p.All, enable: !0}``

Everything this tool reports is labelled as an inference from the UI, never as a router response.

    venv/Scripts/python.exe -m tools.inventory.form_models \
        --bundles .cache/ax12-ui/bundles --inventory .cache/ax12-ui/inventory-v2.json \
        --routes .cache/ax12-ui/ui-routes.json --probe .cache/ax12-ui/live-probe.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import Any

COLUMN_RE = re.compile(r'\{[^{}]{0,120}?text:[^{}]{0,120}?value:"([A-Za-z][A-Za-z0-9_]{1,24})"')
DEFAULT_ROW_RE = re.compile(r"\{[^{}]{0,600}?\}")

# A row default mixes strings, minified booleans (`!0` / `!1`), numbers and enum references
# (`p.All`); anything else in the literal is not a scalar field.
KEY_RE = re.compile(
    r'([A-Za-z][A-Za-z0-9_]{1,24})\s*:\s*(?:true|false|null|"[^"]*"|!?[01]|-?\d+|'
    r"[A-Za-z$_][\w$]*(?:\.[A-Za-z$_][\w$]*)?)"
)

# Table metadata keys rather than row fields. `name`, `key` and `type` stay out of this list on
# purpose: they are real fields on rows the router does return.
SKIP_KEYS = frozenset({"text", "value", "label", "class", "style", "width", "default", "optional", "required"})


def read_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def is_empty_row_shape(schema: dict[str, Any] | None) -> bool:
    """An answered form carrying no rows -- `{}` or `[]` -- so nothing here describes a row."""
    if not schema:
        return False
    if schema.get("type") == "object":
        return not schema.get("keys")
    if schema.get("type") == "array":
        return schema.get("length") == 0
    return False


def bundle_text(directory: str, component: str) -> str:
    """Source of a route component, addressed as `./index-x.js`, under the crawler's flat naming."""
    basename = os.path.basename(component)
    for name in os.listdir(directory):
        if name.endswith(f"__{basename}") or name == basename:
            with open(os.path.join(directory, name), encoding="utf-8", errors="replace") as handle:
                return handle.read()
    return ""


def empty_row_forms(inventory: dict[str, Any], probe: dict[str, Any]) -> dict[str, str]:
    """Forms the router answered but that hold no rows here, keyed `module?form=x` -> module."""
    verdicts = {f"{p['module']}?form={p['form']}": p for p in probe["probes"]}
    out: dict[str, str] = {}
    for module, forms in inventory["modules"].items():
        for form in forms:
            key = f"{module}?form={form}"
            record = verdicts.get(key)
            if record is not None and record["verdict"] == "answered" and is_empty_row_shape(record["data_schema"]):
                out[key] = module
    return out


def columns_of(text: str) -> set[str]:
    """The `value:` keys a table declares, e.g. `internalPort` in a port-forwarding column."""
    return {match.group(1) for match in COLUMN_RE.finditer(text)}


def default_rows_of(text: str) -> list[set[str]]:
    """Object literals that look like a form's initial row: several keys, scalar values only."""
    rows: list[set[str]] = []
    seen: set[frozenset[str]] = set()
    for match in DEFAULT_ROW_RE.finditer(text):
        body = match.group(0)
        if body.count(':"') < 2 or "operation" in body:
            continue
        keys = {key for key in KEY_RE.findall(body) if key not in SKIP_KEYS}
        if len(keys) >= 4 and not (keys & {"text", "label", "width"}) and frozenset(keys) not in seen:
            seen.add(frozenset(keys))
            rows.append(keys)
    return rows


@dataclass
class Candidate:
    """One page's initial-row literal, scored by how many of its fields the page also shows as columns."""

    page: str
    component: str
    fields: list[str]
    matched_columns: list[str]

    @property
    def score(self) -> int:
        return len(self.matched_columns)


def row_candidates(directory: str, pages: list[tuple[str, str]]) -> list[Candidate]:
    """Every plausible initial row across the pages that can reach one form."""
    candidates: list[Candidate] = []
    for page_name, component in pages:
        text = bundle_text(directory, component)
        if not text:
            continue
        columns = columns_of(text)
        for fields in default_rows_of(text):
            candidates.append(
                Candidate(
                    page=page_name,
                    component=os.path.basename(component),
                    fields=sorted(fields),
                    matched_columns=sorted(fields & columns),
                )
            )
    candidates.sort(key=lambda c: (-c.score, c.page))
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundles", default=".cache/ax12-ui/bundles")
    parser.add_argument("--inventory", default=".cache/ax12-ui/inventory-v2.json")
    parser.add_argument("--routes", default=".cache/ax12-ui/ui-routes.json")
    parser.add_argument("--probe", default=".cache/ax12-ui/live-probe.json")
    parser.add_argument("--out", default=".cache/ax12-ui/form-models.json")
    args = parser.parse_args()

    inventory = read_json(args.inventory)
    probe = read_json(args.probe)
    routes = read_json(args.routes)
    forms_without_rows = empty_row_forms(inventory, probe)

    # A form appears on several pages once imports are followed, so keep the page whose name the
    # router table gave it, and rank the rest by how well their row literal matches their columns.
    pages_for_form: dict[str, list[tuple[str, str]]] = {}
    for page in routes["pages"]:
        for form in page["forms"]:
            pages_for_form.setdefault(form, []).append((page["name"], page["component"]))

    report: dict[str, Any] = {"note": "inferred from the UI's own form/table model; never returned by the router",
                              "forms": {}}
    for key in sorted(forms_without_rows):
        pages = sorted(set(pages_for_form.get(key, [])), key=lambda p: p[0])
        candidates = row_candidates(args.bundles, pages)
        report["forms"][key] = {
            "ui_pages": [name for name, _ in pages],
            "candidates": [
                {
                    "page": c.page,
                    "component": c.component,
                    "fields": c.fields,
                    "matched_columns": c.matched_columns,
                }
                for c in candidates[:3]
            ],
        }

    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)

    print(f"{len(forms_without_rows)} answered row forms hold no rows on this unit")
    for key, entry in report["forms"].items():
        print(f"\n{key}   pages: {', '.join(entry['ui_pages']) or '-'}")
        if not entry["candidates"]:
            print("   no row literal recovered")
        for candidate in entry["candidates"][:2]:
            print(f"   [{candidate['page']}] {len(candidate['matched_columns'])}/{len(candidate['fields'])} in columns:")
            print(f"      {', '.join(candidate['fields'])}")
    print(f"\nreport: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
