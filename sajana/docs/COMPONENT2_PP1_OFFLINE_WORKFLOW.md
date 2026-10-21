# Component 2 PP1 offline prototype

Component 2 runs both bundled LiteRT models locally through
`Component2InferenceService`. The app does not send a selected image or model
result to a remote service. `assets/models/component2_manifest.json` remains the
source of the model assets, class names, image sizes, thresholds and quality
gate. The model quality gate remains false and each result keeps
`trail_condition` set to `not_assessed`.

The models are trained and exported outside the Android app:

```text
offline training and validation
    -> LiteRT/TFLite export and desktop validation
    -> copy approved development bundle into assets/models/
    -> Flutter packages the local model assets
    -> on-device offline inference
```

Do not train or fine-tune YOLO on the Android device. The training datasets,
checkpoints and Python environments are not Flutter assets. The current models
are development-only because their research accuracy acceptance failed; a
successful on-device inference is not a trail-safety assessment.

## Demo photos

The carousel catalog is `assets/demo/component_2/demo_samples.json`. Add only
small, manually reviewed demonstration photos at these exact paths:

| Filename | Intended example |
| --- | --- |
| `litter_on_trail.jpg` | Litter visible on a trail |
| `litter_near_vegetation.jpg` | A second litter scene with vegetation nearby |
| `rock_on_trail.jpg` | A rock visible on a trail |
| `fallen_log_branch.jpg` | A fallen log or branch |
| `clean_trail.jpg` | A reviewed clean-trail example |

Keep fresh independent final-test photos out of this demo folder. These are
development/demo-only assets and must not be used to claim model accuracy. Until
the image files are present in the asset directory and the app is rebuilt, the
carousel displays each expected filename as a placeholder and sample inference
is unavailable. No sample result is generated without running the local models
on an actual image.

## Offline reports and Android photo access

Incident reports are saved locally with `SharedPreferences`; their photo is
stored as a compact thumbnail alongside the type, timestamp, notes, optional
location, detected labels and `Saved offline` status. There is no report upload
or authority notification. The report repository is an interface so a future
synchronization implementation can be added behind it.

Photo selection uses the current `image_picker` API. On Android 13 and above it
uses the system Photo Picker, which does not require broad media-library access.
The app does not add broad storage permissions. Camera/gallery failures are
shown as short retryable messages, while cancelling a picker leaves the current
screen state intact.

## Future live-camera extension

The current `Component2PhotoSource` returns one image at a time. A future live
mode can add a camera-stream frame source that samples frames at a controlled
rate, converts a sampled frame to image bytes, calls the same
`Component2PhotoAnalyzer`, and draws the returned detections with the existing
overlay painter:

```text
camera stream -> frame sampling -> on-device analyzer -> result overlay
```

Continuous inference, camera-stream lifecycle and performance tuning are not
part of this PP1 prototype.
