#!/bin/bash
# Baut "s(i)oul.app" in dist/ als Verweis-App: Die App startet desktop.py aus
# diesem Ordner. Änderungen am Code wirken also sofort, ohne neu zu bauen.
# Nur neu bauen, wenn sich setup.py oder das Icon ändert, oder der Ordner verschoben wird.
set -e
cd "$(dirname "$0")"
rm -rf build dist
mkdir -p build/sioul.iconset

echo "Erzeuge das Icon ..."
# macOS-Icons haben einen Rand: Avatar-Kachel auf ca. 80 % der Fläche
python3.12 - <<'EOF'
src = open('sioul-avatar.svg', encoding='utf-8').read()
inner = src.split('>', 1)[1].rsplit('</svg>', 1)[0]
with open('build/icon.svg', 'w', encoding='utf-8') as f:
  f.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="-8 -8 80 80">{inner}</svg>')
EOF
qlmanage -t -s 1024 -o build build/icon.svg > /dev/null 2>&1
for size in 16 32 128 256 512; do
  sips -z $size $size build/icon.svg.png --out build/sioul.iconset/icon_${size}x${size}.png > /dev/null
  sips -z $((size*2)) $((size*2)) build/icon.svg.png --out build/sioul.iconset/icon_${size}x${size}@2x.png > /dev/null
done
iconutil -c icns build/sioul.iconset -o build/sioul.icns

echo "Baue die App ..."
python3.12 setup.py py2app --alias > /dev/null

echo "Fertig: dist/s(i)oul.app"
echo "Zum Installieren in den Programme-Ordner ziehen und von dort ins Dock."
open dist
