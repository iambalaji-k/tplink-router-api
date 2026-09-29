"""Regression tests for the bundle scanner.

These pin the URL shapes that the first inventory scan missed: the newer AX12 bundles build
endpoint URLs with template literals, appended query parameters and `Array.join("&")` batches
instead of writing them out as plain strings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.inventory.extract_ui_inventory import scan_bundles

BUNDLES: dict[str, str] = {
    "guest-network.js": """
        import { s as e } from "./update-store.js";
        const n = "/admin/wireless?";
        function s() {
            const { deviceConfig: t } = a(), { isTriBand: r, supportWifi6E: u } = t;
            const o = ["form=guest_2g", "form=guest_5g", "form=guest_2g5g"];
            return r && o.push("form=guest_5g_2"), u && o.push("form=guest_6g"), `${n}${o.join("&")}`;
        }
        function c() { return e.read(s()); }
        function f(t, r = !1) { return e.write(s(), t, { preventSuccess: r }); }
        function g() { return e.read(`${n}form=guest`, { preventSuccess: !0 }); }
        function p(t) { return e.write(`${n}form=guest`, t, { preventSuccess: !0 }); }
        function w() { return e.read(`${n}form=syspara_2g`, { preventSuccess: !0 }); }
    """,
    "iot.js": """
        import { _ } from "./update-store.js";
        const c = "/admin/wireless";
        function w() { return _.request(`${c}?form=iot_2g&form=iot_5g&form=iot_5g_2`, { operation: "read_spf" }); }
        function b(e) {
            let s = `${c}?form=iot_2g&form=iot_5g`;
            const { deviceConfig: t } = u();
            return t.isTriBand && (s += "&form=iot_5g_2"), _.request(s, { ...e, operation: "write_spf" });
        }
    """,
    "radio.js": """
        import { s as t, B as d } from "./update-store.js";
        const r = { preventSuccess: !0, preventError: !0 };
        const n = "/admin/wireless?form=wireless";
        function i(e) { return t.request(e, { operation: "read_spf" }, r); }
        function S(e, s) { return t.request(e, { operation: "write_spf", ...s }, r); }
        function W() { return i(`${n}_2g`); }
        function R() { return i(`${n}_5g`); }
        function U(e) {
            const s = `/admin/wireless?${d.getSupportBands().map((m) => `form=wireless_${m}`).join("&")}`;
            return S(s, e);
        }
        function q() { return t.read("/admin/wireless?form=region"); }
    """,
    "plain.js": """
        import { s as t } from "./update-store.js";
        const g = "/admin/ffs?form=config";
        function M() { return t.read(g); }
        function $(e) { return t.write(g, { enable: e }); }
    """,
    "syslog.js": """
        import { H } from "./update-store.js";
        const q = "/admin/syslog?form";
        function Ge() { return H.read(`${q}=filter`); }
        function ze() { return H.load(`${q}=log`); }
        function Qe() {
            const e = new FormData();
            e.append("operation", "save");
            return H.file(`${q}=save_log`, e);
        }
    """,
}


def write_bundles(tmp_path: Path) -> Path:
    directory = tmp_path / "bundles"
    directory.mkdir()
    for name, source in BUNDLES.items():
        (directory / name).write_text(" ".join(source.split()), encoding="utf-8")
    return directory


def forms(report: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(module, form): info for module, entries in report["modules"].items() for form, info in entries.items()}


def test_template_literal_base_is_resolved(tmp_path: Path) -> None:
    found = forms(scan_bundles(str(write_bundles(tmp_path))).to_json())
    assert ("admin/wireless", "guest") in found
    assert set(found[("admin/wireless", "guest")]["operations"]) == {"read", "write"}


def test_joined_array_batch_is_resolved_with_operations(tmp_path: Path) -> None:
    found = forms(scan_bundles(str(write_bundles(tmp_path))).to_json())
    for form in ("guest_2g", "guest_5g", "guest_2g5g", "guest_5g_2", "guest_6g"):
        assert ("admin/wireless", form) in found, form
        assert set(found[("admin/wireless", form)]["operations"]) == {"read", "write"}, form
        assert found[("admin/wireless", form)]["batched"] is True, form


def test_appended_form_parameter_is_resolved(tmp_path: Path) -> None:
    found = forms(scan_bundles(str(write_bundles(tmp_path))).to_json())
    assert set(found[("admin/wireless", "iot_5g_2")]["operations"]) == {"request", "read_spf", "write_spf"}


def test_form_name_completed_from_a_variable(tmp_path: Path) -> None:
    found = forms(scan_bundles(str(write_bundles(tmp_path))).to_json())
    assert set(found[("admin/wireless", "wireless_2g")]["operations"]) == {"request", "read_spf"}


def test_repeated_forms_in_one_literal_are_all_recorded(tmp_path: Path) -> None:
    found = forms(scan_bundles(str(write_bundles(tmp_path))).to_json())
    assert ("admin/wireless", "iot_2g") in found
    assert ("admin/wireless", "iot_5g") in found


def test_quoted_form_suffix_after_a_bare_form_key(tmp_path: Path) -> None:
    found = forms(scan_bundles(str(write_bundles(tmp_path))).to_json())
    assert set(found[("admin/syslog", "filter")]["operations"]) == {"read"}
    assert set(found[("admin/syslog", "log")]["operations"]) == {"load"}
    assert "save" in found[("admin/syslog", "save_log")]["operations"]


def test_plain_literal_still_works(tmp_path: Path) -> None:
    found = forms(scan_bundles(str(write_bundles(tmp_path))).to_json())
    assert set(found[("admin/ffs", "config")]["operations"]) == {"read", "write"}


def test_band_driven_pattern_is_reported_not_silently_dropped(tmp_path: Path) -> None:
    report = scan_bundles(str(write_bundles(tmp_path))).to_json()
    patterns = [pattern["url"] for pattern in report["dynamic_patterns"]]
    assert any("form=wireless_" in url for url in patterns), patterns


def test_report_is_json_serializable(tmp_path: Path) -> None:
    report = scan_bundles(str(write_bundles(tmp_path))).to_json()
    assert json.loads(json.dumps(report))["counts"]["forms"] == report["counts"]["forms"]
