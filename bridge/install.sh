#!/usr/bin/env bash
# Build the After Effects MCP bridge this plugin talks to.
#
# Upstream (Dakkshin/after-effects-mcp) is cloned at the exact commit the patch was made
# against, then runJsx.patch is applied. Nothing is forked or vendored here: see
# docs/design.md §10 — whether to ship a fork is still an open decision.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${AESTUDIO_BRIDGE_SRC:-$HOME/.ae-video-studio/after-effects-mcp}"
REPO="${AESTUDIO_BRIDGE_REPO:-https://github.com/Dakkshin/after-effects-mcp.git}"
BASE="$(tr -d '[:space:]' < "$HERE/base-commit.txt")"

for tool in git node npm; do
  command -v "$tool" >/dev/null || { echo "error: $tool is required but not installed" >&2; exit 1; }
done

if [ -e "$TARGET/build/index.js" ]; then
  echo "already built: $TARGET"
  echo "delete that folder and re-run to rebuild."
  exit 0
fi

if [ -e "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null)" ]; then
  echo "error: $TARGET exists and is not empty, and holds no build." >&2
  echo "move it aside, or set AESTUDIO_BRIDGE_SRC to another path." >&2
  exit 1
fi

echo "cloning $REPO"
mkdir -p "$(dirname "$TARGET")"
git clone --quiet "$REPO" "$TARGET"
git -C "$TARGET" checkout --quiet "$BASE"
echo "applying runJsx.patch at $BASE"
git -C "$TARGET" apply "$HERE/runJsx.patch"
echo "building"
(cd "$TARGET" && npm install --silent && npm run build --silent)

cat <<DONE

built: $TARGET/build/index.js

Two steps left, both inside After Effects:
  1. Install the panel: copy the bridge's ScriptUI panel into
     "/Applications/Adobe After Effects 2026/Scripts/ScriptUI Panels/"
  2. Window > mcp-bridge-auto.jsx, and tick Auto-run.

Then check it end to end:
  python3 -m aestudio doctor --ping
DONE
