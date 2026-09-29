# Archer AX12 v1 — Router API Inventory

> Surveyed 2026-09-29 against firmware **AX12v1_1.10.2** (`192.168.0.1`): the router's own web
> bundles were parsed, then every endpoint found was asked about live with read-only verbs.
> Companion to [`2026-06-26_sdk-tplink-router-report.md`](../2026-06-26_sdk-tplink-router-report.md),
> which covers how authentication was reverse-engineered.

**50 modules / 225 forms** were recovered from 263 JS bundles — 40 `/admin/*` modules carrying 194
forms, plus 10 non-admin modules with 31. One more form, `admin/wireless?form=statistics`, is used by
this SDK but named nowhere in the bundles, so it was added to the sweep as well: **226 endpoints**
were probed with `read`, `load` or `list` and nothing else:

| This firmware's answer | Forms |
| --- | --- |
| answered (`read`, `load` or `list` succeeded) | **179** |
| no handler — every approved verb returned `no such callback` | 18 |
| handler exists but wants an argument this sweep will not invent | 4 |
| handler exists and named a blocking condition (`err_download`, `recovery enable is off`) | 3 |
| declined with `{"success": false}` and no reason at all | 1 |
| answered with a file or a server error instead of the JSON envelope | 4 |
| module not served at all (HTTP 404) | 4 |
| deliberately not probed: the form name is itself an action | 13 |

The machine-readable twin of this document is
[`tplink_modern/endpoints.py`](../tplink_modern/endpoints.py), generated from the same two reports;
`tests/test_endpoints_inventory.py` fails if the numbers above and the table disagree, or if a call
site in the SDK addresses a form that was not surveyed.

An earlier revision of this document claimed **41 modules / 181 endpoints** and labelled that a
lower bound. It was a lower bound and the gap was worse than stated: the scanner that produced it
matched only quoted literals, while the newer UI builds endpoint URLs from template literals,
variable suffixes and `Array.join("&")` batches. Nothing in that scan was wrong; roughly a fifth of
the surface was simply invisible to it.

---

## 1. How the API works

Every call is a form-encoded POST; there are no meaningful GETs on the router itself:

```
POST http://<host>/cgi-bin/luci/;stok=<session-token>/<module>?form=<form>
Content-Type: application/x-www-form-urlencoded
Referer: http://<host>/webpages/index.html

operation=<operation>&<field>=<value>&...
```

- **`stok`** — session token from the RSA login handshake (`login?form=keys` → `form=auth` →
  `form=login`). **The router keeps exactly one admin session**: a new login replaces the previous
  token, and requests carrying the discarded one answer HTTP 200 with `errorcode: "timeout"`. That
  was established by logging in three times from separate clients and replaying the older tokens;
  this survey's sweep kept one client throughout and never saw a `timeout`, so it adds no evidence
  either way. Stale or unauthorized tokens otherwise surface as `401`/`403` or
  `errorcode: "permission denied"`.
- **`operation`** — the action on that form. Verbs seen in the bundles: `read`, `write`, `load`,
  `insert`, `update`, `remove`, `request`, `go`, `set`, `get`, `file`, plus form-specific ones such
  as `connect`, `disconnect`, `renew`, `release`, `reboot`, `start`, `stop`, `wakeup`, `upgrade`,
  `block`, `access`, `bind`, `unbind`, `export`, `generate`, `check_collision`, `read_spf`,
  `write_spf`, `read_match`, `read_max`. Only `read`, `load` and `list` were ever sent by this survey.
- **Response** — `{"success": bool, "data": {...} | [...], "errorcode": 0 | "reason"}`. A form this
  firmware does not implement answers `errorcode: "no such callback"`.

`ArcherAX12.read()`, `.write()` and `.api(path, form, operation)` reach any row in this document
without SDK changes.

### The UI's own request layer

`update-store-*.js` exports one service object whose eight methods all take the endpoint URL first.
Reading it out of the bundle settles the row-CRUD convention the previous revision could only infer:

| Method | Body it sends |
| --- | --- |
| `read(url)` | `operation=read` |
| `load(url)` | `operation=load` |
| `write(url, payload)` | `operation=write` merged with `payload` |
| `request(url, payload)` | the payload verbatim, so `operation` is whatever the payload names |
| `insert(url, row, {index: 0})` | `operation=insert`, `new=<row as JSON>`, `index=0` |
| `update(url, {key}, newRow, oldRow)` | `operation=update`, `key=…`, `new=<JSON>`, `old=<JSON>` |
| `remove(url, {key, index})` | `operation=remove`, `key=…`, `index=…` |
| `file(url, formData)` | `multipart/form-data`, with `operation` as a form field |

- **Serialization** (`Fo()` in that bundle): each key becomes one `key=value` pair; arrays repeat the
  key once per element; non-scalars are JSON-encoded; `null`/`undefined` are dropped. A repeated
  `form=a&form=b` in the URL is the read side of the same batching.
- **The stok is prepended by an interceptor** (`Ro()`): `url = "/cgi-bin/luci/;stok=" + token + url`,
  with a leading `/` added if missing — matching `tplink_modern/session.py`.
- **The error field has four spellings.** The UI's normalizer destructures
  `errorCode`, `error`, `error_code` **and** `errorcode` and re-emits one field. The SDK inspects
  `errorcode` and `errorCode` only; a refusal reported under either of the other two would be
  invisible to it. Fixed in `tplink_modern/session.py` and `client.py` as part of this survey.
