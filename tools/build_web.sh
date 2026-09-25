#!/bin/sh
# Assemble the web version into build/web (or $1): the web/ app plus the shared stylesheet,
# fonts and the public-domain Coverdale Psalter from lectern/resources. No RSV-2CE text is included.
set -e
root=$(cd "$(dirname "$0")/.." && pwd)
out=${1:-"$root/build/web"}
rm -rf "$out"
mkdir -p "$out/fonts"
cp "$root"/web/* "$out/"
res="$root/lectern/resources"
cp "$res/reader.css" "$res/coverdale.json" "$res/icon.svg" "$out/"
cp "$res"/fonts/* "$out/fonts/"
touch "$out/.nojekyll"
echo "Built $out"
