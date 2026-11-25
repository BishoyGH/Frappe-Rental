"""Emit the CI matrix as JSON from ci/versions.yml (single source of truth)."""
import json
import pathlib

import yaml

root = pathlib.Path(__file__).resolve().parent.parent
data = yaml.safe_load((root / "ci" / "versions.yml").read_text())["versions"]
print(json.dumps({"include": [{"major": m, **{k: str(v) for k, v in d.items()}} for m, d in data.items()]}))
