"""Download the archive linked by the official MJU-Waste repository.

Extract only requested RGB PNGs into a flat local folder. No archive paths,
links, depth images or executable files are extracted.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
FILE_ID = '1o101UBJGeeMPpI-DSY6oh-tLk9AHXMny'


def extract_rgb(archive: Path, destination: Path, expected: set) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    seen = set()

    def copy_member(name, size, open_member):
        # VOC masks reuse the RGB filenames under SegmentationClass/Instance.
        # The official archive's photographs are specifically in JPEGImages.
        if 'JPEGImages' not in PurePosixPath(name).parts:
            return
        leaf = PurePosixPath(name).name
        if leaf not in expected:
            return
        if leaf in seen:
            raise ValueError(f'Duplicate RGB filename in archive: {leaf}')
        if size > 100 * 1024 * 1024:
            raise ValueError(f'Unexpectedly large RGB member: {leaf}')
        seen.add(leaf)
        target = destination / leaf
        temporary = target.with_suffix('.part')
        with open_member() as source, temporary.open('wb') as stream:
            shutil.copyfileobj(source, stream)
        temporary.replace(target)

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                if not member.is_dir() and (member.external_attr >> 16) & 0o170000 != 0o120000:
                    copy_member(member.filename, member.file_size, lambda member=member: source.open(member))
    elif tarfile.is_tarfile(archive):
        with tarfile.open(archive) as source:
            for member in source:
                if member.isfile():
                    copy_member(member.name, member.size, lambda member=member: source.extractfile(member))
    else:
        raise ValueError('Downloaded response is not a ZIP/TAR archive; check Google Drive access')
    missing = sorted(expected - seen)
    if missing:
        raise ValueError(f'Archive lacks {len(missing)} required RGB images, e.g. {missing[0]}')
    return len(seen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'data/raw/mju_waste')
    parser.add_argument('--annotations', type=Path, default=ROOT / 'data/interim/mju_waste')
    args = parser.parse_args()
    expected = set()
    for split in ('train', 'val', 'test'):
        data = json.loads((args.annotations / f'{split}.json').read_text())
        expected.update(image['file_name'] for image in data['images'])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    archive = args.out_dir / 'mju_waste_archive'
    try:
        if not archive.is_file() or not (zipfile.is_zipfile(archive) or tarfile.is_tarfile(archive)):
            import gdown
            result = gdown.download(id=FILE_ID, output=str(archive), quiet=False,
                                    use_cookies=False, resume=True)
            if not result:
                raise ValueError('Google Drive did not provide the public archive')
        count = extract_rgb(archive, args.out_dir / 'extracted', expected)
        (args.out_dir / 'download_status.json').write_text(json.dumps({
            'downloaded': True, 'extracted_rgb_images': count,
            'official_repository': 'https://github.com/realwecan/mju-waste',
            'download_url': f'https://drive.google.com/file/d/{FILE_ID}/view',
            'rgb_member_directory': 'JPEGImages', 'archive': str(archive.resolve())}, indent=2) + '\n')
        print(f'Extracted {count} RGB images. Run MJU: Prepare RGB images, then full verification.')
    except Exception as exc:
        failure = {'downloaded': False, 'training_ready': False, 'error': str(exc),
                   'official_repository': 'https://github.com/realwecan/mju-waste',
                   'download_url': f'https://drive.google.com/file/d/{FILE_ID}/view',
                   'next_step': 'Place the official archive here or extracted RGB images in the extracted folder, then rerun.'}
        (args.out_dir / 'download_status.json').write_text(json.dumps(failure, indent=2) + '\n')
        parser.exit(1, f'MJU image acquisition failed: {exc}\n')


if __name__ == '__main__':
    main()
