# Archer AX12 v1 — Router API Inventory

> Surveyed 2026-09-29 against firmware **AX12v1_1.10.2** (`192.168.0.1`).
> Companion to [`2026-06-26_sdk-tplink-router-report.md`](../2026-06-26_sdk-tplink-router-report.md), which covers how authentication was reverse-engineered.

**41 modules / 181 endpoints** were extracted from the router's own web UI, and every module
was spot-checked with live read-only calls. The `tplink_modern` SDK and its REST layer now model
about two dozen of them — status, clients, DHCP, wireless (incl. guest credentials), VPN,
access control, reboot and firmware check.

---

## 1. How the API works

Every call is a form-encoded POST; there are no meaningful GETs on the router itself:

```
POST http://<host>/cgi-bin/luci/;stok=<session-token>/<module>?form=<form>
Content-Type: application/x-www-form-urlencoded
Referer: http://<host>/webpages/index.html

operation=<operation>&<field>=<value>&...
```

- **`stok`** — session token from the RSA login handshake (`login?form=keys` → `form=auth` → `form=login`). **The router keeps exactly one admin session**: a new login replaces the previous token, and requests carrying the discarded one answer HTTP 200 with `errorcode: "timeout"`. Stale or unauthorized tokens otherwise surface as `401`/`403` or `errorcode: "permission denied"`. Verified by logging in three times from separate clients and replaying the older tokens.
- **`operation`** — the action on that form. Observed values: `read`, `write`, `load`, `insert`, `update`, `remove`, `list`, `go`, `set`, `request`, plus form-specific verbs such as `connect`, `disconnect`, `renew`, `release`, `reboot`, `start`, `stop`, `wakeup`, `upgrade`.
- **Response** — `{"success": bool, "data": {...} | [...], "errorcode": 0 | "reason"}`. A rejected form name answers `errorcode: "no such callback"`.

`ArcherAX12.read()`, `.write()` and `.api(path, form, operation)` reach any row in this document
without SDK changes.

---

## 2. Verified against this router (live, read-only)

### REST read endpoints — 12/12 checks passed

`GET` routes exposed by `app.py`, validated for HTTP 200, declared response shape, and PSK
redaction, against the real router:

| Endpoint | Result | Sample |
| --- | --- | --- |
| `/status` | ok | cpu 0.37, 8 clients, `psk_key` redacted |
| `/clients` | ok | list[8] — `Example-SSID / 192.168.0.224 / 2.4G` |
| `/firmware` | ok | `{"update_number": 1}` |
| `/network/lan` | ok | `192.168.0.1/24`, dhcp on |
| `/network/wan` | ok | `198.51.100.27`, gw `198.51.100.1`, dhcp |
| `/network/dhcp/reservations` | ok | list[2] — `laptop`, `serverbox` |
| `/wifi/statistics` | ok | list[8] — per-client rx/tx packets |
| `/vpn/openvpn` | ok | disabled, udp/1194 |
| `/vpn/pptp` | ok | disabled |
| `/vpn/connections` | ok | list[0] |
| `/docs`, `/openapi.json` | ok | 200 |

### Access control, forwarding and WoL probes

Run with `read`/`load` only, against this unit:

| Probe | Result |
| --- | --- |
| `access_control?form=enable` | `{enable: "off", host_mac: "AA-BB-CC-DD-EE-08"}` — access control is off, and the router pins one protected MAC |
| `access_control?form=mode` | `{access_mode: "black"}` |
| `access_control?form=black_devices` / `white_devices` | list[8] of `{mac, name, ipaddr, conn_type, raw_conn_type, type, guest, host}` — candidates to block or allow |
| `access_control?form=black_list` / `white_list` | `{}` when empty; entries arrive as a list, so both shapes must be handled |
| `nat?form=setting` | `{enable: "on", boost_enable: "on", reboot_time: 190}` |
| `nat?form=pt`, `upnp?form=service`, `wol?form=device` | `{}` — reachable, nothing configured |
| `status?form=menu_status` | `{patrol_mark: "0"}` — far thinner than expected; it reports feature flags, not a navigation tree |

