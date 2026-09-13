# Hearth v0.1 review test plan

Run after `omarchy restart shell`. Plugin path is `~/18019-frigate/hearth` (symlink `~/.config/omarchy/plugins/hearth`). HA instance **3804-HA** at `http://192.168.18.9:8123`.

Automated: `cd helpers && python -m unittest test_rfc6455.py test_energy.py test_menu_sync.py`

---

## 1. Office fan (your example)

Entity: `fan.0x881a14fffe41c112` — currently named **Office Fan Light**, area **Office**. HA reports `percentage_step` ≈ 33.3, so the row must be **Off · 1 · 2 · 3** (not a binary toggle).

1. Open the Hearth pill → **Rooms** → **Office**.
2. Confirm the fan row shows the current HA name, not the raw entity id.
3. Note the selected chip (expect **1** if HA still shows 33%).
4. Tap **Off**. Fan stops. Chip is Off. HA state is `off`.
5. Tap **1**, then **2**, then **3**. Motor matches; HA `percentage` ≈ 33 / 67 / 100.
6. From Super-space: **Hearth → Rooms → Office → Office Fan Light** should be a **submenu** with Off / Speed 1 / 2 / 3 (not a single toggle).
7. Keyboard in the panel: `j`/`k` moves the highlight, Enter activates, `/` filters by name.
8. **Rename in HA:** Settings → Devices → Office fan → rename to something obvious (e.g. `Office ceiling fan`).
   - Within ~1s the Hearth row label must change (live `state_changed` / registry snapshot).
   - Super-space label must update after the 250 ms menu sync (open Super-space again).
   - Recents / Favorites, if starred, show the new name too.
9. Rename it back if you want.

Pass if you never need to restart the shell for the new name, and Off/1/2/3 all work.

---

## 2. Smoke: bar + panel

| Step | Expect |
| --- | --- |
| Pill visible on the right, not hidden when label is empty | Always “Hearth”, `N on`, or live W |
| Click pill | Panel opens, no extra scroll-only banner |
| `omarchy-shell hearth ping` | `ok` |
| `omarchy-shell shell summon hearth` | Same panel |

---

## 3. Energy

Today’s Envoy numbers are **not** zero (solar tens of kWh, grid in/out). Strip under the header: solar today, grid in, grid out. Pill may show ~kW while producing. Hide the strip only if Energy prefs fail.

---

## 4. Lights / rooms / stars

1. Toggle a kitchen or office light. Optimistic flip, then HA matches.
2. Star it. **Favorites** tab lists it.
3. **Recents** lists the last act (cap 12).
4. Keys: `1` Recents, `2` Favorites, `3` Rooms, `s` Settings, `f` star focused/first row, `r` refresh, Esc back/close.

---

## 5. Climate / media

If present: climate `−`/`+` and HVAC chip; media play/pause and volume. Skip if you have none.

---

## 6. Settings

Re-pick rooms, Save rooms, replace token (optional), **Add instance** (`+` in header too), two-click **Remove instance**.

---

## 7. Super-space menu

After restart, Super-space → **Hearth**. Rooms/favorites/recents present. Non-`hearth` keys in `~/.config/omarchy/extensions/omarchy-menu.jsonc` unchanged. A `.bak` appears next to that file on the first write of the day.

CLI: `~/.config/omarchy/plugins/hearth/helpers/hearth status` prints JSON. `hearth act light.<id>` toggles via IPC.

---

## 8. Disconnect / reconnect

Stop HA or unplug LAN briefly. Pill dims. Desktop notification **Hearth disconnected**. Header meta **Reconnecting…**. Restore network; panel comes back without a shell restart.

---

## 9. Rename (general)

Same as the office fan: change `friendly_name` in HA. Plugin and menu pick it up without restart. Entity **id** does not change (HA does not rename `fan.0x881a…` when you change the display name).

---

## Non-goals (do not fail the review)

Cameras, Lovelace, Frigate, HA subpaths, climate schedules, alarm with a code, guessed energy sensors.
