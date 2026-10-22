#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf 'Usage: %s <reviewed-development-photo-directory>\n' "$0" >&2
  exit 2
fi

source_dir=$1
if [[ ! -d "$source_dir" ]]; then
  printf 'Photo directory not found: %s\n' "$source_dir" >&2
  exit 2
fi

adb_bin=${ADB:-adb}
device=${ANDROID_SERIAL:-emulator-5554}
destination=/sdcard/Pictures/Component2Demo
photos=(
  litter_on_trail.jpg
  litter_multiple.jpg
  rock_on_trail.jpg
  fallen_log.jpg
  clean_trail.jpg
)

"$adb_bin" -s "$device" get-state >/dev/null
for photo in "${photos[@]}"; do
  if [[ ! -f "$source_dir/$photo" ]]; then
    printf 'Required reviewed demo photo is missing: %s\n' "$source_dir/$photo" >&2
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

printf 'Copied %d reviewed development photos to %s on %s.\n' \
  "${#photos[@]}" "$destination" "$device"
