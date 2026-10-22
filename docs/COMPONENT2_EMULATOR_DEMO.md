# Component 2 emulator photo demo

Component 2 can analyze photos selected with Android's system photo picker or
captured with the camera. Its bundled-sample carousel reads only the
demo-only catalog in `assets/demo/component_2/demo_samples.json`; it never
creates detections without passing a real image to the local TFLite models.

## Current photo status

The five planned image files are not bundled yet. The local review queue does
not show approved demo examples, TACO's local image-level license fields are
empty, and the MJU-Waste metadata does not state a redistribution license.
Therefore no image has been copied into the app. Each catalog entry records
the missing provenance and remains unavailable until its image has been
reviewed, its development split and source identifier are recorded, and its
license permits redistribution. Demo photos are never fresh evaluation
evidence.

The filenames expected by the catalog and helper are:

| File | Intended example |
| --- | --- |
| `litter_on_trail.jpg` | Litter visible on a trail |
| `litter_multiple.jpg` | Several pieces of litter |
| `rock_on_trail.jpg` | A rock visible on a trail |
| `fallen_log.jpg` | A fallen log or branch |
| `clean_trail.jpg` | A manually reviewed clean-trail negative |

## Seed an Android gallery after photos are approved

Once all five approved development photos are available in
`assets/demo/component_2/`, start the Android emulator and copy them into its
Pictures collection:

```sh
adb -s emulator-5554 get-state
adb -s emulator-5554 shell mkdir -p /sdcard/Pictures/Component2Demo
for file in litter_on_trail.jpg litter_multiple.jpg rock_on_trail.jpg fallen_log.jpg clean_trail.jpg; do
  adb -s emulator-5554 push "assets/demo/component_2/$file" "/sdcard/Pictures/Component2Demo/$file"
  adb -s emulator-5554 shell am broadcast \
    -a android.intent.action.MEDIA_SCANNER_SCAN_FILE \
    -d "file:///sdcard/Pictures/Component2Demo/$file"
done
```

The repository helper performs the same allowlisted copy and checks the five
files before writing to the emulator:

```sh
bash scripts/component2/seed_emulator_demo_photos.sh assets/demo/component_2
```

To use a connected device other than `emulator-5554`, set `ANDROID_SERIAL`.
The gallery seed is only for testing the real `Choose photo` flow; bundled
sample inference does not depend on it. Android's `image_picker` uses the
system Photo Picker where available and does not need broad media-storage
permissions.