- **Payload encryption is conditional and not required.** The UI encrypts request bodies for
  non-whitelisted URLs over plain HTTP (`needEncrypt()`), with a whitelist covering the pre-login and
  telemetry endpoints (`/login`, `/locale`, `/`, `/debug`, `/upgrade`, `/wan_error`, `/blocking`,
  `/device_config`, `/domain_login`, `/domain_redirect`, `/accessibility`). A client that never
  negotiates an AES key — the SDK — is answered in plaintext, which the live sweep confirms on every
  one of the 179 forms that replied.

### `others`, the sibling outside `data`

List endpoints report their capacity in a top-level `others` object *next to* `data`, never inside
it: `{"success": true, "data": {...}, "others": {"max_rules": 64}}`. Fourteen forms carry a
non-empty one on this unit (`max_rules` for row tables, `max_accounts` for PPTP accounts,
`max_clients` for WireGuard peers), and one — `admin/nat?form=fr6` — sends an empty `others` object,
so its presence is not a signal that limits exist.

**`others` arrives only with `load`.** For every one of the fourteen, `read` returned `data` with no
`others` sibling. Code that needs a rule limit must ask with `load`; this is the one place where the
choice of read verb is not arbitrary.

---

## 2. How this was produced, and how to re-run it

1. **Crawl.** `/webpages/` assets are fetched recursively following `import`/`src` references.
   Static assets need no stok, and the `/cgi-bin/luci/;stok=` prefix 404s for them. 263 JS bundles
   are cached under `.cache/ax12-ui/bundles` (gitignored; regenerable).
2. **Scan the bundles** for endpoint URLs, resolving all four construction shapes the UI uses:
   `venv/Scripts/python.exe -m tools.inventory.extract_ui_inventory`. It reads the router's request
   service vocabulary off the bundle rather than hard-coding it, follows local helper functions that
   forward a URL to that service, and prints the URLs it could *not* resolve instead of dropping
   them. Current output: 50 modules / 225 forms, 8 forms reachable only through batched
   `?form=a&form=b` URLs, 18 forms referenced as strings but with no call site the resolver could
   attribute, and 2 sites whose form name is built at runtime (listed in §4).
3. **Check completeness.** Every `form=<name>` token appearing anywhere in the bundles was
   re-derived independently and looked up in the report. One token did not resolve — `n.locale=r` in
   `su-*.js`, an i18n assignment that happens to read like a query parameter — and it is the only
   miss, so the scan is accounted for. Import specifiers that were never downloaded are listed by
   `venv/Scripts/python.exe -m tools.inventory.fetch_missing_bundles` — plain GETs, so they cannot
   evict the router's session. 27 remain, all translation bundles; three were sampled and contain no
   `form=` string at all, so the missing files are not an endpoint gap.
4. **Map it to the UI.** `venv/Scripts/python.exe -m tools.inventory.ui_routes` reads the Vue router
   table (51 routes, every one resolving to a component chunk), the menu tree (59 entries), and the
   bundle import graph, then attributes each form to the pages that can reach it: 154 in a page's own
   feature chunks, 71 only in the 24 shared chunks (store, composables, vendor), and at two import
   hops all 225 are reachable — so no page is orphaned and no form is stranded. (`statistics` is not
   in that map, because no page requests it.)
5. **Probe the SDK's own call sites too.** `tools/inventory/sdk_calls.py` scans this package for
   `client.read/write/api(...)` and adds any literal form the bundle scan never found, so an
   endpoint the SDK depends on is re-verified rather than inherited from a previous survey's notes.
   That is how `admin/wireless?form=statistics` got its live confirmation and its row fields.

6. **Probe live, read-only.**
   `venv/Scripts/python.exe -m tools.inventory.probe_live --out .cache/ax12-ui/live-probe.json`.
   One `ArcherAX12` client, `read`/`load`/`list` only (the verb is checked before every request),
   forms whose name is an action skipped, and values for keys matching
   `psk|passwd|password|key|pin|private` reduced to their type. The report was audited for leaked
   secret values: none.
7. **Recover the row shapes the router could not show.** `tools/inventory/form_models.py` reads the
   UI's table columns and initial-row literals, which is the only way to name the fields of a list
   the unit has no rows for. Anything from there is labelled as an inference, never as a response.

---

## 3. What the UI references vs what this firmware answers

The two are not the same list, and the difference is the useful part.

**Referenced but not implemented (18)** — `no such callback` for `read`, `load` and `list` alike:
`admin/cloud_account?form=cloud_unbind`, `admin/cloud_account?form=get_device`,
`admin/easymesh_network?form=available_mesh_device_manage`, `admin/easymesh_network?form=change_satellite`,
`admin/smart_network?form=client_speed_limit`, `admin/smart_network?form=game_accelerator`,
`admin/smart_network?form=patrol_owner_block`, `admin/smart_network?form=patrol_owner_website_block`,
`admin/status?form=wan_cable_match_stat`, `admin/vpn?form=thirdvpn`, `admin/wireless?form=mlo_host`,
`admin/wireless?form=ofdma_mimo`, `admin/wireless?form=wireless`, `locale?form=multilang`,
`login?form=get_device`, `login?form=get_token`, `login?form=telemetry`, `wan_error?form=never`.
The wireless pair among them is the interesting case: `mlo_host` (Wi-Fi 7 multi-link) and
`ofdma_mimo` are in the bundles because the bundles ship to several models, not because this unit
has them. Treat "in the UI" as "the UI can ask", never as "the device supports it".

