# Changelog

Hindsight's release notes are maintained in the documentation site so
they can be styled, cross-linked, and published to every release.

- **Full changelog (user-facing changes):**
  [`hindsight-docs/src/pages/changelog/index.md`](hindsight-docs/src/pages/changelog/index.md)
  — also published at
  [hindsight.vectorize.io/changelog](https://hindsight.vectorize.io/changelog)
- **GitHub Releases (every tag, with bundled artefacts, SBOMs, signatures):**
  [github.com/vectorize-io/hindsight/releases](https://github.com/vectorize-io/hindsight/releases)
- **Integration-specific changelogs** live under each integration directory,
  e.g. [`hindsight-integrations/claude-code/CHANGELOG.md`](hindsight-integrations/claude-code/CHANGELOG.md).

## For contributors

When you add a user-facing feature, improvement, or bug fix, add an entry to
`hindsight-docs/src/pages/changelog/index.md` under the next unreleased
version heading. Group entries by **Features / Improvements / Bug Fixes**.
Internal maintenance and infrastructure changes are intentionally omitted
from this file — they live in git history.

`scripts/release.sh <version>` verifies the target version has a
`## [<version>]` section in the docs changelog before tagging.
