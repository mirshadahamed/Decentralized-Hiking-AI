# Component 2 data in Git

Version the preparation code, tests, dependency lists, portable configs, source annotation JSON, selected text labels, split manifests, class mappings, quarantine records and readiness reports. These files explain which real examples were selected and allow the same preparation to be reproduced.

Keep these local using the repository `.gitignore`:

- Download archives, raw photographs/masks, resumable chunks and temporary connection metadata under `sajana/data/raw/`.
- Prepared RGB images, generated semantic PNG masks, orientation-review images and machine-specific `data.yaml` files.
- Preview images, model weights, training outputs, environments, caches and partial downloads.
- Downloaded RUGD paper/webpage references and the unused pLitter 10-class annotation variant. The selected 4-class annotations remain versioned.
- Unofficial TACO download journals. Its curated available-subset exclusion report remains versioned.

Ignoring a file keeps the local copy. It does not delete data or remove files already in Git history. Do not force-add the ignored raw directory: temporary public S3 credentials may be present there. The local trail annotation workspace has its own ignore rules for photographs and annotation payloads while retaining the empty collection templates.

`.gitattributes` preserves annotation/manifest bytes across operating systems and recognizes valid CRLF CSV record endings, so source hashes do not change during checkout.

Large RGB and mask datasets must be acquired locally using the documented commands. A clone contains labels and provenance; it is not automatically ready for training. Run each source's full verifier, then `Component 2: Audit dataset readiness` in VS Code. The component status distinguishes missing photos, verified auxiliary data and missing local damage/passability ground truth.

Install the combined preprocessing dependencies with `sajana/.venv/bin/python -m pip install -r sajana/requirements_component2.txt`, or use `Component 2: Install preprocessing dependencies` in VS Code after creating the environment.

Source-specific preparation instructions:

- [Dataset order and local annotation plan](COMPONENT2_DATASET_PLAN.md)
- [TACO](TACO_PREPROCESSING_AND_VSCODE_GUIDE.md)
- [pLitterStreet and Mawanella observations](PLITTER_PREPROCESSING_GUIDE.md)
- [RUGD](RUGD_PREPROCESSING_GUIDE.md)
- [WildScenes](WILDSCENES_PREPROCESSING_GUIDE.md)

Model training is separate and is not started by these preprocessing tasks.