**A handler exists but wants an argument (4)** — the refusal names what is missing, so the form is
reachable once it is supplied. This sweep sends no arguments of its own.

| Form | Refusal | What it wants |
| --- | --- | --- |
| `admin/vpnconn?form=config` | `invalid parameter vpntype` | a `vpntype` field — the SDK already passes one, and `/vpn/connections` works |
| `admin/vpn?form=wireguard` | `invalid vpn_name` | a VPN profile name |
| `admin/network?form=wan_ipv4_bigpond` | `invalid proto_name` | an interface/proto name |
| `admin/smart_network?form=patrol_insights` | `invalid args` | unknown; not reachable without writing |

**A handler exists and named a blocking condition (3)** — the refusal is a state, not a missing
argument, so no parameter would have made these succeed:

| Form | Refusal | Reading |
| --- | --- | --- |
| `admin/cloud_account?form=detect_upgrade_status` | `err_download` | it reports the result of an upgrade check that has to be started first (`upgrade` — not probed) |
| `admin/network?form=wan_autodetect` | `autodetect failed` | `read` *runs* a detection; treat this form as an action, not a query |
| `login?form=vercode` | `recovery enable is off` | account recovery is disabled on this unit |

**Declined without any reason (1)** — `admin/cloud_account?form=auto_update_remind` answers
`{"success": false}` with no error field at all, on every verb. Earlier drafts of this document
printed the SDK's own exception text ("`…/form=auto_update_remind refused by router`") in that cell
and called it a refusal reason; it was our wording, not the router's. The honest entry is
"unknown": a form that carries no handler is reported as `no such callback`, so something is
answering here, but nothing in the response says whether it wants an argument, a different verb or a
different session state.

**Not JSON (4)** — `admin/openvpn?form=export` answers with the client config as a file body (the UI
fetches it through the blob client), `admin/status?form=speedtest` and
`admin/easymesh_network?form=mesh_sclient_detail` return HTTP 500 to a parameterless read, and
`wan_error?form=read` mixes a 500 with `no such callback`.

**Not served (4)** — HTTP 404 for every verb: `/debug?form=cmd|refresh|upload` and
`/blocking?form=vercode`. These are referenced by the UI's never-encrypt whitelist but this firmware
does not host them.

**A correction to the previous revision:** it filed `/locale`, `/upgrade`, `/device_config`,
`/domain_login`, `/domain_redirect` and `/accessibility` as "cloud endpoints reached over
`https://www.tp-link.com`, not the router's CGI". They are router CGIs. The axios instances are built
with `baseURL: "/"` and the stok interceptor rewrites every one of these URLs to
`/cgi-bin/luci/;stok=…/<module>`, and the live sweep got JSON back from `locale?form=lang|list|country`,
`upgrade?form=info|set`, `device_config?form=config`, `domain_login?form=dlogin`,
`domain_redirect?form=get` and `accessibility?form=accessibility_state`. The real tp-link.com
destinations in the bundles are separate link constants (`www.tp-link.com/support/...`,
`privacy.tp-link.com`, `download-app.tp-link.com`), not these forms. What the whitelist actually
means is *unencrypted payload*, not *different host*.

**Deliberately not probed (13)** — `admin/cloud_account?form=cloud_upgrade`,
`admin/easymesh?form=search_slave`, `admin/firmware?form=auto_upgrade|config_multipart|save_upgrade|slave_cmd|upgrade`,
`admin/openvpn?form=openvpn_cert`, `admin/quick_setup?form=ap_setup|quick_setup`,
`admin/syslog?form=save_log`, `admin/system?form=logout|reboot`. Their *names* are actions; a CGI
that acts on any POST would be the one thing a read-only sweep could not take back. "Not probed"
here, not "does not work".

---

## 4. Forms the bundles build at runtime

Two sites assemble a form name from data rather than text, so no literal scan can name them:

- `` `/admin/wireless?${d.getSupportBands().map(m => `form=wireless_${m}`).join("&")}` ``
  (`index-wvlnjLga.js`) — one batch request carrying `wireless_<band>` for every band the unit
  reports. `wireless_2g`, `wireless_5g`, `wireless_5g_2` and `wireless_6g` were recovered as
  individual forms and all four answer `load`/`list`/`read` on this unit.
- The guest-network equivalent, `[...].join("&")` over `["form=guest_2g", ...]` plus conditional
  `.push("form=guest_5g_2")` / `.push("form=guest_6g")` — captured through the joined-array path.

---

## 5. Module reference

Generated by `tools/inventory/gen_endpoints.py --markdown`; "Verbs in the UI" is what the bundles
apply to the form (writes included, as evidence of intent only — none were sent), and "This
firmware" is the live read-only verdict, naming the verbs that answered.