The UI issues these write operations, confirmed from the bundles: block is
`request(black_devices, {operation:"block", data: JSON.stringify(row), index: n})` and allow is
the same with `operation:"access"` against `white_devices`; removal is
`remove(list_form, {key: <mac>, index: <position>})`. `set_guest`'s and access control's write
paths follow that shape but have **not been exercised against the device**, since both would
change live configuration.

Row CRUD across this firmware follows one convention, observed in the WoL and NAT modules:
`insert(url, row, {index: 0})`, `update(url, {key}, row, index)`, `remove(url, {key, index})`,
and one-off verbs via `request(url, {operation: "wakeup"|"block"|..., data: JSON.stringify(row)})`.
List loads also carry an `others` sibling (e.g. `others.max_rules`) that is *not* inside `data`.

**Port forwarding rules could not be schema-mapped.** `nat?form=vs` and `?form=pt` answer `{}`
on this unit and there is no example row anywhere in the bundles, so `ForwardRule` keeps whatever
fields the router sends (`extra="allow"`) instead of asserting a shape. Adding a rule is therefore
not implemented — the field names are the one part of this survey still unknown.

### General form probes — 26 of 27 returned data

These confirmed the SDK's targets are real:

| Probe | Result |
| --- | --- |
| `admin/status?form=all` | ok — full status incl. `guest_2g5g_*` fields |
| `admin/wireless?form=wireless_2g` / `wireless_5g` | ok — ch 2 / ch 149, `htmode` auto / 80, `hwmode` bgn / anacax |
| `admin/wireless?form=guest_2g5g` | ok — reads back unprefixed `psk_key`, `encryption=psk_sae`, `redirect`, `passwd_cycle`; writes need the prefixed names (finding 2) |
| `admin/wireless?form=statistics` | ok — list[8] |
| `admin/wireless?form=wireless_addition_setting`, `region` | ok — region `US`, `beacon_int=100`, `dtim_period=1` |
| `admin/wireless?form=wireless` | **FAIL — `no such callback`** (present in UI source; needs an extra parameter) |
| `admin/dhcps?form=reservation` / `client` / `setting` | ok — 2 reservations, 10 lease clients, pool `192.168.0.2-253`, leasetime 120 |
| `admin/network?form=lan_ipv4` | ok |
| `admin/nat?form=vs` / `dmz` | ok — no virtual servers, DMZ off |
| `admin/imb?form=bind_list` | ok — empty |
| `admin/upnp?form=enable` | ok — `enable=on` |
| `admin/security_settings?form=new_enable` | ok — lan_ping on, **wan_ping off** |
| `admin/time?form=settings` | ok — NTP `in.pool.ntp.org`, timezone 91 |
| `admin/smart_network?form=patrol_enable` | ok — off |
| `admin/easymesh_network?form=mesh_sclient_list_all` | ok — empty |
| `admin/system?form=sysmode` | ok — `mode=router` |
| `admin/wireguard?form=config` | ok — **returns `private_key`** |
| `admin/vpn?form=enable` | ok — off |
| `admin/ledgeneral?form=setting` | ok — on |
| `admin/administration?form=account` | ok — read-only view of the admin-account form |
| `admin/cloud_account?form=check_upgrade` | ok |

---

## 3. Module reference

Operations listed are those observed in the UI bundles. Bare `read`/`write` means the form
follows the usual read-modify-write pattern; extra verbs are form-specific.

### Authentication — `/login` (14)

| Form | Operations |
| --- | --- |
| `keys`, `auth`, `password`, `vercode`, `sysmode`, `check_internet`, `check_factory_default`, `get_firmware_info`, `get_token`, `cloud_bind_status`, `get_eweb_url` | read |
| `cloud_login` | write |
| `telemetry` | request, user_action |

`login?form=login` (used by the SDK to obtain the stok) is issued by the login page itself and
is not present in the post-login bundles.

### Status & diagnostics

