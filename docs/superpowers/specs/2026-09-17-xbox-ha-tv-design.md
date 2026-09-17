# Xbox TV for Home Assistant

Date: 2026-09-17  
Status: Ready for review  
Repo: `xbox-ha`

## Problem

Apple Home only treats a Home Assistant media player as a Television when all of the following are true:

- The entity is a `media_player`
- `device_class` is `tv` (or `receiver`)
- HomeKit exposes that entity as its **own accessory** (`mode: accessory`), not as part of the existing bridge

Home Assistant’s built-in Xbox integration talks to Xbox Network in the cloud. It does not use `device_class: tv`, so Apple Home shows switches instead of a TV. That blocks Apple Home automations that need a Television accessory (power and input/source).

`homebridge-xbox-tv` already does this for Homebridge: local SmartGlass control plus Microsoft web API for apps/games, advertised as a HomeKit Television. This project brings the same outcome into Home Assistant without replacing the user’s existing HomeKit Bridge.

## Goals (v1)

- Control an Xbox Series S or Series X from Home Assistant as a Television media player.
- Power on/off using the local SmartGlass protocol (IP + Xbox network device ID).
- Switch sources in Home and Home Assistant: Dashboard, installed apps, installed games.
- Appear in Apple Home as a TV via Home Assistant’s HomeKit integration in accessory mode, so it can be used in Apple Home automations.
- Leave the user’s existing HomeKit Bridge unchanged.

## Non-goals (v1)

- Volume, mute, Apple Remote key handling, extra switches, sensors, MQTT, or REST servers (homebridge-xbox-tv extras).
- Xbox One support (may work, not a v1 requirement).
- Friends, clips, screenshots, or other cloud Xbox features already covered by HA core `xbox`.
- Embedding a second HomeKit/HAP stack inside this integration.
- Changing or wrapping the built-in `xbox` integration.

## Success criteria

v1 is done when:

1. Installing the custom component and completing config flow produces one `media_player` with `device_class: tv`.
2. Turning that entity on/off wakes or shuts down the console (Instant-on must be enabled on the Xbox).
3. `source_list` includes Dashboard plus installed apps and games; selecting a source launches it on the console.
4. Following the documented HomeKit accessory setup, Apple Home shows a Television named after the console, with power and input selection.
5. Apple Home automations can use that Television (for example: when the Xbox turns on, or set the Xbox input to an app).

## Architecture

Home Assistant custom integration `xbox_tv` (HACS-style, domain chosen so it does not collide with core `xbox`).

```
Apple Home  --HAP-->  HA HomeKit accessory (mode: accessory, this entity only)
                              |
                              v
                     media_player.<slugified_name>
                              |
                              v
                     DataUpdateCoordinator
                     /                    \
          SmartGlassClient           XboxWebApiClient
          (LAN, ~10s poll)           (OAuth, catalog ~15 min)
                |                            |
                v                            v
         Xbox Series S|X              Xbox Network
```

The integration never speaks HomeKit itself. It only produces a correctly typed media player. Pairing stays in Home Assistant’s HomeKit integration, next to the user’s existing bridge.

## Components

| Unit | Responsibility | Depends on |
| --- | --- | --- |
| Config flow | Collect name, host, Xbox network device ID; Microsoft OAuth; store tokens in the config entry | HA config entries |
| `SmartGlassClient` | Async LAN client: power on/off, reachable/on/off, current title AUMID | Host + live ID |
| `XboxWebApiClient` | OAuth refresh, installed titles, launch by product ID, map AUMID → friendly name | Microsoft tokens |
| Coordinator | Merge local state + catalog; poll SmartGlass ~10s; refresh titles ~15 min | Both clients |
| `XboxTvMediaPlayer` | HA `media_player` with `device_class: tv`, power, `source` / `source_list` | Coordinator |
| README | Console prerequisites + dedicated HomeKit accessory YAML/UI steps | None |

Python package layout:

```
custom_components/xbox_tv/
  __init__.py
  manifest.json
  const.py
  config_flow.py
  coordinator.py
  media_player.py
  smartglass.py
  xbox_api.py
  strings.json
  translations/en.json
```

HACS metadata (`hacs.json`) and a root README live at the repo root.

### SmartGlass client (in-repo)

v1 implements a small async client in `smartglass.py` for power, presence, and current title only. It does not vendor the full OpenXbox stack.

Behavior:

- **Power on:** Send the SmartGlass power-on / wake packet addressed to the Xbox network device ID (the same LAN wake used by the Xbox app and homebridge-xbox-tv). Instant-on is required.
- **Power off:** Open a SmartGlass session and send power-off. If the session cannot be opened, treat the console as already off.
- **State:** If SmartGlass reports powered-on, state is `on`. If there is no reply within 5 seconds on a poll, state is `off`. Sleeping consoles look like this; Apple Home automations must be able to see Off vs On.
- **Current title:** AUMID / package family from the SmartGlass console-status payload when on.

If a maintained async library later covers this subset cleanly, it can replace the in-repo client without changing the media player API.

### Xbox web API

Microsoft login is required for a useful source list and for launching titles. Use Xbox Live REST (same family as `xbox-webapi` / Home Assistant core Xbox):

- OAuth2 through HA config flow (browser redirect). Default client ID is the OpenXbox / `xbox-webapi` public client already used by community Xbox tools, stored in `const.py` and named in the README. Advanced options allow a user-supplied Azure AD application (personal Microsoft accounts only, mobile/desktop redirect URI).
- Refresh tokens stored in the config entry (not in git, not in logs).
- Installed titles: name, launch id, AUMID when available. Launch id is `oneStoreProductId` when the API provides it, otherwise title id. No content-type filtering in v1 (apps, games, and DLC all appear if the API returns them).
- Launch: Dashboard is a first-class source and sends the SmartGlass/web “go home” command. Every other source launches by that title’s launch id.

Config can be finished without OAuth. In that case the media player still does power, `source_list` is only Dashboard plus the current title if known, and selecting anything other than Dashboard fails with a repair/issue: “Sign in with Microsoft to switch apps and games.”

## Config flow

User-visible steps:

1. **Console:** Name (default “Xbox”), IP or hostname, Xbox network device ID (Settings → System → Console info → Xbox network device ID). Validate that the live ID looks like a hex device ID and that the host is a non-empty IP or hostname. Do not fail setup if the console is off (no SmartGlass reply); that is the normal asleep state.
2. **Microsoft account:** “Sign in” (external OAuth) or “Skip for now” (power only).
3. Created device + one media player.

Reconfigure later: change host / live ID; connect or reconnect Microsoft account; replace tokens.

Console prerequisites (shown in form description and README):

- Instant-on power mode
- Remote features / allow connections from any device (Xbox app preferences)

One config entry per console. Multiple consoles are separate entries.

## Media player contract

Entity id: HA default slug of the configured name (for example name `Living Room Xbox` → `media_player.living_room_xbox`).  
Unique id: the Xbox network device ID.  
Device class: `MediaPlayerDeviceClass.TV`  
Supported features (v1 only): `TURN_ON`, `TURN_OFF`, `SELECT_SOURCE`

| HA field | Mapping |
| --- | --- |
| `state` | `on` / `off` from SmartGlass (unreachable counts as `off`) |
| `source` | Friendly name of current title, or `Dashboard` |
| `source_list` | `Dashboard` first, then installed titles alphabetically by name. Deduplicate by launch id. If the current title is missing from the catalog, append it so Home can display it. HomeKit allows at most 100 inputs: if the list would exceed 100, keep `Dashboard`, the current title, and then as many alphabetical titles as fit (98 or 99), and log a warning. |
| `turn_on` / `turn_off` | SmartGlass power on/off. After `turn_on`, poll for up to 30 seconds for an on status (boot can be slow); still return from the service call without blocking the event loop for that whole period (background wait + coordinator refresh). |
| `select_source` | Dashboard → go home; other names → launch matching launch id. Unknown name → warning log, no-op. |

