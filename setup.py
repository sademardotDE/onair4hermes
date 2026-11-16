from pathlib import Path

from setuptools import setup

# Das Repository-Wurzelverzeichnis *ist* das Python-Paket ``onair4hermes``
# (Hermes-Verzeichnis-Plugin mit plugin.yaml + __init__.py). Deshalb wird das
# Paket explizit auf "." gemappt; ein klassisches src-Layout gibt es hier nicht.
ROOT = Path(__file__).resolve().parent

setup(
    name="onair4hermes",
    version="0.2.0",
    description="Hermes-Plugin für OnAir (SDR / Funküberwachung)",
    long_description=(ROOT / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="fm",
    license="GPL-3.0-or-later",
    url="https://github.com/sademardotDE/onair4hermes",
    packages=["onair4hermes"],
    package_dir={"onair4hermes": "."},
    package_data={
        "onair4hermes": [
            "plugin.yaml",
            "plugin.json",
            "onair_devices.json",
            "desktop/plugin.js",
            "dashboard/manifest.json",
            "dashboard/plugin_api.py",
        ],
    },
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "onair4hermes=onair4hermes.hermes_plugin:main",
        ],
    },
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: POSIX :: Linux",
    ],
)
