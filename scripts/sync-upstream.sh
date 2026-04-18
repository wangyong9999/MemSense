#!/bin/bash
# Sync with vectorize-io/hindsight upstream.
#
# Usage:
#   ./scripts/sync-upstream.sh               # show gap; prompt before merge
#   ./scripts/sync-upstream.sh --yes         # merge without prompt
#   ./scripts/sync-upstream.sh --dry-run     # show gap only, no merge
#
# Assumes:
#   - `upstream` remote points to vectorize-io/hindsight
#   - current branch is main (refuses otherwise)
#   - working tree is clean (refuses otherwise)

set -e

UPSTREAM_URL="https://github.com/vectorize-io/hindsight.git"
DRY_RUN=0
AUTO_YES=0

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --yes|-y)  AUTO_YES=1 ;;
        --help|-h)
            sed -n '2,13p' "$0"
            exit 0
            ;;
        *)
            echo "unknown arg: $arg" >&2
            exit 2
            ;;
    esac
done

cd "$(git rev-parse --show-toplevel)"

# Ensure upstream remote exists and points at the right URL.
if ! git remote get-url upstream >/dev/null 2>&1; then
    echo "[info] adding upstream remote → $UPSTREAM_URL"
    git remote add upstream "$UPSTREAM_URL"
fi

CURRENT_URL=$(git remote get-url upstream)
if [ "$CURRENT_URL" != "$UPSTREAM_URL" ]; then
    echo "[warn] upstream remote points at $CURRENT_URL (expected $UPSTREAM_URL)"
    echo "       continuing anyway; fix with:  git remote set-url upstream $UPSTREAM_URL"
fi

BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "main" ]; then
    echo "[error] current branch is '$BRANCH'; switch to main first" >&2
    exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "[error] working tree not clean; commit or stash first" >&2
    git status --short >&2
    exit 1
fi

echo "[info] fetching upstream..."
git fetch upstream --tags --prune --quiet

AHEAD=$(git rev-list --count HEAD..upstream/main)
BEHIND=$(git rev-list --count upstream/main..HEAD)

echo ""
echo "=============================================="
echo "  Gap against upstream/main"
echo "=============================================="
echo "  upstream has:   $AHEAD new commits we lack"
echo "  we have:        $BEHIND commits ahead of upstream (fork-only)"
echo ""

if [ "$AHEAD" -eq 0 ]; then
    echo "[info] already in sync"
    exit 0
fi

echo "  Recent upstream feat/fix commits we'd inherit:"
git log HEAD..upstream/main --oneline --no-merges \
    | grep -iE "^[a-f0-9]+ (feat|fix|perf|security)" \
    | head -15 \
    | sed 's/^/    /'
echo ""

# Tags upstream added since our last sync point.
NEW_TAGS=$(git tag --contains HEAD..upstream/main 2>/dev/null \
    | grep -E "^v[0-9]+\." \
    | sort -V \
    | tail -5 \
    || true)
if [ -n "$NEW_TAGS" ]; then
    echo "  Upstream tags in the window:"
    echo "$NEW_TAGS" | sed 's/^/    /'
    echo ""
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[info] dry-run complete; no merge performed"
    exit 0
fi

if [ "$AUTO_YES" -ne 1 ]; then
    read -r -p "Merge upstream/main into main? (y/N) " REPLY
    case "$REPLY" in
        y|Y|yes|YES) ;;
        *) echo "[info] aborted"; exit 0 ;;
    esac
fi

echo ""
echo "[info] merging upstream/main..."
if git merge upstream/main --no-edit; then
    echo "[info] merge clean"
else
    echo ""
    echo "=============================================="
    echo "  Merge conflicts — resolve before committing"
    echo "=============================================="
    git status --short | grep -E "^UU|^AA|^DD" || true
    echo ""
    echo "Steps:"
    echo "  1. Edit the conflicted files"
    echo "  2. git add <files>"
    echo "  3. git commit --no-edit"
    echo "  4. re-run this script with --dry-run to verify"
    exit 3
fi

echo ""
echo "[info] running fork-owned tests to catch regressions..."
if ( cd hindsight-api-slim && uv run pytest tests/test_post_extraction.py tests/test_recall_cache.py -q --no-header ); then
    echo "[info] fork tests pass"
else
    echo "[warn] fork tests failed — investigate before pushing"
    exit 4
fi

echo ""
echo "=============================================="
echo "  Next steps"
echo "=============================================="
echo "  * Review the merge commit:    git log -1"
echo "  * Push main:                  git push origin main"
echo "  * Tag a post-sync release:    ./scripts/release.sh <version>"