| Module | Form | Verbs in the UI | This firmware |
| --- | --- | --- | --- |
| `/accessibility` | `accessibility_state` | read, write | answered (read) |
| `/admin/access_control` | `black_devices` | block, load, request | answered (load) |
| `/admin/access_control` | `black_list` | insert, load, remove | answered (load) |
| `/admin/access_control` | `enable` | read, write | answered (read) |
| `/admin/access_control` | `mode` | read, write | answered (read) |
| `/admin/access_control` | `white_devices` | access, load, request | answered (load) |
| `/admin/access_control` | `white_list` | insert, load, remove | answered (load) |
| `/admin/administration` | `account` | read, write | answered (read) |
| `/admin/administration` | `https` | read, write | answered (read) |
| `/admin/administration` | `local` | insert, load, remove | answered (load) |
| `/admin/administration` | `mode` | read, write | answered (read) |
| `/admin/administration` | `recovery` | read, write | answered (read) |
| `/admin/administration` | `remote` | read, write | answered (read) |
| `/admin/cloud_account` | `auto_update_remind` | read | declined, no reason |
| `/admin/cloud_account` | `check_device` | read | answered (read) |
| `/admin/cloud_account` | `check_internet` | read | answered (read) |
| `/admin/cloud_account` | `check_upgrade` | read | answered (read) |
| `/admin/cloud_account` | `cloud_bind_status` | read, request | answered (read) |
| `/admin/cloud_account` | `cloud_unbind` | write | no such callback |
| `/admin/cloud_account` | `cloud_upgrade` | read, request, upgrade | not probed |
| `/admin/cloud_account` | `detect_upgrade_status` | read | declined: stated reason |
| `/admin/cloud_account` | `get_device` | read | no such callback |
| `/admin/cloud_account` | `get_token` | read | answered (read) |
| `/admin/cloud_account` | `remind` | read, write | answered (read) |
| `/admin/cloud_account` | `user_login` | write | answered (read) |
| `/admin/cwmp` | `cwmp_setting` | read, write | answered (read) |
| `/admin/ddns` | `dyndns` | login, logout, read, refresh, request | answered (read) |
| `/admin/ddns` | `noip` | login, logout, read, refresh, request | answered (read) |
| `/admin/ddns` | `provider` | read | answered (read) |
| `/admin/ddns` | `tplink` | bind, insert, load, remove, request, unbind | answered (load) |
| `/admin/dhcps` | `client` | load | answered (load) |
| `/admin/dhcps` | `reservation` | insert, load, remove, update | answered (load) |
| `/admin/dhcps` | `setting` | read, write | answered (read) |
| `/admin/diag` | `diag` | continue, request, start, stop | answered (read) |
| `/admin/easymesh` | `easymesh_enable` | read, write | answered (read) |
| `/admin/easymesh` | `search_slave` | check, request, start, stop | not probed |
| `/admin/easymesh_network` | `ap_avoidance_enable_status` | read | answered (read) |
| `/admin/easymesh_network` | `available_mesh_device_manage` | add_onboarding, link, request, unlink | no such callback |
| `/admin/easymesh_network` | `change_satellite` | write | no such callback |
| `/admin/easymesh_network` | `mesh_sclient_detail` | read, request, write | not JSON |
| `/admin/easymesh_network` | `mesh_sclient_list_all` | read | answered (read) |
| `/admin/ffs` | `config` | read, write | answered (read) |
| `/admin/firmware` | `auto_upgrade` | read, write | not probed |
| `/admin/firmware` | `config` | check, factory, read, request | answered (read) |
| `/admin/firmware` | `config_multipart` | backup, file, restore | not probed |
| `/admin/firmware` | `save_upgrade` | file, firmware | not probed |
| `/admin/firmware` | `slave_cmd` | request, slave_get_info, slave_get_upgrade_info, slave_upgrade_firmware | not probed |
| `/admin/firmware` | `upgrade` | fwup_check, read, request, write | not probed |
| `/admin/imb` | `arp_list` | bind, load, remove, request | answered (load) |
| `/admin/imb` | `bind_list` | insert, load, remove | answered (load) |
| `/admin/imb` | `client_list` | read | answered (read) |
| `/admin/imb` | `setting` | read, write | answered (read) |
| `/admin/iptv` | `setting` | change, read, request, write | answered (read) |
| `/admin/iptv` | `udp_proxy_setting` | read, write | answered (read) |
| `/admin/l2tpoveripsec` | `config` | read | answered (read) |
| `/admin/ledgeneral` | `setting` | read, write | answered (read) |
| `/admin/ledpm` | `setting` | read, write | answered (read) |
| `/admin/nat` | `alg` | read, write | answered (read) |
| `/admin/nat` | `client_list` | read | answered (read) |
| `/admin/nat` | `client_list_v6` | read | answered (read) |
| `/admin/nat` | `dmz` | read, write | answered (read) |
| `/admin/nat` | `fr6` | insert, load, remove, update | answered (load+read) |
| `/admin/nat` | `pt` | insert, load, remove, update | answered (load+read) |
| `/admin/nat` | `setting` | read, write | answered (read) |
| `/admin/nat` | `vs` | insert, load, remove, update | answered (load+read) |
| `/admin/network` | `lan_agg` | read, write | answered (read) |
| `/admin/network` | `lan_fc` | read, write | answered (read) |
| `/admin/network` | `lan_ipv4` | read, write | answered (read) |
| `/admin/network` | `lan_ipv6` | read, write | answered (read) |
| `/admin/network` | `mac_clone_advanced` | read, write | answered (read) |
| `/admin/network` | `port_speed_current` | read, write | answered (read) |
| `/admin/network` | `port_speed_supported` | read | answered (load+list+read) |
| `/admin/network` | `routes_static` | insert, load, remove, update | answered (load) |
| `/admin/network` | `routes_system` | load | answered (load) |
| `/admin/network` | `status_ipv4` | read | answered (load+list+read) |
| `/admin/network` | `wan_autodetect` | detect, read, request | declined: stated reason |
| `/admin/network` | `wan_fc` | read, write | answered (read) |
| `/admin/network` | `wan_ipv4_bigpond` | read, write | needs a parameter |
| `/admin/network` | `wan_ipv4_dslite` | read, write | answered (read) |
| `/admin/network` | `wan_ipv4_dynamic` | read, release, renew, request, write | answered (read) |
| `/admin/network` | `wan_ipv4_l2tp` | connect, disconnect, read, request, write | answered (read) |
| `/admin/network` | `wan_ipv4_ocn` | read, write | answered (read) |
| `/admin/network` | `wan_ipv4_pppoe` | connect, disconnect, read, release, renew, request, write | answered (read) |
| `/admin/network` | `wan_ipv4_pptp` | connect, disconnect, read, request, write | answered (read) |
| `/admin/network` | `wan_ipv4_protos` | read, request | answered (read) |
| `/admin/network` | `wan_ipv4_staticip` | read, write | answered (read) |
| `/admin/network` | `wan_ipv4_status` | read | answered (read) |
| `/admin/network` | `wan_ipv4_v6plus` | read, write | answered (read) |
| `/admin/network` | `wan_ipv6_dynamic` | read, release, renew, request, write | answered (read) |
| `/admin/network` | `wan_ipv6_pass` | write | answered (read) |
| `/admin/network` | `wan_ipv6_pppoe` | connect, disconnect, read, request, write | answered (read) |
| `/admin/network` | `wan_ipv6_protos` | read, request | answered (read) |
| `/admin/network` | `wan_ipv6_static` | read, write | answered (read) |
| `/admin/network` | `wan_ipv6_status` | read, write | answered (read) |
| `/admin/network` | `wan_ipv6_tunnel` | connect, disconnect, read, request, write | answered (read) |
| `/admin/network` | `wan_port_status` | detect, read, request, write | answered (read) |
| `/admin/network` | `wan_retrieve_ipv4_pppoe` | read, write | answered (read) |
| `/admin/openvpn` | `config` | read, write | answered (read) |
| `/admin/openvpn` | `export` | backup, file | not JSON |
| `/admin/openvpn` | `openvpn_cert` | check, generate, request | not probed |
| `/admin/pptpd` | `accounts` | insert, load, remove, update | answered (load) |
| `/admin/pptpd` | `config` | read, write | answered (read) |
| `/admin/privacy_policy` | `fing_auth_state` | read, write | answered (read) |
| `/admin/qos` | `update_database` | - | answered (read) |
| `/admin/quick_setup` | `ap_setup` | read, write | not probed |
| `/admin/quick_setup` | `check_router` | read | answered (load+list+read) |
| `/admin/quick_setup` | `quick_setup` | read, write | not probed |
| `/admin/reboot` | `set` | read, write | answered (read) |
| `/admin/security_settings` | `new_enable` | read, write | answered (read) |
| `/admin/smart_network` | `client_speed_limit` | read_max, request, write | no such callback |
| `/admin/smart_network` | `device_priority` | load, update | answered (load) |
| `/admin/smart_network` | `game_accelerator` | request | no such callback |
| `/admin/smart_network` | `get_host_info` | read | answered (read) |
| `/admin/smart_network` | `patrol_devices` | load | answered (load+list+read) |
| `/admin/smart_network` | `patrol_enable` | read, write | answered (read) |
| `/admin/smart_network` | `patrol_insights` | read, request | needs a parameter |
| `/admin/smart_network` | `patrol_limit` | read | answered (read) |
| `/admin/smart_network` | `patrol_owner_block` | write | no such callback |
| `/admin/smart_network` | `patrol_owner_list` | insert, load, remove, update | answered (load+list+read) |
| `/admin/smart_network` | `patrol_owner_website_block` | write | no such callback |
| `/admin/smart_network` | `qos` | read, write | answered (read) |
| `/admin/status` | `all` | read | answered (load+list+read) |
| `/admin/status` | `cloud_login_window_pop` | read, write | answered (read) |
| `/admin/status` | `internet` | read | answered (load+list+read) |
| `/admin/status` | `menu_status` | read, request, set | answered (load+list+read) |
| `/admin/status` | `router` | read | answered (read) |
| `/admin/status` | `speedtest` | clear, get, get_servers, get_status, modify_status, read, request, start, stop | not JSON |
| `/admin/status` | `user_experience_plan_switch` | read, write | answered (read) |
| `/admin/status` | `wan_cable_match_stat` | read_match, request | no such callback |
| `/admin/status` | `wan_dual_nat_state` | read | answered (read) |
| `/admin/status` | `wan_speed` | read | answered (load+list+read) |
| `/admin/syslog` | `filter` | read, write | answered (read) |
| `/admin/syslog` | `log` | load, mail, remove, request | answered (load) |
| `/admin/syslog` | `mail` | read, write | answered (read) |
| `/admin/syslog` | `save_log` | file, save | not probed |
| `/admin/syslog` | `types` | load | answered (load+list+read) |
| `/admin/system` | `logout` | request | not probed |
| `/admin/system` | `reboot` | reboot, request, write | not probed |
| `/admin/system` | `sysmode` | read, write | answered (read) |
| `/admin/time` | `dst` | read, write | answered (read) |
| `/admin/time` | `hour24` | write | answered (read) |
| `/admin/time` | `settings` | gmt, read, refresh, request, write | answered (read) |
| `/admin/traffic` | `dev_name` | write | answered (read) |
| `/admin/upnp` | `enable` | read, write | answered (read) |
| `/admin/upnp` | `service` | load | answered (load+list+read) |
| `/admin/usbmodem` | `isplist` | read | answered (read) |
| `/admin/usbmodem` | `modemset` | read | answered (read) |
| `/admin/vpn` | `enable` | read, write | answered (read) |
| `/admin/vpn` | `ovpn` | file, read, release, request, write | answered (read) |
| `/admin/vpn` | `server` | connected_status, file_check, insert, load, remove, request, update | answered (load) |
| `/admin/vpn` | `thirdvpn` | cloud_check, enable_server, get_detail, get_ping, get_server_list, insert, modify, nordvpn_login, request, surfshark_login, update, update_config, verify | no such callback |
| `/admin/vpn` | `vpn_user_devices` | load | answered (load+list+read) |
| `/admin/vpn` | `vpn_user_list` | insert, load, remove, request, update | answered (load) |
| `/admin/vpn` | `wireguard` | file, upload_file | needs a parameter |
| `/admin/vpnconn` | `config` | disconnect, list, request | needs a parameter |
| `/admin/wifidog` | `portal_background` | file, read, upload | answered (read) |
| `/admin/wifidog` | `portal_logo` | file, read, upload | answered (read) |
| `/admin/wireguard` | `account` | check_collision, download, export, file, get_default, insert, load, remove, renew, request, update | answered (load) |
| `/admin/wireguard` | `config` | read, renew, request, wg_status, write | answered (read) |
| `/admin/wireless` | `guest` | read, write | answered (load+list+read) |
| `/admin/wireless` | `guest_2g` | read, write | answered (load+list+read) |
| `/admin/wireless` | `guest_2g5g` | read, write | answered (load+list+read) |
| `/admin/wireless` | `guest_5g` | read, write | answered (load+list+read) |
| `/admin/wireless` | `guest_5g_2` | read, write | answered (load+list+read) |
| `/admin/wireless` | `guest_6g` | read, write | answered (load+list+read) |
| `/admin/wireless` | `guestnetwork_bandwidth_ctrl` | read, write | answered (read) |
| `/admin/wireless` | `guestnetwork_effectivetime_ctrl` | read, write | answered (read) |
| `/admin/wireless` | `iot_2g` | read_spf, request, write_spf | answered (load+list+read) |
| `/admin/wireless` | `iot_5g` | read_spf, request, write_spf | answered (load+list+read) |
| `/admin/wireless` | `iot_5g_2` | read_spf, request, write_spf | answered (load+list+read) |
| `/admin/wireless` | `mlo_host` | read, write | no such callback |
| `/admin/wireless` | `ofdma` | read, write | answered (load+list+read) |
| `/admin/wireless` | `ofdma_mimo` | read, write | no such callback |
| `/admin/wireless` | `portal_content` | read, write | answered (load+list+read) |
| `/admin/wireless` | `region` | read, write | answered (load+list+read) |
| `/admin/wireless` | `smart_connect` | read, write | answered (load+list+read) |
| `/admin/wireless` | `statistics` | not in the bundles | answered (load+list+read) |
| `/admin/wireless` | `syspara_2g` | read | answered (load+list+read) |
| `/admin/wireless` | `syspara_5g` | read | answered (load+list+read) |
| `/admin/wireless` | `syspara_5g_2` | read | answered (load+list+read) |
| `/admin/wireless` | `syspara_6g` | read | answered (load+list+read) |
| `/admin/wireless` | `syspara_wps` | read, write | answered (load+list+read) |
| `/admin/wireless` | `twt` | read, write | answered (load+list+read) |
| `/admin/wireless` | `wireless` | - | no such callback |
| `/admin/wireless` | `wireless_2g` | read, read_spf, request | answered (load+list+read) |
| `/admin/wireless` | `wireless_5g` | read, read_spf, request | answered (load+list+read) |
| `/admin/wireless` | `wireless_5g_2` | read, read_spf, request | answered (load+list+read) |
| `/admin/wireless` | `wireless_6g` | read_spf, request | answered (load+list+read) |
| `/admin/wireless` | `wireless_addition_setting` | read, write | answered (read) |
| `/admin/wireless` | `wireless_schedule` | read, write | answered (read) |
| `/admin/wireless` | `wps_connect` | read, request | answered (load+list+read) |
| `/admin/wireless` | `wps_pin` | read, write | answered (load+list+read) |
| `/admin/wol` | `device` | insert, load, remove, request, update, wakeup | answered (load) |
| `/admin/yandex_dns` | `device` | insert, load, remove, update | answered (load) |
| `/admin/yandex_dns` | `enable` | read, write | answered (read) |
| `/admin/yandex_dns` | `setting` | read, write | answered (read) |
| `/blocking` | `vercode` | - | HTTP 404 |
| `/debug` | `cmd` | - | HTTP 404 |
| `/debug` | `refresh` | - | HTTP 404 |
| `/debug` | `upload` | - | HTTP 404 |
| `/device_config` | `config` | read | answered (read) |
| `/domain_login` | `dlogin` | read | answered (read) |
| `/domain_redirect` | `get` | - | answered (load+list+read) |
| `/locale` | `country` | read | answered (read) |
| `/locale` | `lang` | read, write | answered (read) |
| `/locale` | `list` | read | answered (read) |
| `/locale` | `multilang` | - | no such callback |
| `/login` | `auth` | read | answered (read) |
| `/login` | `check_factory_default` | read | answered (read) |
| `/login` | `check_internet` | read | answered (read) |
| `/login` | `cloud_bind_status` | read | answered (read) |
| `/login` | `cloud_login` | write | answered (read) |
| `/login` | `get_device` | - | no such callback |
| `/login` | `get_eweb_url` | read | answered (read) |
| `/login` | `get_firmware_info` | - | answered (load+list+read) |
| `/login` | `get_logo_url` | read | answered (read) |
| `/login` | `get_token` | - | no such callback |
| `/login` | `keys` | read | answered (read) |
| `/login` | `password` | - | answered (read) |
| `/login` | `sysmode` | - | answered (load+list+read) |
| `/login` | `telemetry` | request, user_action | no such callback |
| `/login` | `vercode` | - | declined: stated reason |
| `/upgrade` | `info` | - | answered (read) |
| `/upgrade` | `set` | - | answered (read) |
| `/wan_error` | `never` | - | no such callback |
| `/wan_error` | `read` | - | not JSON |