No volume, play/pause, or media image in v1.

## HomeKit (user setup, not code in this integration)

Because the user already has a HomeKit Bridge, the Xbox **must not** be included in that bridge. Apple will not show a Television on a mixed bridge.

After the media player exists, the user adds a **second** HomeKit integration entry (UI or YAML) in accessory mode that includes **only** this entity. Example YAML:

```yaml
homekit:
  - name: Xbox TV
    mode: accessory
    filter:
      include_entities:
        - media_player.living_room_xbox
```

Then pair the new accessory in Apple Home. The existing bridge pairing is left alone.

The README must state:

- Do not add this `media_player` to the existing bridge include list.
- If it was previously exposed as switches, remove it from HomeKit and re-add the accessory; HomeKit does not change type in place.
- Television accessories require iOS 12.2 or later.

The integration does not auto-write `configuration.yaml` or create HomeKit entries (HA does not give custom components a supported way to do that safely). Config flow success text and README both point at these steps.

## Data flow

1. Coordinator polls SmartGlass every 10 seconds: on/off, current AUMID.
2. When Microsoft tokens exist, coordinator refreshes installed titles every 15 minutes and after a successful OAuth.
3. Media player reads coordinator data: state, source, source_list.
4. `turn_on` / `turn_off` / `select_source` call the clients, then request a coordinator refresh.
5. HomeKit accessory mirrors that entity; Apple Home automations fire on the HAP Television.

Launch is fire-and-forget from Home’s point of view: send launch, then poll until current AUMID matches or 30 seconds elapse. If it does not match, log a warning; do not flip power off.

## Error handling

| Situation | User-visible result |
| --- | --- |
| Console asleep / no SmartGlass reply | Media player `off` (not `unavailable`) so Home automations can use Off |
| Wrong live ID or power-on fails | Stay `off`; warning log on the explicit `turn_on` call. No persistent notification in v1. |
| OAuth missing | Power works; source list is Dashboard (+ current title); launch of other sources shows a repair asking to sign in |
| OAuth/token refresh fails | Keep last title catalog; mark Microsoft connection failed; power still works |
| Launch fails | State unchanged; warning log |
| HA / integration crash | Isolated to this component; existing HomeKit Bridge unaffected |

Do not log access tokens, refresh tokens, or client secrets.

## Testing

Automated (no console required):

- SmartGlass packet encode/decode and state mapping (on / off / current AUMID) using fixtures taken from documented OpenXbox / homebridge-xbox-tv packet formats. Live captures are a manual-test aid, not a CI dependency.
- Web API catalog parsing → `source_list` (Dashboard first, alphabetical titles, current title appended if missing, truncated to 100).
- Media player: device class TV, features, `select_source` dispatch (Dashboard vs product ID), skip-OAuth degraded mode.
- Config flow: required fields, skip OAuth vs complete OAuth (mocked).

Manual (developer with Series S/X + HA + Apple Home):

1. Instant-on + remote features on the console.
2. Add integration; confirm entity is TV media player.
3. Power on/off from HA.
4. Source list populated after Microsoft login; launch Dashboard and one app/game.
5. Create HomeKit accessory (this entity only); pair in Apple Home as TV.
6. Apple Home: power tile and input list; one automation (e.g. Xbox turns on → a light).
7. Confirm the existing HomeKit Bridge still works and does not contain the Xbox.

## Distribution

- HACS custom repository (integration category).
- `manifest.json` `iot_class`: `local_polling`.
- Python 3.13 as used by current Home Assistant, async only on the event loop (no blocking SmartGlass I/O).

## v1 cut line

Ship power + sources + README HomeKit steps. Do not add volume, remote keys, buttons, sensors, MQTT, or an in-integration HAP server unless a later spec says so.
