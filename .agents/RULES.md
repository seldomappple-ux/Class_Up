# Local Rules

This file is owned by the project maintainer. Keep durable local preferences here in prose, but do not expect this file alone to affect generated adapters.

## Protection

- Treat this file as manually maintained source.
- Generated files must never overwrite this file.
- Durable project-specific rules should be mirrored in `.agents/overrides/rules.yaml` when they need structured enforcement.

## Progress Records

- User-reported bugs, regressions, behavior anomalies, rule conflicts, template imports, structural migrations, batch renames, and rule changes should leave a progress entry under `.agents/progress/entries/YYYY/`.
- `.agents/PROGRESS.md` is a sliding index. Detailed context belongs in the yearly entry files.

## Notes

- Use this file for repository-specific rationale, not for generated adapter content.
- Keep this lightweight unless the project actually needs a heavier governance toolchain.
