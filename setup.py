#!/usr/bin/env python3
"""spicepy is the Spice.ai client library.

"""


from setuptools import setup, find_packages

def parse_requirements(filename: str) -> str:
    """Load requirements from a pip requirements file."""
    with open(filename, 'r') as f:
        requirements = f.read().splitlines()

    # Filter out comments or empty lines
    requirements = [req.strip() for req in requirements if req.strip() and not req.startswith('#')]
    return requirements

def parse_markdown(path: str) -> str:
    with open(path, "r", encoding="utf8") as fh:
        return fh.read()

def setup_package():
    setup(
        name="spicepy",
        version="1.0.1",
        maintainer="Spice AI, Inc.",
        maintainer_email="webmaster@spice.ai",
        author="Spice AI, Inc.",
        author_email="webmaster@spice.ai",
        url="https://github.com/spiceai/spicepy",
        description="Spice.ai client library - data and AI infrastructure for web3.",
        license="Apache 2.0",
        classifiers=[
            "Development Status :: 4 - Beta",
            "Intended Audience :: Developers",
            "License :: OSI Approved :: Apache Software License",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "Topic :: Software Development :: Libraries",
        ],
        keywords="spice, AI, web3, data, ML",
        long_description=parse_markdown("README.md"),
        long_description_content_type="text/markdown",
        packages=["spicepy"],
        install_requires=parse_requirements('requirements.txt'),
        extras_require={
            'test': parse_requirements('test.requirements.txt')
        },
        python_requires=">=3.8",
        platforms=["Any"],
    )


if __name__ == "__main__":
    setup_package()
