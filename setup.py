#!/usr/bin/env python3
"""Setup script for abi-scanner."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="abi-scanner",
    version="0.1.0-dev",
    description="Universal ABI compatibility checker for C/C++ libraries",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Nikolay Petrov",
    author_email="nikolay.a.petrov@intel.com",
    url="https://github.com/napetrov/abi-scanner",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "click>=8.0",
    ],
    entry_points={
        "console_scripts": [
            "abi-scanner=abi_scanner.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="abi compatibility checker semver c++ shared-library",
)
