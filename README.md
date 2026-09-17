# Xbox TV

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

Add a second HomeKit entry in accessory mode with only the Xbox entity:

```yaml
homekit:
  - name: Xbox TV
    mode: accessory
    filter:
      include_entities:
        - media_player.living_room_xbox
```

Pair that accessory in Apple Home. Leave the existing bridge pairing alone.

If the Xbox was previously exposed as switches, remove it from HomeKit and re-add; HomeKit does not change accessory type in place. Television accessories need iOS 12.2 or later.

## Microsoft sign-in

Sign-in is required to list and launch apps/games and to power off. Power on and on/off presence use the local network. After opening the login URL, paste the full redirected `http://localhost/auth/callback?code=...` URL back into the form.

Default Microsoft client id is OpenXbox `388ea51c-0b25-4029-aae2-17df49d23905`.

## Entities

Each configured console creates one Television `media_player` entity (slug from the name you chose at setup, e.g. `media_player.living_room_xbox`). It reports on/off state, current source, and a selectable source list for installed apps and games.

## v1 limitations

Volume control and Apple Remote keys are not supported in v1.