Built at runtime, so no single form name is readable statically:
- `/admin/wireless?«d.getSupportBands().map(m=>`form=wireless_${m}`).join("&")»` in `webpages__js__index-wvlnjLga.js`
- `form=wireless_«m»` in `webpages__js__index-wvlnjLga.js`
---

## 6. Response shapes worth knowing

Field names and types, sampled on this unit; secret-named values are masked.

**`admin/status?form=all`** — one flattened blob holding the router, LAN, WAN, wireless and guest
state. Guest settings arrive as prefixed siblings (`guest_2g_ssid`, `guest_2g_enable`,
`guest_2g_psk_key`, `guest_5g_*`, `guest_2g5g_*`), which is why it looks like a merged view but is
not the form to write. `access_devices_wireless_host` is an array of `{hostname, ipaddr, macaddr,
wire_type}`.

**`admin/wireless?form=wireless_2g` / `wireless_5g` / `wireless_5g_2` / `wireless_6g`** — 41 fields
each (40 on `wireless_5g_2`), all four answering `read`, `load` and `list`: `ssid`, `channel`,
`current_channel`, `htmode`, `hwmode`, `encryption`, `hidden`, `disabled`, `enable`, `macaddr`,
`port`, `server`, `txpower`, `airtime_fairness`, `mu_mimo`, `wds_status`, `wps_state`, `extinfo`,
plus the key material `psk_key`, `psk_cipher`, `psk_version`, `wpa_key`, `wpa_cipher`,
`wep_key1`–`wep_key4` and `wep_format1`–`wep_format4`. Three of those are actual secrets
(`psk_key`, `wpa_key`, `wep_key1`–`wep_key4`) sitting in one form alongside everything else;
anything that dumps this form must redact by name.

