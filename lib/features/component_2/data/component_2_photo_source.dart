import 'dart:typed_data';

import 'package:image_picker/image_picker.dart';

abstract interface class Component2PhotoSource {
  Future<Uint8List?> pick(ImageSource source);
}

class ImagePickerComponent2PhotoSource implements Component2PhotoSource {
  ImagePickerComponent2PhotoSource({ImagePicker? picker})
    : _picker = picker ?? ImagePicker();

  final ImagePicker _picker;

  @override
  Future<Uint8List?> pick(ImageSource source) async {
    final file = await _picker.pickImage(
      source: source,
      maxWidth: 2048,
      maxHeight: 2048,
      requestFullMetadata: false,
    );
    return file?.readAsBytes();
  }
}
