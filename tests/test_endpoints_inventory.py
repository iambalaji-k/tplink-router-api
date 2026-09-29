"""The inventory doc, the generated constants table and the SDK call sites must agree.

`tplink_modern/endpoints.py` is generated from the bundle scan and the read-only live probe, so it
is the machine-readable half of docs/router-api-inventory.md. This test is what makes that pairing
real: the doc's headline counts are read back out of the markdown and compared to the table, the
table's rows are compared to the doc's module reference, and every endpoint the SDK or the REST
layer addresses has to appear in the table -- with a live-answered status if it reads it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.inventory.sdk_calls import call_sites
from tplink_modern import endpoints

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "router-api-inventory.md"
READ_VERBS = frozenset({"read", "load", "list"})

MODULE_RE = re.compile(r"\*\*(\d+) modules / (\d+) forms\*\*")
SURVEYED_RE = re.compile(r"\*\*(\d+) endpoints\*\*")
ANSWERED_ROW_RE = re.compile(r"^\s*\|\s*answered\s*\([^|]*\)\s*\|\s*\*\*(\d+)\*\*\s*\|\s*$", re.M)
DOC_ROW_RE = re.compile(r"^\| `/([^`]+)` \| `([^`]+)` \|", re.M)


@pytest.fixture(scope="module")
def doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_headline_counts_match_the_table(doc_text: str) -> None:
    headline = MODULE_RE.search(doc_text)
    assert headline, "the doc no longer states a module/form headline count"
    assert int(headline.group(1)) == endpoints.MODULE_COUNT
    bundle_forms = int(headline.group(2))

    surveyed = SURVEYED_RE.search(doc_text)
    assert surveyed, "the doc no longer states how many endpoints were surveyed"
    assert int(surveyed.group(1)) == endpoints.FORM_COUNT

    # The gap between the two is exactly the forms no bundle names but this package addresses.
    from_bundles = sum(1 for endpoint in endpoints.ENDPOINTS if endpoint.in_bundles)
    assert bundle_forms == from_bundles
    assert endpoints.FORM_COUNT == from_bundles + sum(
        1 for endpoint in endpoints.ENDPOINTS if not endpoint.in_bundles
    )

    answered = ANSWERED_ROW_RE.search(doc_text)
    assert answered, "the doc no longer states how many forms answered"
    assert int(answered.group(1)) == endpoints.ANSWERED_COUNT


def test_doc_module_reference_lists_every_endpoint(doc_text: str) -> None:
    listed = {(module, form) for module, form in DOC_ROW_RE.findall(doc_text)}
    assert len(listed) == endpoints.FORM_COUNT
    assert listed == {(endpoint.module, endpoint.form) for endpoint in endpoints.ENDPOINTS}


def test_lookup_helpers_agree_with_the_table() -> None:
    assert endpoints.endpoint("admin/nat", "vs") is endpoints.endpoint("/admin/nat", "vs")
    assert endpoints.forms("admin/wireless")
    for name in endpoints.answered_forms("admin/nat"):
        entry = endpoints.endpoint("admin/nat", name)
        assert entry is not None and entry.status == endpoints.ANSWERED
    for endpoint in endpoints.ENDPOINTS:
        assert endpoints.BY_URL[endpoint.url] is endpoint


def test_status_and_verbs_are_consistent() -> None:
    for endpoint in endpoints.ENDPOINTS:
        if endpoint.status == endpoints.ANSWERED:
            assert endpoint.read_verbs, f"{endpoint.url} answered with no verb recorded"
            assert all(verb in READ_VERBS for verb in endpoint.read_verbs)
        else:
            assert not endpoint.read_verbs, f"{endpoint.url} is {endpoint.status} yet records answers"
        if endpoint.status == endpoints.NOT_PROBED:
            assert not endpoint.others_key


def test_every_sdk_call_site_is_inventoried() -> None:
    """No resource may address a form this survey did not see -- that is how `set_guest` broke."""
    seen = 0
    for site in call_sites(ROOT / "tplink_modern", ROOT / "app.py"):
        module, prefix, suffix, verb, path = site.module, site.prefix, site.suffix, site.verb, site.source
        seen += 1
        candidates = [
            endpoint
            for endpoint in endpoints.ENDPOINTS
            if endpoint.module == module and endpoint.form.startswith(prefix) and endpoint.form.endswith(suffix)
        ]
        assert candidates, f"{path.name}: {module}?form={prefix}*{suffix} is not in the inventory"
        if verb in READ_VERBS:
            # A form the probe could not read *without* an argument is still readable: the SDK
            # supplies it (`admin/vpnconn?form=config` needs `vpntype`). Anything else must have
            # answered plainly, or this call site is addressing a form nobody has confirmed.
            assert any(
                endpoint.status in (endpoints.ANSWERED, endpoints.NEEDS_PARAMETERS) for endpoint in candidates
            ), f"{path.name}: {module}?form={prefix}*{suffix} is read ({verb}) but no surveyed form answers it"
    assert seen > 15, f"the call-site scan found only {seen} requests; it has stopped matching"
