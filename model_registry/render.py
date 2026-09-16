from __future__ import annotations

from model_registry.loader import Registry

BEGIN_MARKER = '<!-- BEGIN MODELS -->'
END_MARKER = '<!-- END MODELS -->'

_HEADER = (
    '| Model | Use cases | Status | Tiers | Hosting | Region | Residency | Review by |\n'
    '|---|---|---|---|---|---|---|---|'
)


def _cell(value: str) -> str:
    """Escape a value so it cannot break out of its table cell.

    The README table is what `README.md` tells developers to trust when they ask "may
    I use this model", and `id`, `region` and `display_name` are unconstrained strings
    copied from vendor documentation. An unescaped `|` forges extra columns, so an
    entry that is really `trial` / `standard` can render a row reading
    `approved | bank`. A generated artifact that can misrepresent its own source is
    worse than a hand-maintained one, because nobody audits it.

    Backslashes are escaped first so an existing `\\` cannot consume the escape we add;
    newlines (which would end the row outright) are folded to spaces.
    """
    return value.replace('\\', '\\\\').replace('|', '\\|').replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')


def render_table(registry: Registry) -> str:
    """Render the registry as a markdown table. Generated — never hand-edited."""
    rows = [_HEADER]
    for model in sorted(registry.models, key=lambda m: m.entry.id):
        entry = model.entry
        tiers = ', '.join(sorted(model.tiers)) if model.tiers else '—'
        use_cases = ', '.join(sorted(use_case.value for use_case in entry.use_cases))
        rows.append(
            f'| `{_cell(entry.id)}` | {_cell(use_cases)} | {_cell(entry.status.value)} | {_cell(tiers)} | '
            f'{_cell(entry.hosting.value)} | {_cell(entry.region)} | {_cell(entry.residency.value)} | '
            f'{_cell(entry.review_by.isoformat())} |',
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
