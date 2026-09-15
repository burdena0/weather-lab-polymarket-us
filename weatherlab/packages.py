"""ZIP contract. Dashboard never executes uploaded source code."""
import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from .core import digest
from .engine import validate_config
from .strategies import STRATEGIES


def inspect_package(raw, trusted_root):
    if len(raw) > 8000000:
        raise ValueError("ZIP exceeds 8 MB")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        names = [f.filename for f in entries]
        if len(entries) > 100 or len(set(names)) != len(names) or len({n.lower() for n in names}) != len(names):
            raise ValueError("Duplicate/oversized ZIP directory")
        if sum(f.file_size for f in entries) > 16000000:
            raise ValueError("Expanded ZIP exceeds 16 MB")
        for f in entries:
            p = PurePosixPath(f.filename)
            if p.is_absolute() or ".." in p.parts or "\\" in f.filename or ":" in f.filename or stat.S_ISLNK(f.external_attr >> 16):
                raise ValueError("Unsafe ZIP path or symlink")
            if p.name == ".env" or "secret" in p.name.lower() or p.suffix in (".pem", ".key"):
                raise ValueError("Credentials must never be uploaded in a bot ZIP")
            if f.file_size > 2000000 or f.flag_bits & 1:
                raise ValueError("Encrypted or oversized ZIP member")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("schema_version") != 1 or manifest.get("runtime") != "weatherlab-1.0.0":
            raise ValueError("Unsupported package runtime")
        config = validate_config(manifest["config"])
        if manifest["bot_id"] != config["strategy"] or manifest["bot_id"] not in STRATEGIES:
            raise ValueError("Package identity mismatch")
        hashes = manifest["files"]
        if set(hashes) != set(names)-{"manifest.json"}:
            raise ValueError("Package file manifest incomplete")
        for name, expected in hashes.items():
            content = archive.read(name)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("Package checksum mismatch")
            if name.endswith((".py", ".cjs")):
                local = Path(trusted_root)/name
                if not local.is_file() or local.read_bytes() != content:
                    raise ValueError("Uploaded code differs from trusted runtime; review/install new runtime separately")
        if "weatherlab/engine.py" not in hashes or "weatherlab/strategies.py" not in hashes:
            raise ValueError("Incomplete standalone package")
        return {"manifest": manifest, "sha256": hashlib.sha256(raw).hexdigest(), "config_hash": digest(config)}
