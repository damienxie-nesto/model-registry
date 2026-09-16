from __future__ import annotations

from model_registry.loader import Registry

BEGIN_MARKER = '<!-- BEGIN MODELS -->'
END_MARKER = '<!-- END MODELS -->'

_HEADER = (
    '| Model | Use cases | Status | Tiers | Hosting | Region | Residency | Review by |\n'
    '|---|---|---|---|---|---|---|---|'
)


def render_table(registry: Registry) -> str:
    """Render the registry as a markdown table. Generated — never hand-edited."""
    rows = [_HEADER]
    for model in sorted(registry.models, key=lambda m: m.entry.id):
        entry = model.entry
        tiers = ', '.join(sorted(model.tiers)) if model.tiers else '—'
        use_cases = ', '.join(sorted(use_case.value for use_case in entry.use_cases))
        rows.append(
            f'| `{entry.id}` | {use_cases} | {entry.status.value} | {tiers} | '
            f'{entry.hosting.value} | {entry.region} | {entry.residency.value} | '
            f'{entry.review_by.isoformat()} |',
        )
    return '\n'.join(rows)


def splice(readme_text: str, table: str) -> str:
    """Replace whatever sits between the markers with `table`."""
    start = readme_text.find(BEGIN_MARKER)
    end = readme_text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f'README is missing the {BEGIN_MARKER} / {END_MARKER} marker pair')
    head = readme_text[: start + len(BEGIN_MARKER)]
    tail = readme_text[end:]
    return f'{head}\n{table}\n{tail}'
