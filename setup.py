"""
s(i)oul – Bauanleitung für die Mac-App (py2app). Nicht direkt aufrufen,
sondern über ./build_app.command, das vorher das Icon erzeugt.
"""
from setuptools import setup

OPTIONS = {
  'iconfile': 'build/sioul.icns',
  # Info.plist: die "Visitenkarte" der App für macOS
  'plist': {
    'CFBundleName': 's(i)oul',
    'CFBundleDisplayName': 's(i)oul',
    'CFBundleIdentifier': 'local.sioul.app',
    'CFBundleShortVersionString': '1.0',
    # Ohne diesen Satz schaltet macOS das Mikrofon für die App komplett ab
    'NSMicrophoneUsageDescription': 's(i)oul nutzt das Mikrofon für die Spracheingabe. '
                                    'Die Aufnahme wird lokal verarbeitet und verlässt deinen Mac nicht.',
    'NSHighResolutionCapable': True,
  },
}

setup(
  name='s(i)oul',
  app=['desktop.py'],
  options={'py2app': OPTIONS},
)
