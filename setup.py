from setuptools import setup

setup(
    name="onair4hermes",
    version="0.1.0",
    description="Hermes-Plugin für OnAir (SDR / Funküberwachung)",
    author="fm",
    license="GPL-3.0-or-later",
    py_modules=["hermes_plugin", "onair_client"],
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "onair4hermes=hermes_plugin:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: POSIX :: Linux",
    ],
)
