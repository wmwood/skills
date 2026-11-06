"""Manually copy the complete sibling library into an absent skills root."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from package_library import payload
from validate_library import SCHEMA, VERSION, validate


def install(root: Path, destination: Path) -> None:
    errors = validate(root)
    if errors:
        raise ValueError('\n'.join(errors))
    if destination.is_symlink():
        raise FileExistsError(f'Installation destination is an existing symbolic link: {destination}')
    destination = destination.resolve()
    source = (root / 'skills').resolve()
    if destination == source or destination.is_relative_to(source):
        raise ValueError('Installation destination must be outside source skills')
    files = payload(root)
    # No exist_ok: an existing destination, including a partial prior copy, fails.
    destination.mkdir(parents=True)
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
    manifest = {'library_version': VERSION, 'schema_version': SCHEMA,
                'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    with (destination / 'library-manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    try:
        install(args.root, args.destination)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    print(f'Installed complete library into {args.destination.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
