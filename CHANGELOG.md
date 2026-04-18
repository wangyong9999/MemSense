# Changelog

Release notes live in the documentation site:

- [`hindsight-docs/src/pages/changelog/index.md`](hindsight-docs/src/pages/changelog/index.md)
- [GitHub Releases](https://github.com/vectorize-io/hindsight/releases) (artefacts, SBOMs, signatures)

Integrations track their own history, e.g. [`hindsight-integrations/claude-code/CHANGELOG.md`](hindsight-integrations/claude-code/CHANGELOG.md).

When you add a user-facing change, add an entry under the next version heading in the docs changelog (Features / Improvements / Bug Fixes). `scripts/release.sh <version>` refuses to tag without one.