| Module | Form | Operations |
| --- | --- | --- |
| `/admin/status` (10) | `all`, `internet`, `router`, `wan_dual_nat_state` | read |
| | `menu_status` | read, request, set — drives the whole UI navigation tree |
| | `wan_speed` | read |
| | `wan_cable_match_stat` | read_match, request |
| | `user_experience_plan_switch`, `cloud_login_window_pop` | read, write |
| | `speedtest` | get, get_servers, get_status, modify_status, start, stop, clear |
| `/admin/diag` (1) | `diag` | start, stop, continue — ping / traceroute |
| `/admin/syslog` (1) | `save_log` | read |
| `/admin/traffic` (1) | `dev_name` | write |
| `/admin/reboot` (1) | `set` | read, write |
| `/admin/system` (3) | `sysmode` | read, write |
| | `reboot` | write, request, reboot |
| | `logout` | request |
| `/admin/time` (3) | `settings` | read, write, gmt, refresh |
| | `dst` | read, write |
| | `hour24` | write |
| `/admin/ledgeneral`, `/admin/ledpm` (1 each) | `setting` | read, write |

### Network — `/admin/network` (32)

| Group | Forms |
| --- | --- |
| LAN | `lan_ipv4`, `lan_ipv6`, `lan_agg`, `lan_fc`, `port_speed_current`, `port_speed_supported` (all read/write, last read-only) |
| Routes | `routes_static`, `routes_system` (load) |
| WAN | `wan_ipv4_dynamic`, `wan_ipv4_staticip`, `wan_ipv4_bigpond`, `wan_ipv4_dslite`, `wan_ipv4_ocn`, `wan_ipv4_v6plus`, `wan_ipv4_protos`, `wan_fc`, `mac_clone_advanced`, `wan_port_status` |
| WAN (dial) | `wan_ipv4_pppoe` and `wan_ipv4_pptp`/`wan_ipv4_l2tp`: connect, disconnect, read, write (+ renew, release for pppoe) |
| WAN IPv6 | `wan_ipv6_dynamic`, `wan_ipv6_static`, `wan_ipv6_pppoe`, `wan_ipv6_tunnel`, `wan_ipv6_protos` (connect/disconnect/renew/release), `wan_ipv6_pass` (write) |
| Status | `status_ipv4`, `wan_ipv4_status`, `wan_ipv6_status`, `wan_autodetect` (detect), `wan_retrieve_ipv4_pppoe` |

### Wireless — `/admin/wireless` (14)

| Form | Operations |
| --- | --- |
| `wireless_2g`, `wireless_5g` | read, write — SSID, `channel`, `current_channel`, `htmode`, `hwmode`, `encryption`, `psk_key`, `psk_cipher`, `hidden`, `isolate`, `airtime_fairness`, `disabled` |
| `guest_2g`, `guest_5g`, `guest_6g` | read, write — per-band guest config: `enable`, `ssid`, `encryption`, `psk_key`, `psk_cipher`, `psk_version`, `hidden`, `disabled`, `redirect`, `redirect_url`, `authentication_*` |
| `guest` | read, write — guest permissions only: `access`, `isolate` |
| `guest_2g5g` | read (unprefixed) / write (**prefixed**: `guest_2g5g_psk_key`, `guest_2g_enable`, …) — merged view of the guest bands |
| `guestnetwork_bandwidth_ctrl`, `guestnetwork_effectivetime_ctrl` | read, write — per-band guest rate limits and an active-hours schedule |
| `statistics` | load — per-client `rxpkts`, `txpkts`, `type`, `encryption` |
| `wireless_addition_setting` | read, write — `beacon_int`, `dtim_period`, `frag`, `rts`, `shortgi` |
| `wireless_schedule` | read, write |
| `region` | read, write — `country`, capability flags |
| `smart_connect` | read, write (WPS) |
| `ofdma`, `ofdma_mimo`, `twt` | read, write |
| `mlo_host` | read, write (Wi-Fi 7 multi-link) |
| `portal_content` | read, write (guest captive portal) |
| `wireless` | read — **rejected as `no such callback`** standalone; likely needs a radio/index parameter |

### Sharing, filtering and forwarding