**`admin/wireless?form=guest_2g` / `guest_5g` / `guest_6g`** — the per-band guest config,
unprefixed: `enable`, `ssid`, `encryption`, `psk_key`, `psk_cipher`, `psk_version`, `hidden`,
`disabled`, `disabled_by`, `redirect`, `redirect_url`, `authentication_type`,
`authentication_timeout`, `portal_password`, `extinfo`.

**`admin/wireless?form=guest_2g5g`** — the merged view, and it is *not* what the per-band forms
return: `encryption`, `psk_key`, `psk_cipher`, `psk_version`, `passwd_cycle`, `redirect`,
`redirect_url`, `authentication_type`, `authentication_timeout`, `portal_password`. No `enable`, no
`ssid`. Writes to it take `GUEST_2G5G_`-prefixed names while the per-band forms take bare ones — the
reason `set_guest()` was a silent no-op before it was fixed (see finding 2).

**`admin/wireless?form=region`** — the capability source: `country`, `region_list`,
`region_select_permission`, `support_please_select`, `support_smart_connect`,
`support_wireless_schedule`, and `capability` holding `channel_*`, `hwmode_*`, `htmode_*` per band.
An unused band's list arrives as `{}` rather than `[]`, and an empty `region_list` means the country
is locked.

**`admin/access_control?form=black_devices` / `white_devices`** — array of
`{mac, name, ipaddr, conn_type, raw_conn_type, type, guest, host}` (8 entries here). The `*_list`
forms are the configured blocks: `{}` when empty, an array or keyed object when populated, and
`others.max_rules = 64`.

