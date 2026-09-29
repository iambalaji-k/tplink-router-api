"""Tests for the route-table and menu-tree scanner.

The bundle layout the crawler saved is `webpages__js__<name>.js`, mirroring the router's
`webpages/js/<name>.js`. A hashed file name may itself contain `__`, so these fixtures include one
such name to keep the basename derivation honest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.inventory.ui_routes import Page, basename_of, page_form_map, read_bundles, routes_and_menus

ROUTE_CHUNK = """
const routes = [
  {name:"networkMap",path:"",component:()=>p(()=>import("./index-AAA.js"),[],import.meta.url)},
  {name:"wirelessBasic",path:"wirelessBasic",component:()=>p(()=>import("./index-BBB.js").then(t=>t.k),[],import.meta.url)},
  {name:"a11y",path:"a11y",component:()=>p(()=>import("./index-CCC.js"),[],import.meta.url)}
];
const filtered = routes.filter(e=>names.includes(e.key)).map(e=>({key:e.key,text:"menu."+e.key}));
const menu = [{key:"networkMap",text:"menu.networkMap"},{key:"diagnostics",text:"menu.diagnostics"},{key:"advanced",text:"menu.advanced",children:[{key:"wirelessBasic",text:"menu.wireless"},{key:"a11y",text:"menu.accessibility"},{key:"firmware",text:"menu.firmware"}]}];
"""

FEATURE_CHUNK = """
import { s as t } from "./update-store-PPP.js";
import "./card-IotNetWorkCard-D0OUY3__.js";
import("../locale/tr_TR/index-ZZZ.js");
const a = "/admin/wireless?form=wireless_2g";
function r() { return t.read(a); }
"""

CARD_CHUNK = """
import { s as t } from "./update-store-PPP.js";
const l = "/admin/status?form=router";
function n() { return t.read(l); }
"""

STORE_CHUNK = """
export const we = { read: async (e) => e, write: async (e) => e };
const shared = "/admin/cloud_account?form=check_upgrade";
export { shared };
"""


def write_bundles(tmp_path: Path) -> Path:
    directory = tmp_path / "bundles"
    directory.mkdir()
    files = {
        "webpages__js__index-ROUTE.js": ROUTE_CHUNK,
        "webpages__js__index-AAA.js": FEATURE_CHUNK,
        "webpages__js__index-BBB.js": 'import { s as t } from "./update-store-PPP.js";',
        "webpages__js__index-CCC.js": 'import { s as t } from "./update-store-PPP.js";',
        "webpages__js__card-IotNetWorkCard-D0OUY3__.js": CARD_CHUNK,
        "webpages__js__update-store-PPP.js": STORE_CHUNK,
    }
    for name, source in files.items():
        (directory / name).write_text(" ".join(source.split()), encoding="utf-8")
    return directory


def inventory() -> dict[str, Any]:
    return {
        "modules": {
            "admin/wireless": {"wireless_2g": {"chunks": ["webpages__js__index-AAA.js"]}},
            "admin/status": {"router": {"chunks": ["webpages__js__card-IotNetWorkCard-D0OUY3__.js"]}},
            "admin/cloud_account": {"check_upgrade": {"chunks": ["webpages__js__update-store-PPP.js"]}},
        }
    }


def by_name(pages: list[Page]) -> dict[str, Page]:
    return {page.route.name: page for page in pages}


def pages(tmp_path: Path, depth: int) -> list[Page]:
    bundles = read_bundles(str(write_bundles(tmp_path)))
    # Three chunks import the store, so a threshold of 3 makes it app plumbing in this fixture.
    return page_form_map(bundles, inventory(), depth=depth, hub_threshold=3)


def test_basename_of_strips_only_directory_segments() -> None:
    assert basename_of("webpages__js__index-BEa7yDFE.js") == "index-BEa7yDFE.js"
    assert basename_of("webpages__js__IotNetWorkCard-D0OUY3__.js") == "IotNetWorkCard-D0OUY3__.js"
    assert basename_of("webpages__locale__tr_TR__index-VMnVfjIG.js") == "index-VMnVfjIG.js"


def test_routes_and_menu_tree(tmp_path: Path) -> None:
    bundles = read_bundles(str(write_bundles(tmp_path)))
    routes, trees = routes_and_menus(bundles)
    assert {route.name for route in routes} == {"networkMap", "wirelessBasic", "a11y"}
    assert {route.path for route in routes} == {"", "wirelessBasic", "a11y"}
    menu = trees[0]
    assert [entry.key for entry in menu] == ["networkMap", "diagnostics", "advanced", "wirelessBasic", "a11y", "firmware"]
    assert [entry.depth for entry in menu] == [0, 0, 0, 1, 1, 1]


def test_menu_filtering_code_is_not_mistaken_for_a_tree(tmp_path: Path) -> None:
    bundles = read_bundles(str(write_bundles(tmp_path)))
    _, trees = routes_and_menus(bundles)
    assert len(trees) == 1


def test_page_owns_forms_from_its_own_and_directly_imported_feature_chunks(tmp_path: Path) -> None:
    found = by_name(pages(tmp_path, depth=1))["networkMap"]
    assert "admin/wireless?form=wireless_2g" in found.forms
    assert "admin/status?form=router" in found.forms
    assert "admin/cloud_account?form=check_upgrade" not in found.forms
    assert found.shared_forms == ["admin/cloud_account?form=check_upgrade"]


def test_depth_zero_limits_a_page_to_its_own_component_chunk(tmp_path: Path) -> None:
    found = by_name(pages(tmp_path, depth=0))["networkMap"]
    assert found.forms == ["admin/wireless?form=wireless_2g"]


def test_unfetched_import_is_reported_as_a_coverage_gap(tmp_path: Path) -> None:
    found = by_name(pages(tmp_path, depth=1))["networkMap"]
    assert found.missing_imports == ["index-ZZZ.js"]
