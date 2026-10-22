import 'dart:typed_data';

import 'package:image/image.dart' as img;

class LetterboxTransform {
  const LetterboxTransform({
    required this.sourceWidth,
    required this.sourceHeight,
    required this.targetSize,
    required this.resizedWidth,
    required this.resizedHeight,
    required this.padLeft,
    required this.padTop,
  });

  final int sourceWidth;
  final int sourceHeight;
  final int targetSize;
  final int resizedWidth;
  final int resizedHeight;
  final int padLeft;
  final int padTop;

  double sourceX(double modelX) =>
      (modelX - padLeft) * sourceWidth / resizedWidth;
  double sourceY(double modelY) =>
      (modelY - padTop) * sourceHeight / resizedHeight;
}

class PreparedInput {
  const PreparedInput({required this.rgbFloat32, required this.transform});

  final Float32List rgbFloat32;
  final LetterboxTransform transform;
}

/// Bundle-defined RGB float32 preprocessing: EXIF correction, bilinear
/// letterbox resize, RGB 114 pad and [0,1] normalization.
PreparedInput prepareLetterboxedInput(img.Image encodedImage, int targetSize) {
  if (targetSize <= 0 || encodedImage.width <= 0 || encodedImage.height <= 0) {
    throw ArgumentError('Image and model input dimensions must be positive.');
  }
  final source = img.bakeOrientation(encodedImage);
  final scale =
      targetSize /
      (source.width > source.height ? source.width : source.height);
  final resizedWidth = _roundToEven(source.width * scale)
      .clamp(1, targetSize)
      .toInt();
  final resizedHeight = _roundToEven(source.height * scale)
      .clamp(1, targetSize)
      .toInt();
  final padLeft = _roundToEven((targetSize - resizedWidth) / 2 - 0.1);
  final padTop = _roundToEven((targetSize - resizedHeight) / 2 - 0.1);
  final transform = LetterboxTransform(
    sourceWidth: source.width,
    sourceHeight: source.height,
    targetSize: targetSize,
    resizedWidth: resizedWidth,
    resizedHeight: resizedHeight,
    padLeft: padLeft,
    padTop: padTop,
  );
  final resized = img.copyResize(
    source,
    width: resizedWidth,
    height: resizedHeight,
    interpolation: img.Interpolation.linear,
  );
  final output = Float32List(targetSize * targetSize * 3);
  for (var y = 0; y < targetSize; y++) {
    for (var x = 0; x < targetSize; x++) {
      final index = (y * targetSize + x) * 3;
      final sx = x - padLeft;
      final sy = y - padTop;
      if (sx < 0 || sy < 0 || sx >= resizedWidth || sy >= resizedHeight) {
        output[index] = 114 / 255;
        output[index + 1] = 114 / 255;
        output[index + 2] = 114 / 255;
      } else {
        final pixel = resized.getPixel(sx, sy);
        output[index] = pixel.r.toDouble() / 255;
        output[index + 1] = pixel.g.toDouble() / 255;
        output[index + 2] = pixel.b.toDouble() / 255;
      }
    }
  }
  return PreparedInput(rgbFloat32: output, transform: transform);
}

int _roundToEven(double value) {
  final floorValue = value.floor();
  final fraction = value - floorValue;
  if (fraction < 0.5) return floorValue;
  if (fraction > 0.5) return floorValue + 1;
  return floorValue.isEven ? floorValue : floorValue + 1;
}