**`admin/dhcps?form=reservation`** — array of `{mac, ip, hostname, comment, enable}`, and note the
names: `ip` and `hostname`, not the `ipaddr`/`name` the lease list uses.
**`admin/dhcps?form=client`** — array of `{macaddr, ipaddr, name, leasetime}`.
**`admin/nat?form=client_list`** — array of `{mac, ip, name, client_type, guest, wire_type}`.
**`admin/smart_network?form=patrol_devices`** / **`admin/vpn?form=vpn_user_devices`** — 19 devices as
`{device_id, mac, name, client_type, …}`.
**`admin/wireless?form=statistics`** — per-client radio counters `{mac, rxpkts, txpkts, type,
encryption}`. This is the one surveyed form no bundle names: the UI never asks for it, while
`wifi.statistics()` does, so it was added to the sweep from this package's own call sites rather than
carried over from the previous survey's notes.

**Empty tables answer `{}`, not `[]`.** `admin/nat?form=vs`, `admin/nat?form=pt`, `admin/upnp?form=service`,
`admin/imb?form=bind_list`, `admin/wol?form=device`, `admin/access_control?form=black_list` and 17
more answered an empty object on this unit (23 in all; not one answered `[]`), while the same forms
return lists when populated. Any caller must accept both shapes; the SDK's `_as_rows()`/`_rows()`
helpers exist for exactly this.