| Module | Form | Operations |
| --- | --- | --- |
| `/admin/access_control` (6) | `enable`, `mode` | read, write — the parental-control / MAC-filter master switch |
| | `white_devices`, `white_list`, `black_devices`, `black_list` | load, block, access |
| `/admin/imb` (4) | `setting` | read, write |
| | `bind_list`, `arp_list` | load, bind |
| | `client_list` | read |
| `/admin/nat` (8) | `setting`, `alg`, `dmz` | read, write |
| | `vs` (virtual server), `pt` (port trigger), `fr6`, `client_list`, `client_list_v6` | load, read |
| `/admin/upnp` (2) | `enable` | read, write |
| | `service` | load — UPnP-mapped rules |
| `/admin/dhcps` (3) | `setting` | read, write — pool range and lease time |
| | `reservation` | load, insert, update, remove |
| | `client` | load — active leases |
| `/admin/iptv` (2) | `setting` (read, write, change), `udp_proxy_setting` (read, write) | |
| `/admin/ffs` (1) | `config` | read, write — USB file sharing (likely) |
| `/admin/wol` (1) | `device` | load, request, `wakeup` |

### VPN

| Module | Form | Operations |
| --- | --- | --- |
| `/admin/vpn` (7) | `enable` | read, write |
| | `ovpn` | read, write, release |
| | `server` | load, connected_status, file_check |
| | `vpn_user_list` | load, insert, update, remove |
| | `vpn_user_devices` | load |
| | `thirdvpn` | get_server_list, get_detail, get_ping, cloud_check, nordvpn_login, surfshark_login, enable_server, insert, modify, update, update_config, verify |
| | `wireguard` | read |
| `/admin/openvpn` (3) | `config` | read, write |
| | `openvpn_cert` | check, generate |
| | `export` | read — downloads the client config |
| `/admin/pptpd` (2) | `config` | read, write |
| | `accounts` | load |
| `/admin/wireguard` (2) | `config` | read, write, renew, `wg_status` — **read returns `private_key`** |
| | `account` | load, get_default, check_collision, export, renew |
| `/admin/l2tpoveripsec` (1) | `config` | read |
| `/admin/vpnconn` (1) | `config` | list, disconnect |

### Remote management, cloud and mesh

| Module | Form | Operations |
| --- | --- | --- |
| `/admin/administration` (6) | `account` | read, write — **changes the admin login** |
| | `remote` | read, write — WAN-side administration |
| | `https`, `mode`, `recovery` | read, write |
| | `local` | load |
| `/admin/security_settings` (1) | `new_enable` | read, write — firewall toggles incl. `wan_ping`, `lan_ping` |
| `/admin/cwmp` (1) | `cwmp_setting` | read, write — TR-069 ISP remote management |
| `/admin/cloud_account` (11) | `check_upgrade`, `check_device`, `check_internet`, `auto_update_remind`, `detect_upgrade_status`, `get_token`, `cloud_bind_status` | read |
| | `cloud_upgrade` | request, upgrade |
| | `remind` | read, write |
| | `user_login`, `cloud_unbind` | write |
| `/admin/ddns` (4) | `provider` | read |
| | `dyndns`, `noip` | read, refresh, login, logout |
| | `tplink` | load, insert, remove, bind, unbind |
| `/admin/yandex_dns` (3) | `enable`, `setting` | read, write |
| | `device` | load |
| `/admin/easymesh` (2) | `easymesh_enable` | read, write |
| | `search_slave` | start, stop, check |
| `/admin/easymesh_network` (5) | `mesh_sclient_list_all`, `ap_avoidance_enable_status` | read |
| | `mesh_sclient_detail` | read, write |
| | `change_satellite` | write |
| | `available_mesh_device_manage` | add_onboarding, link, unlink |
| `/admin/usbmodem` (2) | `modemset`, `isplist` | read |
| `/admin/privacy_policy` (1) | `fing_auth_state` | read, write |
| `/admin/qos` (1) | `update_database` | read |
| `/admin/smart_network` (12) | `qos`, `patrol_enable`, `client_speed_limit` | read, write |
| | `device_priority`, `patrol_devices`, `patrol_owner_list` | load |
| | `patrol_insights`, `patrol_limit`, `get_host_info`, `client_speed_limit` (read_max) | read |
| | `patrol_owner_block`, `patrol_owner_website_block` | write |
| | `game_accelerator` | request |
| `/admin/quick_setup` (3) | `quick_setup`, `ap_setup` | read, write |
| | `check_router` | read |
| `/admin/firmware` (6) | `auto_upgrade` | read, write |
| | `config` | read, check |
| | `upgrade` | read, write, fwup_check |
| | `config_multipart`, `save_upgrade` | read |
| | `slave_cmd` | slave_get_info, slave_get_upgrade_info, slave_upgrade_firmware |

