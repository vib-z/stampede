#!/bin/bash
# render.sh [name ...]: render docs/images/src/<name>.html to docs/images/<name>.png, 1800 px wide.
# Each source sets its height in <meta name="render-height" content="N">. With no names, renders every source.
# Needs Chrome or Chromium; set CHROME to its path if it is not found.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"; OUT="$(dirname "$SRC")"
CHROME="${CHROME:-}"
if [ -z "$CHROME" ]; then
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "/Applications/Chromium.app/Contents/MacOS/Chromium" \
           "$(command -v google-chrome || true)" "$(command -v chromium || true)" "$(command -v chromium-browser || true)"; do
    [ -n "$c" ] && [ -x "$c" ] && { CHROME="$c"; break; }
  done
fi
[ -x "$CHROME" ] || { echo "render.sh: Chrome not found; set CHROME=<path>" >&2; exit 1; }
names=("$@"); [ ${#names[@]} -gt 0 ] || names=($(cd "$SRC" && ls *.html | sed 's/\.html$//'))
PROFILE="$(mktemp -d)"; trap 'rm -rf "$PROFILE"' EXIT
for n in "${names[@]}"; do
  f="$SRC/$n.html"; [ -f "$f" ] || { echo "render.sh: no $f" >&2; exit 2; }
  h=$(sed -n 's/.*<meta name="render-height" content="\([0-9]*\)".*/\1/p' "$f" | head -1); h=${h:-1000}
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 --user-data-dir="$PROFILE" \
    --window-size="1800,$h" --screenshot="$OUT/$n.png" "file://$f" >/dev/null 2>&1
  echo "$OUT/$n.png 1800x$h"
done
