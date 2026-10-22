#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'Usage: %s <demo-photo-directory>\n' "$0" >&2
  exit 2
fi

source_dir=$1
if [[ ! -d "$source_dir" ]]; then
  printf 'Photo directory not found: %s\n' "$source_dir" >&2
  exit 2
fi

adb_bin=${ADB:-}
if [[ -z "$adb_bin" ]]; then
  if command -v adb >/dev/null 2>&1; then
    adb_bin=$(command -v adb)
  else
    for sdk_root in "${ANDROID_SDK_ROOT:-}" "${ANDROID_HOME:-}" "$HOME/Library/Android/sdk"; do
      if [[ -n "$sdk_root" && -x "$sdk_root/platform-tools/adb" ]]; then
        adb_bin="$sdk_root/platform-tools/adb"
        break
      fi
    done
  fi
fi
if [[ -z "$adb_bin" || ! -x "$adb_bin" ]]; then
  printf 'adb was not found. Set ADB or add Android platform-tools to PATH.\n' >&2
  exit 1
fi

device=${ANDROID_SERIAL:-emulator-5554}
destination=/sdcard/Pictures/Component2Demo
photos=(
  litter_on_trail.jpg
  litter_multiple.jpg
  rock_on_trail.jpg
  fallen_log.jpg
  clean_trail.jpg
)

device_state=$("$adb_bin" -s "$device" get-state 2>/dev/null || true)
if [[ "$device_state" != 'device' ]]; then
  printf 'Android device %s is not online (state: %s). Start emulator-5554 and retry.\n' \
    "$device" "${device_state:-offline}" >&2
  exit 1
fi

for photo in "${photos[@]}"; do
  if [[ ! -f "$source_dir/$photo" ]]; then
    printf 'Required demo photo is missing: %s\n' "$source_dir/$photo" >&2
    exit 1
  fi
done

"$adb_bin" -s "$device" shell mkdir -p "$destination"
for photo in "${photos[@]}"; do
  "$adb_bin" -s "$device" push "$source_dir/$photo" "$destination/$photo" >/dev/null
  "$adb_bin" -s "$device" shell am broadcast \
    -a android.intent.action.MEDIA_SCANNER_SCAN_FILE \
    -d "file://$destination/$photo" >/dev/null
done

remote_files=$("$adb_bin" -s "$device" shell ls -1 "$destination" | tr -d '\r')
for photo in "${photos[@]}"; do
  if ! printf '%s\n' "$remote_files" | grep -Fxq "$photo"; then
    printf 'Photo did not appear in emulator folder: %s\n' "$photo" >&2
    exit 1
  fi
done

printf 'Seeded %d demo photos to %s on %s. Final emulator folder contents:\n' \
  "${#photos[@]}" "$destination" "$device"
printf '%s\n' "$remote_files"
