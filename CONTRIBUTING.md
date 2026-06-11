# Contributing

AutoPaperReader treats the generated wiki as a versioned artifact. A good pull
request should keep the markdown reports, generated HTML/JSON pages, taxonomy
configuration, and quality checks in sync.

## Common Workflows

### Triage Incoming Issues

Use the issue forms to keep a large paper library manageable:

1. `Paper intake` issues should either become `docs/inbox.csv` rows or be closed
   as duplicates after checking `docs/inbox.html` and `docs/library.html`.
2. `Taxonomy governance` issues should cite `docs/facets.html`,
   `docs/taxonomy_actions.json`, `docs/quality.html`, or affected report slugs.
3. `Report quality issue` issues should identify the report slug and whether the
   fix touches markdown, rendered HTML, taxonomy config, or generation scripts.
4. Prefer small PRs that resolve one intake batch, one taxonomy action, or one
   quality queue at a time.

### Add Or Update A Paper

1. Add or edit `docs/<slug>.md`, preferably starting from
   `docs/guides/report.template.md`.
2. Make sure the frontmatter follows `docs/guides/metadata.schema.json`.
3. Render or update `docs/<slug>.html`.
4. Run `python3 scripts/build_wiki.py docs`.
5. Run `python3 scripts/check_quality.py docs`.

### Change Taxonomy Or Metadata Rules

1. Update `docs/guides/taxonomy.json` for label aliases, state values, role order,
   or shared views.
2. Update `docs/guides/taxonomy.schema.json` if the taxonomy config contract
   changes; update `docs/guides/metadata.schema.json` only when the report
   frontmatter contract itself changes.
3. Update `docs/guides/taxonomy.md` and `README.md` if the user-facing workflow
   changes.
4. Run `python3 scripts/build_wiki.py docs`.
5. Run `python3 scripts/check_quality.py docs`.

### Change Wiki UI Or Scripts

1. Prefer updating `scripts/build_wiki.py` instead of editing generated HTML by
   hand.
2. Regenerate with `python3 scripts/build_wiki.py docs`.
3. Keep generated pages committed if their output changes.
4. Run `python3 scripts/check_quality.py docs`.

## Quality Gate

Run this before committing:

```bash
python3 scripts/check_quality.py docs
```

The same gate runs in GitHub Actions on push and pull request. It checks Python
syntax, generated wiki freshness, metadata/inbox/taxonomy contract files,
strict taxonomy validation, inline JavaScript parsing, and the unit test suite.

## Review Checklist

- Reports include required frontmatter and valid `importance`, `confidence`,
  `reproducibility`, `has_code`, and review date values.
- New status, reading stage, review stage, or line role values are added to the
  active workflow in `docs/guides/taxonomy.json`, or intentionally show up as
  taxonomy drift. For alternate processes, add a named `status_workflows` entry
  and switch it through `active_status_workflow`.
- `docs/quality.html` has no surprising unresolved queues for the change.
- Generated artifacts are current: `python3 scripts/build_wiki.py docs --check`
  passes.
- `python3 scripts/check_quality.py docs` passes locally.
