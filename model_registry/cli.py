from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

from model_registry.drift import GatewayUnreachableError, compare, fetch_served_models
from model_registry.loader import DEFAULT_REGISTRY_PATH, Registry, RegistryError, load_registry
from model_registry.render import render_table, splice
from model_registry.scan import Severity, has_file_header, scan_diff

DEFAULT_README_PATH = Path(__file__).resolve().parent.parent / 'README.md'


def _build_parser() -> argparse.ArgumentParser:
    registry_parent = argparse.ArgumentParser(add_help=False)
    registry_parent.add_argument('--registry', type=Path, default=argparse.SUPPRESS, help='path to models.yaml')

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

    scan_parser = subparsers.add_parser(
        'scan',
        help='scan a unified diff on stdin for model IDs',
        parents=[registry_parent],
    )
    scan_parser.add_argument(
        '--block-unknown',
        action='store_true',
        help='treat unregistered model IDs as blocking rather than warnings',
    )

    drift_parser = subparsers.add_parser(
        'drift',
        help='compare the gateway against the registry',
        parents=[registry_parent],
    )
    drift_parser.add_argument('--base-url', default=os.environ.get('LITELLM_GATEWAY_BASE_URL', ''))
    drift_parser.add_argument('--api-key', default=os.environ.get('LITELLM_GATEWAY_API_KEY', ''))
    drift_parser.add_argument('--json', action='store_true', help='emit JSON for a downstream reporter')
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


def _cmd_scan(registry: Registry, diff_text: str, *, block_unknown: bool) -> int:
    if diff_text.strip() and not has_file_header(diff_text):
        sys.stderr.write('input does not look like a unified diff (no `+++ b/<path>` file header found); cannot scan\n')
        return 1

    severity = Severity.BLOCK if block_unknown else Severity.WARN
    findings = scan_diff(diff_text, registry, unknown_severity=severity)
    for finding in findings:
        sys.stderr.write(f'{finding.format()}\n')
    if any(finding.severity is Severity.BLOCK for finding in findings):
        sys.stderr.write('\nSee the approved list: https://github.com/OWNER/model-registry\n')
        return 1
    sys.stdout.write(f'{len(findings)} warning(s), no blocking model usage\n')
    return 0


def _cmd_drift(registry: Registry, base_url: str, api_key: str, *, as_json: bool) -> int:
    if not base_url or not api_key:
        sys.stderr.write('drift needs LITELLM_GATEWAY_BASE_URL and LITELLM_GATEWAY_API_KEY\n')
        return 1
    try:
        served = fetch_served_models(base_url, api_key)
    except GatewayUnreachableError as exc:
        sys.stderr.write(f'drift check failed: {exc}\n')
        return 2

    report = compare(served, registry)
    if as_json:
        sys.stdout.write(
            json.dumps(
                {
                    'models_checked': report.models_checked,
                    'clean': report.is_clean,
                    'items': [
                        {'kind': item.kind.value, 'model_id': item.model_id, 'detail': item.detail}
                        for item in report.items
                    ],
                },
            )
            + '\n',
        )
    else:
        for item in report.items:
            sys.stdout.write(f'{item.kind.value}: {item.model_id} — {item.detail}\n')
        sys.stdout.write(f'{report.models_checked} models checked, {len(report.items)} drift item(s)\n')
    return 0 if report.is_clean else 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    # `--registry` defaults to argparse.SUPPRESS on the shared parent parser so that
    # a value supplied before the subcommand is never silently clobbered by the
    # subparser's own default when it re-merges its namespace (see Task 6 fix round 1).
    registry_path = getattr(args, 'registry', DEFAULT_REGISTRY_PATH)

    try:
        registry = load_registry(registry_path)
    except RegistryError as exc:
        sys.stderr.write(f'registry invalid: {exc}\n')
        return 1

    dispatch: dict[str, Callable[[], int]] = {
        'validate': lambda: _cmd_validate(registry),
        'render': lambda: _cmd_render(registry, args.readme, check=args.check),
        'scan': lambda: _cmd_scan(registry, sys.stdin.read(), block_unknown=args.block_unknown),
        'drift': lambda: _cmd_drift(registry, args.base_url, args.api_key, as_json=args.json),
    }
    return dispatch[args.command]()


if __name__ == '__main__':
    raise SystemExit(main())
