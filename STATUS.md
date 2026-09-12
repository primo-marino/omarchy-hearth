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

## Not done yet (PRs 4–9)

- Entity allow-list / 5000 cap applied as hide-filters (snapshot currently dumps registries raw, capped at 5000).
- Room device rows, favorites, recents, toggles (PR 5a).
- Climate/media/alarm (PR 5b).
- Energy strip (PR 6).
- Super-space menu merge (PR 7).
- Multi-instance switcher UI (data model already uses `instances[]`).
- Polish / tag 0.1.0.

## Commands

```bash
cd ~/18019-frigate/hearth
python -m unittest helpers/test_rfc6455.py
omarchy-shell hearth ping
omarchy-shell shell summon hearth
omarchy plugin disable hearth     # if you want the pill gone
```

`keepLoaded` service edits need `omarchy restart shell`.
