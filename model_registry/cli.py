from __future__ import annotations

import argparse
import sys
from pathlib import Path

from model_registry.loader import DEFAULT_REGISTRY_PATH, Registry, RegistryError, load_registry
from model_registry.render import render_table, splice

DEFAULT_README_PATH = Path(__file__).resolve().parent.parent / 'README.md'


def _build_parser() -> argparse.ArgumentParser:
    registry_parent = argparse.ArgumentParser(add_help=False)
    registry_parent.add_argument('--registry', type=Path, default=DEFAULT_REGISTRY_PATH, help='path to models.yaml')

    parser = argparse.ArgumentParser(
        prog='model-registry',
        description='Nesto approved-model registry.',
        parents=[registry_parent],
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser('validate', help='validate models.yaml', parents=[registry_parent])

    render_parser = subparsers.add_parser('render', help='regenerate the README table', parents=[registry_parent])
    render_parser.add_argument('--readme', type=Path, default=DEFAULT_README_PATH)
    render_parser.add_argument(
        '--check',
        action='store_true',
        help='fail instead of writing when the README is out of date',
    )
    return parser


def _cmd_validate(registry: Registry) -> int:
    sys.stdout.write(f'{len(registry.models)} models, registry valid\n')
    return 0


def _cmd_render(registry: Registry, readme_path: Path, *, check: bool) -> int:
    current = readme_path.read_text()
    try:
        updated = splice(current, render_table(registry))
    except ValueError as exc:
        sys.stderr.write(f'{exc}\n')
        return 1

    if check:
        if updated != current:
            sys.stderr.write('README table is out of date; run `make render` and commit the result\n')
            return 1
        return 0

    readme_path.write_text(updated)
    sys.stdout.write(f'rendered {len(registry.models)} models into {readme_path}\n')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        registry = load_registry(args.registry)
    except RegistryError as exc:
        sys.stderr.write(f'registry invalid: {exc}\n')
        return 1

    if args.command == 'validate':
        return _cmd_validate(registry)

    if args.command == 'render':
        return _cmd_render(registry, args.readme, check=args.check)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
