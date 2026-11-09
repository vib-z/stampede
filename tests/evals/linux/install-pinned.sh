#!/bin/bash
# install-pinned.sh: install the pinned Herdr TUI, Herdr Core and moshi-hook from pins.txt into ~/.local/bin, as the
# unprivileged user, each download checked by sha256 before anything is installed. Writes what it installed to
# ~/.local/share/stampede-eval/installed.tsv (name, version line, sha256 of the artefact) for the I01 record.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
case "$(uname -m)" in aarch64|arm64) arch=arm64;; x86_64|amd64) arch=amd64;; *) echo "unsupported arch $(uname -m)" >&2; exit 2;; esac
bin="$HOME/.local/bin"; share="$HOME/.local/share/stampede-eval"; work=$(mktemp -d)
mkdir -p "$bin" "$share"
: > "$share/installed.tsv"
while read -r name a url sha; do
  case "$name" in ''|'#'*) continue;; esac
  [ "$a" = "$arch" ] || continue
  file="$work/$(basename "$url")"
  curl -fsSL --retry 3 -o "$file" "$url"
  echo "$sha  $file" | sha256sum -c - >/dev/null   # a wrong digest stops the build here
  case "$name" in
    herdr) install -m 755 "$file" "$bin/herdr";;
    hc) tar -xzf "$file" -C "$work" herdr-core && install -m 755 "$work/herdr-core" "$bin/herdr-core" && ln -sfn herdr-core "$bin/hc";;
    moshi-hook) tar -xzf "$file" -C "$work" moshi-hook && install -m 755 "$work/moshi-hook" "$bin/moshi-hook";;
  esac
  printf '%s\t%s\t%s\t%s\n' "$name" "$("$bin/$name" --version 2>&1 | head -1)" "$sha" "$url" >> "$share/installed.tsv"
done < "$here/pins.txt"
rm -rf "$work"
cat "$share/installed.tsv"
