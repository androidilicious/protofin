"""Plugin discovery: every folder under decision_support/plugins with a manifest.json and a plugin.py.

plugin.py exposes `build(root: Path, manifest: Manifest) -> Plugin`. Plugins are loaded by file path, so
a folder is the unit of contribution: copy one, edit the manifest, point `data` at saved answers.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Dict, Iterable

from .contract import Manifest, Plugin, repo_root

PLUGINS_DIR = Path(__file__).resolve().parent / "plugins"


def discover(plugins_dir: Path = PLUGINS_DIR) -> Dict[str, Manifest]:
    out: Dict[str, Manifest] = {}
    for mf in sorted(plugins_dir.glob("*/manifest.json")):
        m = Manifest.from_dict(json.loads(mf.read_text(encoding="utf-8")))
        if m.name != mf.parent.name:
            raise ValueError(f"{mf}: manifest name {m.name!r} must equal the folder name {mf.parent.name!r}")
        if m.name in out:
            raise ValueError(f"duplicate plugin name {m.name}")
        out[m.name] = m
    return out


def load(name: str, plugins_dir: Path = PLUGINS_DIR, root: Path | None = None) -> Plugin:
    folder = plugins_dir / name
    manifest = Manifest.from_dict(json.loads((folder / "manifest.json").read_text(encoding="utf-8")))
    spec = importlib.util.spec_from_file_location(f"decision_support.plugins.{name}", folder / "plugin.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.build(root or repo_root(), manifest)


def load_all(names: Iterable[str] | None = None, plugins_dir: Path = PLUGINS_DIR, root: Path | None = None) -> Dict[str, Plugin]:
    found = discover(plugins_dir)
    wanted = list(names) if names else list(found)
    unknown = [n for n in wanted if n not in found]
    if unknown:
        raise KeyError(f"unknown plugins {unknown}; available: {sorted(found)}")
    return {n: load(n, plugins_dir, root) for n in wanted}
