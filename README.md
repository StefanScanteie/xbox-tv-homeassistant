# Xbox TV

<img src="https://raw.githubusercontent.com/StefanScanteie/xbox-tv-homeassistant/main/custom_components/xbox_tv/brand/icon.png" width="72" height="72" alt="Xbox">

Home Assistant custom integration that exposes an Xbox Series S or Series X as a Television media player for Apple Home automations.

## Console settings

- Instant-on: Profile & system → Settings → General → Power mode & startup
- Allow connections from any device: Settings → Devices & connections → Remote features → Xbox app preferences

You need the **Xbox network device ID** (Settings → System → Console info), not the serial number.

## Install

HACS → Custom repositories → this GitHub repo → Integration category.

Or copy `custom_components/xbox_tv` into your Home Assistant `custom_components` folder and restart.

## Apple Home

Home Assistant already using a HomeKit **Bridge** must **not** include this media player on that bridge. Apple will not show a Television on a mixed bridge.

Add a second HomeKit entry in accessory mode with only the Xbox media player:

```yaml
homekit:
  - name: Xbox TV
    mode: accessory
    filter:
      include_entities:
        - media_player.living_room_xbox
```

Pair that accessory in Apple Home. Leave the existing bridge pairing alone.

The Occupied binary sensor can stay on the existing HomeKit Bridge for lighting automations (“when Xbox is occupied, set lights”).

If the Xbox was previously exposed as switches, remove it from HomeKit and re-add; HomeKit does not change accessory type in place. Television accessories need iOS 12.2 or later.

After adding play/pause or remote support, reload or re-add the HomeKit accessory so Control Center picks up the new features.

## Microsoft sign-in

Sign-in is required to list and launch apps/games, power off, and use the Apple Remote / media controls. Power on and on/off presence use the local network. After opening the login URL, paste the full redirected `http://localhost/auth/callback?code=...` URL back into the form.

Default Microsoft client id is OpenXbox `388ea51c-0b25-4029-aae2-17df49d23905`.

## Entities

Each configured console creates:

- One Television `media_player` (slug from the name you chose at setup, e.g. `media_player.living_room_xbox`). It reports on/off, current source, play/pause/next/previous, and Apple Remote keys. Attributes: `app_id` (AUMID), `content_type`, `in_game`.
- One Occupied `binary_sensor` (device class occupancy) that is on while the console is powered on.

## Source list

HomeKit caps Television inputs at 100. Configure the integration to hide DLC and system apps (on by default) and pin favorites (comma-separated names or product IDs). Dashboard stays first, then favorites, then the rest alphabetically.

## Limitations

Volume and mute are not exposed. Xbox volume is often HDMI-CEC / TV audio, so HomeKit speaker buttons would be unreliable.
