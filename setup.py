#!/usr/bin/env python3
"""spicepy is the Spice.xyz client library.

"""


from setuptools import setup, find_packages


def setup_package():
    setup(
        name="spicepy",
        version="0.1.0",
        maintainer="Spice AI, Inc.",
        maintainer_email="webmaster@spiceai.io",
        author="Corentin Risselin",
        author_email="corentin@spiceai.io",
        url="https://github.com/spicehq/spice-py",
        description="Spice.xyz client library - data and AI infrastructure for web3.",
        license="Apache 2.0",
        packages=["spicepy"],
        install_requires=["pyarrow", "pandas", "web3>=6.0.0b2"],
        python_requires=">=3.7",
    )


if __name__ == "__main__":
    setup_package()
