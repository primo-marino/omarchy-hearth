# Hearth

Remote-control Home Assistant from the Omarchy bar and Super-space menu.

v0.1 is a bar pill + popup panel (Weather / Tailscale family), not a Lovelace dashboard and not a Frigate viewer.

## Install

```bash
omarchy plugin add <repo-url> --enable --yes
```

Or drop this directory at `~/.config/omarchy/plugins/hearth/` (manifest at the root), then:

```bash
omarchy-shell shell rescanPlugins
omarchy plugin enable hearth --yes
```

The pill appears on the right of the bar immediately, dimmed, labelled **Hearth**. Open it to onboard.

## Credentials

Onboard asks for a Home Assistant URL (`homeassistant.local:8123`, a LAN IP, Tailscale name, or Nabu Casa URL) and either:

- a **long-lived access token** (HA Profile → Long-lived access tokens), or
- **username and password** (only if the instance advertises the `homeassistant` auth provider). Hearth mints a long-lived token named `Hearth` and does not keep the password.

Tokens live in `~/.config/omarchy/hearth/secrets.json` (mode `0600`). They are never written to `shell.json` or the Omarchy menu file.

## Notes

- Plugin id is `hearth`. `omarchy-shell shell summon hearth` opens the panel.
- Service IPC is `omarchy-shell hearth <method> …`, **not** `omarchy-shell shell call hearth …`.
- `keepLoaded` service code changes need `omarchy restart shell`. Other plugin files hot-reload.
- Taking the pill off the bar disables the WebSocket helper. Menu actions then use REST if secrets still exist.
- HTTP is allowed after an explicit acknowledgement. `*.ui.nabu.casa` does not offer insecure TLS on first run.
- HA-on-a-subpath (`https://gw.example/ha/`) is not supported in v0.1.
- Hearth rewrites `hearth*` keys in `~/.config/omarchy/extensions/omarchy-menu.jsonc` as JSON (comments in that file are lost).
