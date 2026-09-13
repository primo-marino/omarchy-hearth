# Hearth

Remote-control Home Assistant from the Omarchy bar and Super-space menu.

v0.1 is a **bar pill + popup panel** (Weather / Tailscale family), not a Lovelace dashboard, not a camera viewer, and not Frigate.

Version **0.1.1**. Plugin id `hearth`.

## Install

```bash
omarchy plugin add <repo-url> --enable --yes
```

Or symlink this directory to `~/.config/omarchy/plugins/hearth/` (manifest at the root), then:

```bash
omarchy-shell shell rescanPlugins
omarchy plugin enable hearth --yes
```

The pill appears on the **right** of the bar immediately, dimmed, labelled **Hearth**. Open it to onboard.

`keepLoaded` service edits need:

```bash
omarchy restart shell
```

Other QML/JS files hot-reload.

## Credentials

Onboard asks for a Home Assistant URL (`homeassistant.local:8123`, a LAN IP, Tailscale name, or `*.ui.nabu.casa`) and either:

- a **long-lived access token** (HA Profile → Long-lived access tokens), or
- **username and password** only if `/auth/providers` includes `type === "homeassistant"`. Hearth mints a long-lived token named `Hearth` (3650 days) and does not keep the password.

Tokens live in `~/.config/omarchy/hearth/secrets.json` mode `0600`, written **only** by `helpers/ha_bridge.py`. Never in `shell.json`, QML `FileView`, or the Omarchy menu file. The helper re-chmods that file on start. Menu actions quote the CLI path and entity id. The helper accepts only `call_service` for a valid `entity_id` (no other HA WebSocket types).

HTTP is allowed after an explicit acknowledgement. `*.ui.nabu.casa` does not offer insecure TLS on first run. HA-on-a-subpath (`https://gw.example/ha/`) is not supported.

## Using it

- Pill: live solar W when Energy is configured, otherwise `N on`, otherwise `Hearth`.
- Panel tabs Recents / Favorites / Rooms (`1`/`2`/`3`). Star (`f` / ★). Settings (`s`).
- Fans with `percentage_step` (Office fan: Off / 1 / 2 / 3). Climate ± and HVAC. Media play/pause + volume.
- Header dropdown switches instances; **+** adds another. Only the active instance keeps a WebSocket.
- Disconnect: header shows **Reconnecting…** and a desktop notification.

## Super-space and CLI

Hearth rewrites **only** keys matching `/^hearth(\.|$)/` in `~/.config/omarchy/extensions/omarchy-menu.jsonc`. Parse failure → **no write**. Non-`hearth` keys survive. Comments in that file are lost on a successful write; put notes outside `hearth*` keys. Daily `.bak` beside the file.

Menu actions use the absolute path to `helpers/hearth`. Optional:

```bash
ln -s ~/.config/omarchy/plugins/hearth/helpers/hearth ~/.local/bin/hearth
```

| Command | Behavior |
| --- | --- |
| `hearth status` | JSON via IPC, or cache if the shell is down |
| `hearth act <entity_id> [service]` | `omarchy-shell hearth act`; REST fallback |
| `hearth favorite <entity_id>` | Toggle star |
| `hearth instance <id>` | Active instance |
| `hearth open [--room id]` | Summon panel |
| `hearth menu-sync` | Rewrite `hearth*` keys from cache |
| `hearth uninstall-menu` | Delete `hearth*` keys only |

Taking the pill off the bar disables the keepLoaded WebSocket. Menu `act` then uses REST if secrets still exist.

IPC is `omarchy-shell hearth <method>`, **not** `omarchy-shell shell call hearth`.

## Tests

```bash
cd helpers
python -m unittest test_rfc6455.py test_energy.py test_menu_sync.py
```

Manual review: [TESTPLAN.md](TESTPLAN.md).

## Non-goals (v0.1)

Lovelace clone, cameras, Frigate, HA subpaths, alarm panels that require a code, guessed energy sensors, multi-dashboard views.
