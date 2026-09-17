# Xbox TV

<img src="https://raw.githubusercontent.com/StefanScanteie/xbox-tv-homeassistant/main/custom_components/xbox_tv/brand/icon.png" width="72" height="72" alt="Xbox">

Home Assistant custom integration that exposes an Xbox Series S or Series X as a **Television** media player so Apple Home can treat it as a TV (power, input, Control Center remote, automations).

Home Assistant’s built-in [Xbox](https://www.home-assistant.io/integrations/xbox) integration is the right place for friends, presence, clips, and media browsing. It does **not** use `device_class: tv`, so Apple Home shows switches instead of a Television. This integration fills that gap. You can run both at once.

## What you get

- Power on over the local network (SmartGlass wake)
- Power off, Dashboard, and app/game launch over Xbox Network (after Microsoft sign-in)
- A source list (Dashboard first, then installed apps and games) for Home Assistant and Apple Home inputs
- Apple Remote / Control Center keys (arrows, select, back, guide, play/pause, next/previous)
- An Occupied occupancy sensor for lighting automations on your existing HomeKit Bridge
- Options to hide DLC and system apps and pin favorites (HomeKit caps Television inputs at 100)

## Microsoft account and Xbox Network

This integration uses the **same Microsoft / Xbox Network sign-in and remote-management APIs** that the Xbox app and Home Assistant’s official `xbox` integration already use. It is not a scrape, a game cheat, or a third-party “login bot.”

- You sign in at Microsoft’s real login page (`login.live.com`) with your own account.
- Cloud commands go to Xbox Network remote management (`xccs.xboxlive.com`) as `sourceId` `com.microsoft.smartglass` — TurnOff, GoHome, Activate (launch a title), InjectKey, Play/Pause/Next/Previous. Those are the same command types the Xbox mobile app and [xbox-webapi](https://github.com/OpenXbox/xbox-webapi-python) / Home Assistant `xbox` use for console control.
- Local power-on is the SmartGlass UDP wake packet the Xbox app sends when Instant-on and “allow connections from any device” are enabled.
- The default OAuth client is the public OpenXbox client (`388ea51c-0b25-4029-aae2-17df49d23905`) with scopes `XboxLive.signin` and `XboxLive.offline_access`. Community Xbox tools have used this client for years. Home Assistant core `xbox` signs in through Home Assistant Cloud instead; this integration cannot use that redirect, so it uses the OpenXbox paste-code flow. Both are normal Microsoft OAuth grants on **your** account.
- Tokens stay in the Home Assistant config entry. They are not written to git, not logged, and not shared with the official `xbox` integration. Running both means two separate sign-ins to the same Microsoft account, which is expected.

There is **no known account-ban risk** from using these APIs. Microsoft exposes them for remote features; Home Assistant ships an official integration on the same Xbox Network stack. This project does not automate gameplay, farm achievements, impersonate other users, or modify console firmware.

No third-party project can promise Microsoft will never change its terms. If Microsoft restricted remote management, it would affect the Xbox app and official Home Assistant `xbox` as well — not this integration alone.

Use a **non-child** Microsoft account (18+), the same requirement as official `xbox`.

## Requirements

- Home Assistant 2025.1 or later (brand icons in Settings → Devices & services need 2026.3+)
- Xbox Series S or Series X on the same LAN as Home Assistant (Xbox One may work; it is not the target)
- Instant-on power mode
- Remote features allowed from any device
- The **Xbox network device ID** (not the serial number)
- Microsoft sign-in for power off, source switching, and the remote. Without sign-in you still get LAN wake and on/off presence.

## Console settings

On the Xbox:

1. **Instant-on** — Profile & system → Settings → General → Power mode & startup
2. **Allow connections from any device** — Settings → Devices & connections → Remote features → Xbox app preferences
3. Copy **Xbox network device ID** — Settings → System → Console info (8–32 hex characters)

Give the console a DHCP reservation or a static IP so the host you enter at setup does not change.

## Install

**HACS (recommended)**

1. HACS → Custom repositories → [this GitHub repo](https://github.com/StefanScanteie/xbox-tv-homeassistant) → Integration
2. Download **Xbox TV**
3. Restart Home Assistant

The HACS **details** page and Home Assistant’s integration list use the bundled brand icon. The HACS **Downloaded** list still asks the old `brands.home-assistant.io` CDN, which has no entry for new custom integrations. That placeholder is a [HACS limitation](https://github.com/hacs/integration/issues/5171), not a missing file in this repo.

**Manual**

Copy `custom_components/xbox_tv` into your Home Assistant `custom_components` folder and restart.

## Setup

1. Settings → Devices & services → Add integration → **Xbox TV**
2. Enter a friendly **name** (this becomes the device name and the media player entity slug, e.g. Living Room Xbox → `media_player.living_room_xbox`)
3. Enter the console **host** (IP or hostname)
4. Enter the **Xbox network device ID**
5. Sign in with Microsoft (recommended) or skip for now

**Microsoft sign-in**

1. Open the login URL shown in the form
2. Sign in with the Microsoft account that owns the console and click **Allow**
3. The browser will try to open `http://localhost/auth/callback?code=...` and show **Safari Can’t Connect to the Server** (or Chrome’s equivalent). That is success. Microsoft sent the code to localhost, and nothing in Home Assistant is supposed to answer that request.
4. Copy the **full** URL from the address bar (Safari may hide `http://`; `localhost/auth/callback?code=...` is enough). You can also copy the localhost URL from the error page text.
5. Paste it into **Redirect URL** in the Home Assistant dialog that is still open, then submit. Do not close that dialog first.

If the code is rejected, sign in again and paste immediately — Microsoft authorization codes expire quickly.

You can reconfigure host, live ID, and tokens later from the integration’s menu. Options (source filters) are under Configure on the integration entry.

## Entities

Each console creates one device with:

| Entity | What it does |
| --- | --- |
| Television `media_player` | On/off, source list, play/pause/next/previous, Apple Remote keys |
| Occupied `binary_sensor` | Occupancy; on while the console is powered on |

Media player attributes (useful in Home Assistant automations):

| Attribute | Meaning |
| --- | --- |
| `app_id` | Current title AUMID |
| `content_type` | Catalog type when known (`Game`, `App`, `Dlc`, …) |
| `in_game` | `true` when the console is on and the current title is a game |

Unreachable consoles report **off**, not unavailable, so Apple Home automations can still see Off vs On (a sleeping Instant-on Xbox often looks like that on the LAN).

## Apple Home

Apple only shows a Television when all of these are true:

- The entity is a `media_player` with `device_class: tv`
- HomeKit exposes it as its **own accessory** (`mode: accessory`)
- That accessory includes **only** this media player

Do **not** add `media_player.living_room_xbox` to your existing HomeKit Bridge. A mixed bridge will not show a TV.

Add a second HomeKit entry:

```yaml
homekit:
  - name: Xbox TV
    mode: accessory
    filter:
      include_entities:
        - media_player.living_room_xbox
```

Pair that accessory in Apple Home. Leave the existing bridge pairing alone.

Put the **Occupied** sensor on the existing HomeKit Bridge if you want lighting automations such as “when Xbox is occupied, set lights.” Television accessories are awkward in some Home scenes; occupancy is not.

If the Xbox was previously exposed as switches, remove it from HomeKit and re-add. HomeKit does not change accessory type in place. Television accessories need iOS 12.2 or later.

After you add play/pause or remote support, reload or re-add the HomeKit TV accessory so Control Center picks up the new features.

**Remote keys** (Control Center Apple Remote) map to Xbox commands: arrows and select are d-pad / A, back is GoBack, exit is Dashboard, info is the Nexus/guide button, play/pause and next/previous use the media player services.

## Source list

HomeKit allows at most **100** Television inputs. A large library is truncated.

Configure the integration to:

- **Hide DLC** (default on)
- **Hide system apps** such as Microsoft Store and Settings (default on)
- **Favorites** — comma-separated source names or product IDs, listed after Dashboard

Dashboard always stays first. The currently running title is kept even if it would otherwise be filtered.

## How it talks to the console

```
Apple Home  →  HA HomeKit accessory (TV only)
                 →  media_player + Occupied sensor
                      →  LAN SmartGlass (wake, on/off presence)
                      →  Xbox Network REST (off, launch, remote, catalog)
```

This integration does **not** embed a second HomeKit stack. Pairing stays in Home Assistant’s HomeKit integration.

## What this does not do

Leave these to core `xbox` or skip them:

- Friends, presence, Game DVR, clips, screenshots
- Volume and mute (Xbox audio is often HDMI-CEC / the TV; HomeKit speaker buttons would be unreliable)
- Xbox One as a supported target
- Replacing or wrapping the official `xbox` integration

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Stays off / will not wake | Instant-on, “allow connections from any device”, correct IP, Xbox network device ID (not serial) |
| Wakes but will not power off or change apps | Complete Microsoft sign-in; use Reconfigure if tokens expired |
| Browser says it cannot connect to localhost after Allow | Expected. Copy that localhost `?code=` URL into the still-open Home Assistant form |
| Source list is only Dashboard | Sign-in skipped or catalog call failed; sign in again |
| Apple Home shows switches, not a TV | The media player is on the mixed HomeKit Bridge; use a dedicated accessory |
| Control Center remote does nothing | Sign-in required; reload/re-add the HomeKit accessory after updating |
| Occupied never trips Home automations | Expose the binary sensor on the **bridge**, not only the TV accessory |
| HACS Downloaded list shows “icon not available” | Known HACS CDN gap; details page and HA integration list are the ones that use the bundled icon |

## License and source

Repository: [StefanScanteie/xbox-tv-homeassistant](https://github.com/StefanScanteie/xbox-tv-homeassistant)
