"""Create a new release archive; never overwrite an existing destination."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from validate_library import SCHEMA, VERSION, validate


def payload(root: Path) -> dict[str, bytes]:
    root = root.resolve()
    files = {}
    for path in sorted((root / 'skills').rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Symlinks are not release inputs: {path}')
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo'):
            files[path.relative_to(root / 'skills').as_posix()] = path.read_bytes()
    return files


def package(root: Path, destination: Path) -> None:
    errors = validate(root)
    if errors:
        raise ValueError('\n'.join(errors))
    files = payload(root)
    manifest = {'library_version': VERSION, 'schema_version': SCHEMA,
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    if destination.is_symlink():
        raise FileExistsError(f'Archive destination is an existing symbolic link: {destination}')
    destination = destination.resolve()
    if destination.is_relative_to((root / 'skills').resolve()):
        raise ValueError('Archive must be outside release input skills')
    # x reserves a new filename and rejects any pre-existing file atomically.
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr('library-manifest.json', json.dumps(manifest, indent=2) + '\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        package(args.root, args.output)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, str(error) + '\n')
    print(f'Created {args.output.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
