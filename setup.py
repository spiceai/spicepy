#!/usr/bin/env python3
"""spicedata is a package to easy access data from the spice Apache Flight endpoints.

"""


import setuptools


def setup_package():
    setuptools.setup(
        name="spicedata",
        version="0.1.0",
        maintainer="Spice AI, Inc.",
        maintainer_email="webmaster@spiceai.io"
        author="Corentin Risselin",
        author_email="corentin@spiceai.io",
        url="https://github.com/spicehq/spicedata-py",
        description="Spice.xyz Python SDK - data and AI infrastructure for web3.",
        license="Apache 2.0",
        packages=["spicedata"],
        install_requires=["pyarrow", "pandas"],
        python_requires=">=3.7",
    )


if __name__ == "__main__":
    setup_package()
