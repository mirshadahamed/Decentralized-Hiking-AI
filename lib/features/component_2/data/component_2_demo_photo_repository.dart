import 'dart:convert';

import 'package:flutter/services.dart';

import '../domain/component_2_demo_photo.dart';

abstract interface class Component2DemoPhotoRepository {
  Future<List<Component2DemoPhoto>> samples();
  Future<Uint8List> load(Component2DemoPhoto sample);
}

class AssetComponent2DemoPhotoRepository
    implements Component2DemoPhotoRepository {
  AssetComponent2DemoPhotoRepository({AssetBundle? bundle})
    : _bundle = bundle ?? rootBundle;

  static const _catalogAsset = 'assets/demo/component_2/demo_samples.json';
  final AssetBundle _bundle;

  @override
  Future<List<Component2DemoPhoto>> samples() async {
    final manifest = await AssetManifest.loadFromAssetBundle(_bundle);
    final availableAssets = manifest.listAssets().toSet();
    final entries = jsonDecode(await _bundle.loadString(_catalogAsset)) as List;
    return entries
        .map((entry) {
          final json = entry as Map<String, dynamic>;
          if (json['demo_only'] != true) {
            throw const FormatException(
              'Component 2 sample catalog entries must be demo-only.',
            );
          }
          final fileName = json['file_name'] as String;
          final assetPath = 'assets/demo/component_2/$fileName';
          return Component2DemoPhoto(
            id: json['id'] as String,
            title: json['display_title'] as String,
            category: json['expected_development_category'] as String,
            assetPath: assetPath,
            isAvailable: availableAssets.contains(assetPath),
            sourceDatasetOrOwner: json['source_dataset_or_owner'] as String?,
            sourceSplit: json['source_split'] as String?,
            originalIdentifier: json['original_identifier'] as String?,
            licenseProvenanceNote: json['license_provenance_note'] as String,
          );
        })
        .toList(growable: false);
  }

  @override
  Future<Uint8List> load(Component2DemoPhoto sample) async {
    if (!sample.isAvailable) {
      throw StateError('Demo photo is not installed: ${sample.assetPath}');
    }
    final data = await _bundle.load(sample.assetPath);
    return data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
  }
}
