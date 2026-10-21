import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:decentralized_hiking_ai/features/component_2/data/letterbox_preprocessor.dart';

void main() {
  test(
    'letterbox creates RGB float input with 114 pad and matching transform',
    () {
      final image = img.Image(width: 2, height: 1);
      image.setPixelRgb(0, 0, 255, 0, 0);
      image.setPixelRgb(1, 0, 0, 0, 255);

      final prepared = prepareLetterboxedInput(image, 2);

      expect(prepared.transform.resizedWidth, 2);
      expect(prepared.transform.resizedHeight, 1);
      expect(prepared.transform.padTop, 0);
      expect(prepared.rgbFloat32.length, 12);
      expect(prepared.rgbFloat32[0], closeTo(1, 1e-6));
      expect(prepared.rgbFloat32[2], closeTo(0, 1e-6));
      expect(prepared.rgbFloat32[9], closeTo(114 / 255, 1e-6));
      expect(prepared.rgbFloat32[10], closeTo(114 / 255, 1e-6));
      expect(prepared.rgbFloat32[11], closeTo(114 / 255, 1e-6));
    },
  );

  test('transform maps padded model coordinates back into source pixels', () {
    const transform = LetterboxTransform(
      sourceWidth: 100,
      sourceHeight: 50,
      targetSize: 100,
      resizedWidth: 100,
      resizedHeight: 50,
      padLeft: 0,
      padTop: 25,
    );
    expect(transform.sourceX(40), 40);
    expect(transform.sourceY(45), 20);
  });
}