### Setup and UI support

| Module | Form |
| --- | --- |
| `/admin/quick_setup` | `check_router`, `quick_setup`, `ap_setup` |
| `/admin/status?form=menu_status` | Reports `patrol_mark` only — not the navigation tree its name suggests (see finding 1) |
| `/locale` | `lang`, `country`, `list`, `multilang` (tp-link.com cloud, not LAN) |
| `/debug`, `/upgrade`, `/wan_error`, `/device_config`, `/domain_login`, `/domain_redirect`, `/blocking`, `/accessibility` | Cloud/telemetry endpoints reached over `https://www.tp-link.com`, **not** the router's CGI |

---

## 4. Findings worth acting on

1. **`menu_status` is not a feature tree — the real capability source is `wireless?form=region`.** `menu_status` answers `{patrol_mark: "0"}`. The region form is what reports what the unit accepts: `capability.channel_2g/5g/6g`, `hwmode_2g/5g`, `htmode_2g/5g`, plus `support_smart_connect` / `support_wireless_schedule` and whether `region_list` offers a country choice. This SDK exposes it as `GET /wifi/capabilities` / `wifi.get_capabilities()`. Note the shape traps: an unused 6G list arrives as `{}` not `[]`, and an empty `region_list` means the country is locked.
2. **Guest networking is three forms, not one, and the old wrapper hit the wrong one.** Reads of `admin/wireless?form=guest_2g` / `guest_5g` / `guest_6g` return the per-band guest config (`enable`, `ssid`, `encryption`, `psk_key`, `psk_cipher`, `psk_version`, `hidden`, `disabled`, `redirect*`) — this router reports 2.4G guest SSID `TP-Link` and 5G `GuestExample`, both disabled. Client isolation and guest LAN access are a *separate* form, `?form=guest`, returning just `access` and `isolate`. `guest_2g5g` is the merged view, and the UI writes it with **prefixed** field names (`guest_2g5g_psk_key`, `guest_2g_enable`, …). The SDK previously posted bare `enable`/`isolate` to `guest_2g5g`, which the router accepted while ignoring both fields — a silent no-op, since `success` says nothing about unrecognised parameters. Fixed in `set_guest()`.
3. **Several forms return secrets in cleartext**: `guest_2g5g` and `wireless_2g/5g` (`psk_key`), `wireless_addition_setting` (`psk_key`), `wireguard?form=config` (`private_key`), `openvpn?form=export`. Anything built on top of these must redact by default, as `GET /status` now does.
4. **Two reboot paths exist** (`/admin/reboot?form=set` and `/admin/system?form=reboot`); the SDK uses the latter.
5. **`nat?form=vs` answers an empty object** — port forwarding is reachable and cheap to model.
6. **No `statistics` form in the UI bundles, yet it works** — a reminder that static extraction under-reports; forms built from template strings or issued by the login page are invisible to it.
7. **One admin session, and the invalidation signal is `errorcode: "timeout"`, not an HTTP error.** Measured by logging in repeatedly and replaying older tokens: the previous stok starts answering `{"success": false, "errorcode": "timeout"}` with status 200. Any client that only watches for `permission denied` will treat a hijacked session as a data error. It also means this API and the web UI evict each other — opening the admin page logs the API out, and the next request logs the browser out.

---

## 5. How this was produced

1. Authenticated with the SDK and fetched `/webpages/index.html`, then recursively crawled every
   `import`/`src` reference under `/webpages/` (static assets need no stok; the `/cgi-bin/luci/;stok=`
   prefix 404s for them). 263 JS bundles, 29 misses — all locale files.
2. Extracted `"<module>?form=<form>"` literals, resolving minified `const` bindings to their
   nearest preceding assignment so operations land on the right form.
3. Cross-checked with read-only `operation=read|load` calls against this unit; nothing was written.

Counts are a **lower bound**: 42 top-level modules were seen as bare tokens in the bundles, and
any endpoint whose form name is assembled at runtime is invisible to a literal scan.
