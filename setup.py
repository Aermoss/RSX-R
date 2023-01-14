from setuptools import setup, find_packages

import os, sys

with open("README.md", "r", encoding = "UTF-8") as file:
    long_desc = file.read()

with open("MANIFEST.in", "w") as file:
    manifest = "include rsxr/*\ninclude rsxr/asm/*\ninclude rsxr/bin/*\ninclude rsxr/lib/*\n"

    for i in os.listdir("rsxr/include"):
        manifest += f"include rsxr/include/{i}/*\n"

    file.write(manifest)

setup(
    name = "rsxr",
    version = "0.0.2",
    entry_points = {
        "console_scripts": [
            "rsxr = rsxr.main:main"
        ]
    },
    description = "A compiled statically typed multi paradigm general purpose programming language designed for cross platform applications.",
    long_description = long_desc,
    long_description_content_type = "text/markdown",
    url = "https://github.com/Aermoss/RSX-R",
    author = "Yusuf Rencber",
    author_email = "aermoss.0@gmail.com",
    license = "MIT",
    keywords = [],
    packages = find_packages(),
    include_package_data = True,
    install_requires = ["rsxpy"]
)