**`others` capacity, this unit:** `max_rules` — virtual servers 64, port triggers 32, IPv6 forwards
(no limit reported; `others` is empty), DHCP reservations 64, IP/MAC bindings 64, ARP entries 64,
access-control black and white lists 64 each, static routes 32, WoL devices 32, Yandex.DNS devices
32, VPN servers 6, local admin hosts 32; `max_accounts` — PPTP 16; `max_clients` — WireGuard 16.

---

## 7. Findings worth acting on

1. **A static scan of this UI under-reports by design, and says so badly.** The first revision
   reported "0 paths built dynamically" — a detector bug, not a clean result. Absence from a literal
   scan is not evidence a form does not exist; the correct claim is "not observed".
2. **`success: true` says nothing about unrecognised parameters.** Established by the guest-wi-fi
   incident: `set_guest()` posted bare `enable`/`isolate` to `guest_2g5g`, which wanted prefixed
   names, and the router accepted and ignored both. Verify a write by reading it back, and never
   assume a read schema equals the write schema. This is why no write verb was sent in this survey:
   the ones the SDK already ships were validated in earlier sessions by read-back, and the rest stay
   unverified rather than half-tested.
3. **`menu_status` is not a feature tree — the real capability source is `wireless?form=region`.**
   Re-confirmed: it answers `{patrol_mark: "0"}` and nothing else.
4. **`others` only arrives with `load`.** A row limit read through `operation=read` is silently
   missing. Use `load` for any list whose capacity you need.
5. **Field names differ between sibling forms.** DHCP reservations use `ip`/`hostname`, leases use
   `ipaddr`/`name`, NAT client lists use `ip`/`mac`/`wire_type`. Do not share a row model between
   them.
6. **Empty list forms answer `{}`, not `[]`,** and an unused 6G capability list also arrives as `{}`.
   Both shapes must be handled.
7. **Several forms return secrets in cleartext:** `wireless_2g/5g/...` (`psk_key`, `wpa_key`,
   `wep_key1..4`), `guest_*` (`psk_key`, `portal_password`), `status?form=all` (flattened
   `guest_*_psk_key`), `admin/wireguard?form=config` (`private_key`), `admin/openvpn?form=export`
   (the client config as a file). `GET /status` redacts by default (`tplink_modern/models.py`);
   anything else built on these forms has to do the same.
8. **The error field has four spellings** (`errorCode`, `error`, `errorcode`, `error_code`); the SDK
   now reads all four, because a session loss reported under an unrecognised spelling looks like a
   data error.
9. **`/locale`, `/upgrade`, `/accessibility`, `/device_config`, `/domain_login` and
   `/domain_redirect` are router CGIs**, not cloud endpoints; `/debug` and `/blocking` are referenced
   but not served (404). See §3.
10. **Two reboot paths exist** (`/admin/reboot?form=set` and `/admin/system?form=reboot`); the SDK
    uses the latter. Neither was probed — both are action-shaped.
11. **Per-band guest and radio forms are the write path, and the batched `guest_2g5g` view is not.**
    `guest_2g`/`guest_5g`/`guest_6g` answer `read`/`load`/`list`; `guest_2g5g` answers with a
    credential-only subset. Client isolation lives on a fourth form, `?form=guest`, with `access` and
    `isolate`.

---

## 8. Not verified

- **Every write path.** No `write`, `insert`, `update`, `remove`, `go`, `set`, `request`, `file`,
  `reboot`, `upgrade`, `block`, `access`, `wakeup`, `connect`, `disconnect` or `bind` was sent.
  `ui_operations` in §5 is bundle evidence of intent, not a result.
- **Bespoke read verbs.** The wireless module's `read_spf` / `write_spf`, `read_match` and `read_max`
  are not `read`, so the sweep did not send them. `wireless_2g` still answers plain `read`.
- **13 action-shaped forms**, listed in §3, were not touched at all.
- **Port-forward and other empty-table row fields are inferred.** The router returned `{}` for
  `admin/nat?form=vs` and `?form=pt` because this unit has no rules, and creating one to find out is
  a write. Their field names come from the UI's own initial-row literal and table columns
  (`tools/inventory/form_models.py`): a virtual server is `{key, name, ip, externalPort, protocol,
  internalPort, enable, externalPortType, externalPortRangeStart, externalPortRangeEnd,
  externalPortSingle}` and a port trigger is `{key, name, externalPort, externalProtocol, triggerPort,
  triggerProtocol, enable}`. **This is a guess in the sense that the router has not confirmed it** —
  the names are as the UI sends them, and `ForwardRule` deliberately keeps `extra="allow"` so an
  unexpected field cannot break a read.
- **Firmware-specific limits.** All counts and schemas are for AX12v1_1.10.2. Another model or
  firmware revision needs the scan and the sweep re-run, not a caveat here.
