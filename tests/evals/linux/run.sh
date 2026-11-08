#!/bin/bash
# run.sh: the Linux evals in one command, from a Mac or Linux host with Docker.
# Builds the image stampede-eval-linux:<herdr>-<hc>-<moshi> (Ubuntu 24.04, the pinned Herdr TUI, Herdr Core and
# moshi-hook checked by sha256), starts one container named stampede-eval-<stamp>, copies a checkout in (tracked and
# untracked files git does not ignore, never .git), runs inside.sh as an unprivileged user (the install cases I01 to
# I06, the TUI cases T01 to T10 and, when a Core scenario is given or found, the C cases), copies the new run folders
# back into <checkout>/tests/evals/runs/ and removes the container. Exit 1 when a case failed or broke.
# The install cases it records, through install_checks.py: I01 the pinned installs, I02 install.sh twice, I03 herdr-doctor
# plain, --relay and --core, I04 the unit suite, I05 the plugin link and its event hook, I06 moshi-hook unpaired.
#
# usage: tests/evals/linux/run.sh [--src <checkout>] [--label <label>] [--core-script <core_e2e.py>] [--only install|tui|core] [--keep]
#   --src           the checkout under test (default: the one holding this script)
#   --label         the run label prefix (default baseline-linux; the runs are <label>-install, <label>-tui, <label>-core)
#   --core-script   a tests/evals/live/core_e2e.py to copy into the container copy (default: the one in --src if any,
#                   else `git show qa/core-live:tests/evals/live/core_e2e.py` from --src when that branch has it)
#   --only          run one runner only (the TUI and Core runners still get install.sh and the plugin link)
#   --keep          leave the container running for a look (docker exec -it <name> bash); remove it yourself
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
SRC=$(cd "$HERE/../../.." && pwd -P); LABEL=baseline-linux; CORE=""; KEEP=0; ONLY=all
while [ $# -gt 0 ]; do
  case "$1" in
    --src) SRC=$(cd "$2" && pwd -P); shift 2;;
    --label) LABEL=$2; shift 2;;
    --core-script) CORE=$2; shift 2;;
    --only) ONLY=$2; shift 2;;
    --keep) KEEP=1; shift;;
    -h|--help) sed -n '2,15p' "$0"; exit 0;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac
done
command -v docker >/dev/null || { echo "docker is not on PATH: the Linux evals need a Docker daemon (colima is fine)" >&2; exit 3; }
tag=$(awk '!/^#/ && NF && $2=="arm64" {print $3}' "$HERE/pins.txt" | sed -E 's#.*/v?([0-9]+\.[0-9]+\.[0-9]+)/.*#\1#' | paste -sd- -)
IMAGE="stampede-eval-linux:$tag"
STAMP=$(date -u +%Y%m%dT%H%M%SZ); C="stampede-eval-$STAMP"
echo "image $IMAGE (build log: ${TMPDIR:-/tmp}/$C-build.log)"
docker build -t "$IMAGE" "$HERE" >"${TMPDIR:-/tmp}/$C-build.log" 2>&1 || { tail -30 "${TMPDIR:-/tmp}/$C-build.log"; echo "image build failed" >&2; exit 1; }
digest=$(docker image inspect --format '{{.Id}}' "$IMAGE")
commit=$(git -C "$SRC" rev-parse HEAD 2>/dev/null || echo none)
dirty=0; [ -n "$(git -C "$SRC" status --porcelain 2>/dev/null)" ] && dirty=1
extra=$(printf '{"image": "%s", "image_tag": "%s", "host": "%s", "docker": "%s"}' "$digest" "$IMAGE" "$(uname -sm)" "$(docker version --format '{{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}' 2>/dev/null)")
docker run -d --init --name "$C" "$IMAGE" sleep infinity >/dev/null   # --init: a pid 1 that reaps, so an ended process never lingers as a zombie
home=$(docker exec "$C" bash -c 'echo "$HOME"')
cleanup() { [ "$KEEP" = 1 ] && { echo "container $C kept (docker exec -it $C bash; docker rm -f $C when done)"; return; }; docker rm -f "$C" >/dev/null 2>&1 || true; }
trap cleanup EXIT
echo "container $C: copying the checkout from $SRC (commit ${commit:0:12}, dirty $dirty)"
export COPYFILE_DISABLE=1
git -C "$SRC" ls-files -z -co --exclude-standard | (cd "$SRC" && tar --null -T - -cf - --no-xattrs 2>/dev/null) \
  | docker exec -i "$C" bash -c 'mkdir -p "$HOME/stampede" && tar -xf - -C "$HOME/stampede" --warning=no-unknown-keyword'
if [ -z "$CORE" ] && [ ! -f "$SRC/tests/evals/live/core_e2e.py" ] && git -C "$SRC" show qa/core-live:tests/evals/live/core_e2e.py >/dev/null 2>&1; then
  CORE="${TMPDIR:-/tmp}/$C-core_e2e.py"; git -C "$SRC" show qa/core-live:tests/evals/live/core_e2e.py >"$CORE"
  echo "Core scenario: tests/evals/live/core_e2e.py from branch qa/core-live (read-only copy)"
fi
[ -n "$CORE" ] && docker cp "$CORE" "$C:$home/stampede/tests/evals/live/core_e2e.py"
before=$(docker exec "$C" bash -c 'ls "$HOME/stampede/tests/evals/runs" 2>/dev/null' || true)
rc=0
docker exec -e STAMPEDE_EVAL_COMMIT="$commit" -e STAMPEDE_EVAL_DIRTY="$dirty" -e EVAL_EXTRA_JSON="$extra" -e EVAL_ONLY="$ONLY" "$C" \
  bash "$home/stampede/tests/evals/linux/inside.sh" "$LABEL" || rc=$?
mkdir -p "$SRC/tests/evals/runs"
for run in $(docker exec "$C" bash -c 'ls "$HOME/stampede/tests/evals/runs" 2>/dev/null' || true); do
  grep -qx "$run" <<<"$before" && continue
  docker cp "$C:$home/stampede/tests/evals/runs/$run" "$SRC/tests/evals/runs/$run" >/dev/null
  echo "recorded tests/evals/runs/$run: $(sed -n 's/^| \([a-z]*\) | \([0-9]*\) |$/\1 \2/p' "$SRC/tests/evals/runs/$run/summary.md" | awk '$2>0' | paste -sd, - | sed 's/,/, /g')"
done
echo "container exit $rc"
exit $rc
