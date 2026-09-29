# TP-Link Archer AX12 API

Async Python SDK and FastAPI REST layer for the **TP-Link Archer AX12 v1** router — built from the
router's own web UI, endpoint by endpoint, and verified against a live device.

![checks](https://github.com/iambalaji-k/tplink-router-api/actions/workflows/ci.yml/badge.svg)
![license](https://img.shields.io/badge/license-MIT-green)
![python](https://img.shields.io/badge/python-3.11%20%7C%203.13-blue)
![firmware](https://img.shields.io/badge/firmware-AX12v1_1.10.2-orange)
![surveyed](https://img.shields.io/badge/surveyed-226%20endpoints-brightgreen)

- **Nothing guessed.** Every form name, verb and payload shape was recovered from the JavaScript the
  router ships, then re-checked against the device.
- **A real inventory.** [226 endpoints surveyed, 179 confirmed answering](docs/router-api-inventory.md),
  each labelled with what this firmware actually did.
- **Typed and checked.** Pydantic models, mypy and ruff clean, 76 mocked tests that need no router.

> Use this against equipment you own or administer. It can block devices, change Wi-Fi passwords and
> reboot the unit — see [Safety and privacy](#safety-and-privacy).

---

## Contents

[Install](#install) · [Quick start](#quick-start) · [SDK tour](#sdk-tour) · [REST API](#rest-api) ·
[Router API surface](#router-api-surface) · [Low-level access](#low-level-access) ·
[How this router behaves](#how-this-router-behaves) · [Safety and privacy](#safety-and-privacy) ·
[Development](#development) · [Survey tooling](#survey-tooling) · [Repository layout](#repository-layout)

---

## Install

Requires Python 3.11+. The router serves plain HTTP on the LAN, so run this from a network segment
you control.

```bash
git clone https://github.com/iambalaji-k/tplink-router-api.git
cd tplink-router-api

python -m venv venv
source venv/bin/activate                     # Windows: .\venv\Scripts\activate

pip install -e .                             # the SDK and its runtime dependencies
pip install pytest pytest-asyncio mypy ruff  # dev tools (not declared in pyproject.toml)
```

Create `.env` in the project root (already gitignored):

```env
TPLINK_HOST=192.168.0.1
TPLINK_PASSWORD=your_router_admin_password
```

---

## Quick start

```python
import asyncio
from tplink_modern import ArcherAX12

async def main():
    async with ArcherAX12(host="192.168.0.1", password="YOUR_PASSWORD") as router:
        await router.login()

        status = await router.status.get()
        print(f"LAN {status.lan.ipaddr}   WAN {status.wan.ipaddr}")
        print(f"CPU {status.system.cpu_usage * 100:.1f}%  "
              f"MEM {status.system.mem_usage * 100:.1f}%")

        for client in await router.clients.get_all():
            # wire_type is one of 'wired', '2.4G' or '5G'
            print(f"[{client.wire_type}] {client.hostname or '<unknown>'} {client.ipaddr}")

        # login() already verifies the session; get_status() doubles as the probe
        print(f"Session alive: {await router.keep_alive()}")

asyncio.run(main())
```

`cpu_usage` and `mem_usage` are ratios in `0.0–1.0`; every boolean on `RouterStatus` is derived from
the router's raw `"on"` / `"off"` strings. The context manager logs out and closes the session.
Runnable versions of these snippets live in [`examples/`](examples) and read credentials from `.env`.

---

## SDK tour

Resources hang off the client: `status`, `clients`, `wifi`, `network`, `vpn`, `nat`, `access`, `wol`,
`system`, `firmware`.

### Wi-Fi

```python
band = await router.wifi.get_2g()             # get_5g() for the other band
print(band.ssid, band.channel, band.htmode)

# Read-modify-write: omitted arguments keep their current value, so this only
# changes the SSID.
await router.wifi.set_wireless_band(band="2g", ssid="MyNetwork")

# Guest networking is per-band on this firmware, and client isolation is its own form.
await router.wifi.set_guest(enable=True, ssid="Guests", password="guest-pass-1", isolate=True)
print(await router.wifi.get_guest_band("2g"))
print(await router.wifi.get_statistics())

# Ask the router what it accepts before you write it.
caps = await router.wifi.get_capabilities()
```

### DHCP reservations

```python
# MAC addresses are normalised to the router's uppercase hyphenated form.
await router.network.add_dhcp_reservation(
    macaddr="00:11:22:33:44:55", ipaddr="192.168.0.99", name="NAS"
)
for res in await router.network.get_dhcp_reservations():
    print(res.macaddr, "->", res.ipaddr, f"({res.name})")

await router.network.delete_dhcp_reservation("00:11:22:33:44:55")
```

### Blocking and allowing devices

```python
for device in await router.access.devices("black"):
    print(device.name, device.macaddr, device.band, device.is_guest)

# Only devices the router has already seen can be listed; it needs the row it
# reported, which is why block() looks the MAC up first.
await router.access.block("AA-BB-CC-DD-EE-01")
await router.access.set_enabled(True)          # access control is off until you turn it on
print(await router.access.blocked())

await router.access.set_mode("white")          # allow-list mode
await router.access.allow("AA-BB-CC-DD-EE-02")
await router.access.unblock("AA-BB-CC-DD-EE-01")
await router.access.set_enabled(False)
```

> Enabling access control in `black` mode cuts the listed device off the network; in `white` mode
> anything absent from the allow list loses connectivity. Test with a device you can reach over
> cable. The router protects one MAC of its own (`host_mac`) — usually the machine that configured
> it.

### VPN, DMZ, port forwarding, Wake-on-LAN

```python
await router.vpn.set_openvpn(OpenVpnConfig(enable=False))
print(len(await router.vpn.get_connections()))

await router.nat.set_dmz(enable=True, ipaddr="192.168.0.50")
print(await router.nat.virtual_servers())

await router.wol.add("AA-BB-CC-DD-EE-03", "study-pc")
await router.wol.wake(name="study-pc")
print(await router.wol.max_rules())            # the `others` limit the router reports
```

> `await router.system.reboot()` restarts the router and drops the session.
> [`examples/reboot.py`](examples/reboot.py) asks for confirmation first.

---

## REST API

The FastAPI app exposes the same SDK over HTTP, sharing one router client and coordinating the
connection lifespan automatically.

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

The server logs in at startup. A failed startup login is logged as a warning rather than fatal: the
client re-authenticates transparently on the first request, and until then endpoints answer `503`.

### Status and devices

| Method | Route | What it gives you |
| --- | --- | --- |
| `GET` | `/status` | CPU, RAM, LAN, WAN, both Wi-Fi bands, guest state, clients. PSKs redacted unless `?include_secrets=true` |
| `GET` | `/clients` | Every connected wired and wireless device |
| `GET` | `/firmware` | Whether the router thinks an upgrade is pending (a count, not a version) |

### Network

| Method | Route |
| --- | --- |
| `GET` | `/network/lan`, `/network/wan` |
| `GET` `POST` `DELETE` | `/network/dhcp/reservations`, `/network/dhcp/reservations/{macaddr}` |

### Wi-Fi

| Method | Route |
| --- | --- |
| `POST` | `/wifi/config` — SSID, password, channel, HT mode for the 2.4G or 5G band |
| `POST` | `/wifi/guest` — guest toggle, SSID, password, isolation; omitted fields keep their values |
| `GET` | `/wifi/statistics` — packets sent and received per wireless client |
| `GET` | `/wifi/capabilities` — channels, band widths and modes this unit accepts in its current country; validate a `/wifi/config` write against this |

### Access control

| Method | Route |
| --- | --- |
| `GET` `POST` | `/access-control` — enabled flag, list mode (`black`/`white`), protected host MAC |
| `GET` | `/access-control/devices`, `/access-control/blocked`, `/access-control/allowed` |
| `POST` `DELETE` | `/access-control/block`, `/access-control/block/{macaddr}` |
| `POST` `DELETE` | `/access-control/allow`, `/access-control/allow/{macaddr}` |

### Forwarding, VPN, WoL, system

| Method | Route |
| --- | --- |
| `GET` `POST` | `/nat/dmz` |
| `GET` `DELETE` | `/nat/virtual-servers`, `/nat/virtual-servers/{key}` |
| `GET` `DELETE` | `/nat/port-triggers`, `/nat/port-triggers/{key}` |
| `GET` `POST` | `/vpn/openvpn`, `/vpn/pptp` |
| `GET` | `/vpn/connections` |
| `GET` `POST` `DELETE` | `/wol/devices`, `/wol/devices/{macaddr}` |
| `POST` | `/wol/wake` |
| `POST` | `/reboot` |

### Error mapping

A write answers `{"success": true}`; a refused write never looks like a success — the router's own
`errorcode` comes back in the body.

| HTTP | Meaning |
| --- | --- |
| `400` | Bad arguments (unknown band, malformed body) |
| `404` | Nothing to act on (an unknown DHCP reservation, an unseen MAC) |
| `501` | This firmware does not implement the form (`errorcode: "no such callback"`) |
| `502` | The router refused or failed the request; body carries `errorcode` |
| `503` | Router client not initialised (startup login pending, or shutting down) |

### OpenAPI documentation

With the server running: **Swagger UI** at `/docs`, **ReDoc** at `/redoc`.

---

## Router API surface

The router's admin UI is a Vue app that posts form-encoded requests to a `luci` CGI. This project
recovered that surface from the shipped JavaScript, then probed it read-only against the device.

**226 endpoints across 50 modules**, of which on firmware AX12v1_1.10.2:

| Outcome | Forms |
| --- | --- |
| Answered a read-only request | **179** |
| No handler (`no such callback` for every approved verb) | 18 |
| Handler exists but wants an argument | 4 |
| Handler exists and named a blocking condition | 3 |
| Declined with no reason given | 1 |
| Answers non-JSON (file download or HTTP 500) | 4 |
| Not served at all (HTTP 404) | 4 |
| Not probed — the form name is itself an action | 13 |

[`docs/router-api-inventory.md`](docs/router-api-inventory.md) holds every form, the verbs the UI
applies to it, the response field names, and the shape traps — empty tables answer `{}` rather than
`[]`; capacity limits arrive in an `others` sibling and **only** on `load`; several forms return
Wi-Fi keys in cleartext.

[`tplink_modern/endpoints.py`](tplink_modern/endpoints.py) is that same table as machine-readable
constants, generated from the survey reports, and
[`tests/test_endpoints_inventory.py`](tests/test_endpoints_inventory.py) fails if the document, the
generated table and the SDK's own call sites ever disagree. The SDK and REST layer model about two
dozen of the 226, including device block/allow and guest credentials.

---

## Low-level access

Three primitives sit under everything, useful for forms the SDK does not wrap yet:

| Method | Request it sends |
| --- | --- |
| `await router.read(path, form, **kw)` | `POST /cgi-bin/luci/;stok=<stok>/{path}?form={form}` with `operation=read` |
| `await router.write(path, form, **kw)` | same, with `operation=write` |
| `await router.api(path, form, operation, **kw)` | same, with any operation (`load`, `insert`, `remove`, `list`, …) |

Responses are the router's raw JSON dict (`{"success": bool, "data": ..., "errorcode": ...}`);
`data` is unwrapped by the higher-level resources.

---

## How this router behaves

Things that were not obvious, written down so they are not discovered the hard way:

- **One admin session, total.** A new login replaces the old `stok`, and requests carrying the
  discarded token answer **HTTP 200** with `errorcode: "timeout"` — not a 401. Opening the web UI
  logs this API out and vice versa. The client detects that and re-authenticates, with a lock so
  concurrent requests share a single re-login instead of stampeding, since parallel logins would
  otherwise knock each other out. Do not run two copies of the server against one router.
- **`success: true` says nothing about unrecognised parameters** — they are silently ignored. This
  one cost real time: a guest-Wi-Fi helper posted bare `enable` / `isolate` to the merged
  `guest_2g5g` form, which wants prefixed names. The router returned success and changed nothing.
  Verify writes by reading them back, and never assume a read schema equals the write schema.
- **The refusal field has four spellings** (`errorCode`, `error`, `error_code`, `errorcode`). The SDK
  reads all four, in the order the router's own UI normalises them.
- **Empty list forms answer `{}`, not `[]`,** and an unused capability list arrives as `{}` too.
- **The password handshake** is `login?form=keys` → `form=auth` → `form=login`, with the password
  RSA PKCS#1 v1.5 encrypted against a 1024-bit modulus the device supplies.
- **Errors are surfaced, not swallowed.** Where the code once caught every exception, it now tolerates
  only the specific failure: `vpn.get_connections()` used to turn any error into "nobody connected",
  so it now accepts only `FeatureUnavailableError` (a unit without that VPN server) and lets anything
  else propagate. `keep_alive()`, `logout()` and the server's startup/shutdown handlers narrow to
  router and transport errors for the same reason.

---

## Safety and privacy

Read these before exposing anything beyond `127.0.0.1`:

- **The REST API has no authentication of its own.** Anyone who can reach the port holds router
  admin rights, including `POST /reboot` and Wi-Fi or VPN changes. Bind to localhost, or put your
  own auth in front of it.
- **Wi-Fi keys are redacted from `GET /status` by default** (`"***redacted***"`), because the router
  returns them inside its own status payload. Pass `?include_secrets=true` to see them. The SDK
  deliberately still hands back real keys: `wifi.set_wireless_band()` re-sends the current PSK on
  every write, so masking at that layer would let a redacted placeholder overwrite your password.
  `tplink_modern.redact_secrets()` is exported if you serialise `RouterStatus` yourself.
- **Plain HTTP on the LAN.** If you pass an `https://` host, certificates are verified by default;
  `ArcherAX12(host, password, timeout=10.0, verify=True)` exposes both, so turn `verify` off
  deliberately for a self-signed device rather than silently trusting a bad certificate.
- **Not every write path is verified.** The live survey sent only `read`, `load` and `list`. Check the
  inventory's *Not verified* section before trusting an unexercised write.
- **Test fixtures use synthetic MACs and hostnames**, never identifiers from a real network.

---

## Development

The suite mocks the router's HTTP layer, so no router needs to be reachable:

```bash
pytest -q          # 76 mocked tests; the live module self-skips
mypy .             # clean across 44 source files
ruff check .       # clean
```

[`ci.yml`](.github/workflows/ci.yml) runs all three on Python 3.11 and 3.13. The lint rule set CI
enforces is pinned in `pyproject.toml`, so a ruff upgrade cannot quietly move the bar.

| Test file | Covers |
| --- | --- |
| `tests/conftest.py` | Supplies dummy `TPLINK_*` env vars so `app.py` imports without a real `.env` |
| `tests/test_login.py` | RSA login handshake, wrong-password failure, transparent re-auth on `permission denied` |
| `tests/test_features.py` | SDK-level DHCP reservations, Wi-Fi band writes, VPN config, wireless statistics |
| `tests/test_api.py` | Every REST endpoint of `app.py` against a mocked router: status codes, request bodies sent to the device, PSK redaction, concurrent re-auth, `400`/`404`/`501`/`502`/`503` handling, OpenAPI route coverage |
| `tests/test_error_field.py` | The four refusal-field spellings |
| `tests/test_inventory_extractor.py` | The URL shapes the bundles actually build |
| `tests/test_ui_routes.py` | Route table, menu tree, page → form map |
| `tests/test_endpoints_inventory.py` | Doc, generated table and SDK call sites agree |
| `tests/test_live.py` | Opt-in checks against a real Archer AX12 |

### Live tests

`tests/test_live.py` talks to the router in your `.env` — it issues reads and logins only, and never
calls a write or reboot endpoint. It is skipped unless you ask for it:

```bash
TPLINK_LIVE=1 pytest -m live
```

Each read route's response is validated against its declared Pydantic model, so a firmware change
that alters a payload shows up as a failure rather than a wrong value downstream. One test also logs
in from a second client to evict the server's `stok` — the same thing the web admin page does — and
asserts that two concurrent requests both recover. **Running it will log out any router web session
you have open.**

---

## Survey tooling

Everything in `tools/inventory/` is reproducible, and read-only by construction. The crawled bundles
and the JSON reports they produce live under `.cache/` — gitignored and regenerable.

| Tool | What it does |
| --- | --- |
| `extract_ui_inventory.py` | Recovers endpoint URLs from the router's own bundles, resolving template literals, `?form=a&form=b` batches, variable suffixes and `join("&")` arrays |
| `jstokens.py` | The JS literal and template scanner underneath it |
| `ui_routes.py` | Reads the Vue router table and menu tree; maps each page to the forms it can reach |
| `probe_live.py` | Asks every form with `read` / `load` / `list` only; records schemas, masks secret-named values, skips action-shaped form names |
| `form_models.py` | Recovers row field names for tables the router returned empty, from the UI's own column and default-row definitions — an inference, never a response |
| `sdk_calls.py` | Scans this package's call sites, so a form no bundle names still gets verified |
| `fetch_missing_bundles.py` | Audits imports that were never downloaded; plain GETs, so it cannot evict your session |
| `gen_endpoints.py` | Generates `endpoints.py` and the inventory doc's module table |

```bash
python -m tools.inventory.extract_ui_inventory
python -m tools.inventory.ui_routes
python -m tools.inventory.probe_live                      # needs a reachable router
python -m tools.inventory.gen_endpoints --markdown .cache/ax12-ui/doc-table.md
```

---

## Repository layout

```text
tplink-router-api/
├── app.py                  # FastAPI REST server
├── pyproject.toml          # Package config, pinned lint rules, test settings
├── LICENSE                 # MIT
├── .github/workflows/      # CI: ruff, mypy, pytest on 3.11 and 3.13
├── docs/
│   └── router-api-inventory.md   # Full surveyed API: 50 modules / 226 endpoints
├── examples/               # Runnable SDK examples (login, status, devices, reboot)
├── tests/                  # Mocked unit tests + opt-in live checks
├── tools/inventory/        # The survey tooling that produced the inventory
└── tplink_modern/          # The SDK
    ├── client.py           # ArcherAX12 high-level client
    ├── auth.py             # RSA-based login handshake
    ├── crypto.py           # RSA PKCS#1 v1.5 utilities
    ├── session.py          # Session, stok and transparent re-auth
    ├── exceptions.py       # Typed RouterError hierarchy
    ├── models.py           # Pydantic schemas for type safety
    ├── endpoints.py        # Generated inventory constants
    └── resources/          # base, access, clients, firmware, nat, network,
                            # status, system, vpn, wifi, wol
```

---

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

Not affiliated with, endorsed by, or sponsored by TP-Link. Reverse-engineered from the firmware's own
client code for interoperability. Use against equipment you own or administer; operating on a device
you are not authorised to manage may be unlawful in your jurisdiction.
