"""Setup script for building Token Meter as a macOS .app bundle using py2app."""

from setuptools import setup

APP = ["token_meter.py"]
APP_NAME = "Token Meter"
APP_VERSION = "1.0.0"

OPTIONS = {
    "argv_emulation": False,
    "iconfile": "icon.icns",
    "packages": ["rumps", "requests"],
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.tokenmeter.app",
        "CFBundleVersion": APP_VERSION,
        "CFBundleShortVersionString": APP_VERSION,
        "LSUIElement": True,  # Menu bar only — no Dock icon
    },
}

setup(
    name=APP_NAME,
    app=APP,
    version=APP_VERSION,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
    install_requires=["rumps", "requests"],
)
