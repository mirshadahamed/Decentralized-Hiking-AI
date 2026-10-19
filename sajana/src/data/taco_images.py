"""Image decoding in the geometry recorded by the TACO annotations."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps


def matches_geometry(size: tuple, width: int, height: int) -> bool:
    """Allow proportional fallback sizes with at most one pixel rounding error."""
    actual_width, actual_height = size
    return abs(actual_width - actual_height * width / height) <= max(1, width / height)


def decode_image(content: bytes, width: int, height: int, orientation_override: str = None) -> tuple:
    """Decode fully, choose annotation-compatible orientation, then strip EXIF.

    Shape alone cannot resolve ambiguous rotations/reflections; reject those for
    manual alignment instead of silently moving pixels relative to the masks.
    """
    with Image.open(io.BytesIO(content)) as image:
        image.verify()
    with Image.open(io.BytesIO(content)) as image:
        image.load()
        orientation = image.getexif().get(274, 1)
        if orientation_override not in (None, 'raw', 'exif'):
            raise ValueError('Orientation override must be raw or exif')
        if orientation_override is None and orientation in (2, 3, 4, 5, 7):
            raise ValueError(f'EXIF orientation {orientation} needs manual annotation alignment')
        raw = image.convert('RGB')
        if orientation_override:
            result = raw if orientation_override == 'raw' else ImageOps.exif_transpose(image).convert('RGB')
            action = f'reviewed_override_{orientation_override}'
        elif orientation in (6, 8):
            upright = ImageOps.exif_transpose(image).convert('RGB')
            raw_matches = matches_geometry(raw.size, width, height)
            upright_matches = matches_geometry(upright.size, width, height)
            if raw_matches == upright_matches:
                raise ValueError('EXIF rotation has ambiguous or incompatible annotation geometry')
            result, action = (raw, 'raw_matches_annotations') if raw_matches else (upright, 'exif_rotation')
        elif orientation in (None, 0, 1):
            # Invalid tag 0 specifies no transform. Preserve source pixels and
            # require geometry compatibility; record the metadata repair.
            result, action = raw, 'invalid_exif_0_preserved_raw' if orientation == 0 else 'unchanged'
        else:
            raise ValueError(f'Unsupported EXIF orientation {orientation}')
        if not matches_geometry(result.size, width, height):
            raise ValueError(f'Image size {result.size} does not match source aspect ratio {width}x{height}')
        clean = Image.new('RGB', result.size)
        clean.paste(result)
        return clean, action


def validate_existing(path: Path, width: int, height: int) -> bool:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            return image.getexif().get(274, 1) in (None, 1) and matches_geometry(image.size, width, height)
    except (OSError, ValueError, SyntaxError):
        return False


def save_image(image: Image.Image, destination: Path, quality: int = 95):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.part')
    try:
        image.save(temporary, 'JPEG', quality=quality)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
