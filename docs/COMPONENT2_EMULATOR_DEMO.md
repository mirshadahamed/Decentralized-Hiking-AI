# Component 2 PP1 emulator demo

Component 2 runs both local LiteRT/TFLite models on-device. The five images
below are demonstration inputs only: selecting a carousel card or pressing
**Use sample** loads the bundled asset and sends its real bytes through the
inference service. The result screen shows the model output, the development
quality disclaimer, and `trail_condition: not_assessed`. Demo photos are not
training, validation, calibration, or final-test evidence.

## Local demo photos and provenance

The expected workstation-local files are:

| File | Display title | Development category |
| --- | --- | --- |
| `litter_on_trail.jpg` | Litter on trail | Litter / waste |
| `litter_multiple.jpg` | Several pieces of litter | Multiple litter items |
| `rock_on_trail.jpg` | Rock on trail | Rock / obstacle |
| `fallen_log.jpg` | Fallen log | Fallen tree / log |
| `clean_trail.jpg` | Clean trail | Clean trail / hard negative |

The catalog records all five as demo-only and enables real AI inference. Their
source, owner, original identifier, split, and redistribution rights are not
confirmed. The JPGs are therefore ignored by Git and must stay local until
redistribution permission is verified. They are included in a local Flutter
build through the `assets/demo/component_2/` asset-directory registration, but
they will not be present in a fresh clone. Do not copy the JPGs into a public
commit or use them as accuracy evidence. Add them to a clone only after the
source and rights are reviewed.

## Run the demo

After placing the five files in `assets/demo/component_2/`, run:

```sh
flutter pub get
bash scripts/component2/seed_emulator_demo_photos.sh assets/demo/component_2
flutter run -d emulator-5554
```

The seed script finds `adb` on `PATH` or under the Android SDK, verifies that
`emulator-5554` is online and all five files exist, copies them to
`/sdcard/Pictures/Component2Demo/`, requests media scanning, and prints the
resulting directory listing. Set `ADB` or `ANDROID_SERIAL` to override the
default tool path or device.

The app opens on the PP1 landing page. Tap **Trail & Environmental
Monitoring** to enter Component 2. The horizontal **Try a sample** carousel
shows the bundled photos; tapping a card runs local model inference, and
**Use sample** analyzes the selected card or the first available card. **Choose
photo** opens Android's system Photo Picker, where the seeded images are also
available. The chosen gallery photo uses the same on-device inference service.

No network service is needed for Component 2 photo analysis after installation.
Saved environmental reports remain on the device with `Saved offline` status.
