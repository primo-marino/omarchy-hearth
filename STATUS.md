# Overnight status — 2026-09-11

Hearth is **installed and enabled** on this Omarchy session.

- Plugin id `hearth` is a third-party `service` + `bar-widget` on the **right** of the bar.
- `omarchy-shell hearth ping` returns `ok`.
- Checkout is this folder, symlinked to `~/.config/omarchy/plugins/hearth`.
- Open the dim **Hearth** pill to onboard (URL + token or username/password).

## Done (PRs 1–3, combined)

1. Scaffold: `manifest.json`, `BarWidget.qml` (always-visible pill, Weather summon contract, **no** `visible: label !== ""`), `Panel.qml` (no `IpcHandler`), `Service.qml` (sole `IpcHandler { target: "hearth" }`).
2. Helper: `helpers/rfc6455.py` + `helpers/ha_bridge.py` (`python3 -u` JSON-lines). Tests in `helpers/test_rfc6455.py` (9 passing): 101 upgrade, 2 MiB accept, >32 MiB reject, no extensions, provider envelope, token redact.
3. Onboard: name, URL, token vs password (password only if `/auth/providers` has `type === "homeassistant"`), HTTP ack, insecure TLS, Test connection, room checklist, Save. Secrets written only by the helper at `~/.config/omarchy/hearth/secrets.json` `0600`.

## Done (PR 4–9 / v0.1.0)

4. Allow-list hide-filters in `js/Entities.js` (config/diagnostic/hidden/disabled, 5000 cap, area via device parent). Snapshot still written by the helper.
5a. Connected panel: Recents / Favorites / Rooms tabs (`1`/`2`/`3`), star (`f` / ★), last-12 recents in `state.json`, cover Open/Close/Stop + lock Lock/Unlock, optimistic toggles with 2s revert, Settings (`s`) to re-pick rooms, replace token, remove instance. Pill still shows `N on`.
5b. Climate ± setpoint + HVAC cycle; media play/pause + volume; vacuum / remote / humidifier / water_heater / lawn_mower / alarm. Hide alarm if a code is required; hide rows when `get_services` lacks the action.
6. Energy strip from `energy/get_prefs` + today's `recorder/statistics_during_period`. Nested and flat grid. Hide on any failure / empty sources / zero ids. Pill uses live W when a power statistic id is an entity. Tests in `helpers/test_energy.py`.

7. Super-space menu: fail-closed JSONC merge of `hearth*` keys, daily `.bak`, CLI `helpers/hearth`. Tests in `helpers/test_menu_sync.py`.
8. Header instance dropdown + **+** add-instance onboard. Switching disconnects the previous WS and connects the new one.
9. Reconnecting copy, desktop notify on drop, registry snapshot so HA renames land live, fans Off/1/2/3, README + TESTPLAN.md. Manifest already `0.1.0`.

## Review

See [TESTPLAN.md](TESTPLAN.md). Office fan `fan.0x881a14fffe41c112` (Off + 3 speeds) and HA rename are called out there.

Bug scrub (post-0.1.0): HA `call_service` waits for result; fan revert; instance dropdown no longer reconnects the same house; menu-sync waits for the tree file; `/` filter; `j`/`k` cursor; light brightness slider; Super-space fan Off/1/2/3; energy refresh at midnight; waiters cleared on disconnect.

After `omarchy restart shell`, you should not need further code drops for the review.

## Commands

```bash
cd ~/18019-frigate/hearth
cd helpers && python -m unittest test_rfc6455.py test_energy.py test_menu_sync.py
omarchy-shell hearth ping
omarchy-shell shell summon hearth
omarchy plugin disable hearth     # if you want the pill gone
```

`keepLoaded` service edits need `omarchy restart shell`.
