"""Print a value from ci/versions.yml: _versions.py <major> <key>. Single reader of the version file."""

import pathlib
import sys

import yaml

data = yaml.safe_load((pathlib.Path(__file__).resolve().parent.parent / "ci" / "versions.yml").read_text())
print(data["versions"][sys.argv[1]][sys.argv[2]])
