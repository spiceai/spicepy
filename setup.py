#!/usr/bin/env python3
"""spicedata is a package to easy access data from the spice Apache Flight endpoints.

"""


import setuptools


def setup_package():
    setuptools.setup(
        name='spicedata',
        version='0.1.0',
        maintainer='SpiceAI',
        author='Corentin Risselin',
        author_email='corentin@spiceai.io',
        url='https://github.com/spicehq/spicedata-py',
        description='Simple Apache Arrow Flight endpoint access',
        license='MIT',
        packages=['spicedata'],
        install_requires=['pyarrow', 'pandas'],
        python_requires='>=3.8'
    )


if __name__ == '__main__':
    setup_package()
