# Hearth

Remote-control Home Assistant from the Omarchy bar and Super-space menu.

v0.1 is a **bar pill + popup panel** (same family as Weather and Tailscale), not a Lovelace dashboard, not a camera viewer, and not Frigate.

Version **0.1.2**. Plugin id `io.github.primo-marino.hearth`.

Plugins run unsandboxed inside `omarchy-shell`. Read this README before enabling.

## Install

```sh
omarchy plugin add https://github.com/primo-marino/omarchy-hearth.git --enable
```

The pill appears on the **right** of the bar, labelled **Hearth** (dimmed until Home Assistant is connected). Click it to onboard.

Needs **Python 3** on PATH (stdlib only; no pip packages). Service code changes need `omarchy restart shell`; other QML/JS files hot-reload.

## Usage

- **Click** the pill to open or close the panel. **Escape** closes it.
- The pill is a house mark. When lights, switches, or fans are on it shows `N on`. Hover for the house name and, when Energy is configured, live power.
- Opening the panel lands on **N on** when something is on. `1` / `2` / `3` are Recents / Favorites / Rooms. `o` returns to what is on. Star (`f`). Settings (`s`). Filter (`/`).
- Fans with `percentage_step` get Off / 1 / 2 / 3. Climate ± and HVAC. Media play/pause + volume.
- Header dropdown switches Home Assistant instances; **+** adds another. Only the active instance keeps a WebSocket.
- Disconnect: header shows **Reconnecting…** and a desktop notification.

```sh
omarchy-shell shell summon io.github.primo-marino.hearth '{}'
omarchy-shell shell hide io.github.primo-marino.hearth
```

## Configure

```sh
omarchy bar move io.github.primo-marino.hearth --section right
```

Onboard asks for a Home Assistant URL (`homeassistant.local:8123`, a LAN IP, Tailscale name, or `*.ui.nabu.casa`) and either:

- a **long-lived access token** (HA Profile → Long-lived access tokens), or
- **username and password** only if `/auth/providers` includes `type === "homeassistant"`. Hearth mints a long-lived token named `Hearth` (3650 days) and does not keep the password.

HTTP is allowed after an explicit acknowledgement. `*.ui.nabu.casa` does not offer insecure TLS on first run. Home Assistant on a URL subpath (`https://gw.example/ha/`) is not supported.

## Credentials and files

Tokens live in `~/.config/omarchy/hearth/secrets.json` mode `0600`, written **only** by `helpers/ha_bridge.py`. They are never stored in `shell.json`, QML, or the Omarchy menu file.

The helper accepts only `call_service` for a valid `entity_id` (no other Home Assistant WebSocket types).

## Super-space menu

Hearth **rewrites only keys matching** `/^hearth(\.|$)/` in `~/.config/omarchy/extensions/omarchy-menu.jsonc` so rooms and favorites show up under Super-space. That is an explicit menu integration, not a silent rewrite of the rest of the file:

- Parse failure → **no write**
- Keys that are not `hearth*` are left alone
- Comments on rewritten `hearth*` keys are lost; keep notes off those keys
- A daily `.bak` is written beside the file
- `hearth uninstall-menu` deletes `hearth*` keys only

| Command | Behavior |
| --- | --- |
| `helpers/hearth status` | JSON via IPC, or cache if the shell is down |
| `helpers/hearth act <entity_id> [service]` | `omarchy-shell io.github.primo-marino.hearth act`; REST fallback |
| `helpers/hearth favorite <entity_id>` | Toggle star |
| `helpers/hearth instance <id>` | Active instance |
| `helpers/hearth open [--room id]` | Summon panel |
| `helpers/hearth menu-sync` | Rewrite `hearth*` keys from cache |
| `helpers/hearth uninstall-menu` | Delete `hearth*` keys only |

IPC is `omarchy-shell io.github.primo-marino.hearth <method>`.

Taking the pill off the bar disables the keepLoaded WebSocket. Menu `act` then uses REST if secrets still exist.

## Remove

```sh
omarchy plugin remove io.github.primo-marino.hearth
~/.config/omarchy/plugins/io.github.primo-marino.hearth/helpers/hearth uninstall-menu
```

`omarchy plugin remove` does **not** delete credentials. To drop them too:

```sh
rm -rf ~/.config/omarchy/hearth ~/.cache/omarchy/hearth
```

## Tests

```sh
cd helpers
python -m unittest test_rfc6455.py test_energy.py test_menu_sync.py test_fan_math.py
```

## Non-goals (v0.1)

Lovelace clone, cameras, Frigate, HA subpaths, alarm panels that require a code, guessed energy sensors, multi-dashboard views.

## License

MIT. See [LICENSE](LICENSE).

## Support

See [SUPPORT.md](SUPPORT.md) for expectations (best-effort, no SLA).
