#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / ".agents/plugins/marketplace.json"
NAME = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")
HASH = re.compile(r"^[0-9a-f]{64}$")
TOOLS = [
    "autograph_start",
    "autograph_get",
    "autograph_send",
    "autograph_respond",
    "autograph_cancel",
]


def fail(message: str) -> None:
    raise ValueError(message)


def load_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        fail(f"Expected a regular file: {path.relative_to(ROOT)}")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        fail(f"Invalid JSON at {path.relative_to(ROOT)}: {error}")
    if not isinstance(value, dict):
        fail(f"Expected an object at {path.relative_to(ROOT)}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate() -> None:
    catalog = load_json(CATALOG)
    if set(catalog) != {"name", "interface", "plugins"}:
        fail("Marketplace catalog keys are not closed.")
    if catalog["name"] != "autograph":
        fail("Marketplace name must be autograph.")
    if catalog["interface"] != {"displayName": "Autograph"}:
        fail("Marketplace display name must be Autograph.")
    plugins = catalog["plugins"]
    if not isinstance(plugins, list):
        fail("Marketplace plugins must be an array.")
    names: set[str] = set()
    for entry in plugins:
        if not isinstance(entry, dict) or set(entry) != {
            "name",
            "source",
            "policy",
            "category",
        }:
            fail("Marketplace plugin entry keys are not closed.")
        name = entry["name"]
        if not isinstance(name, str) or not NAME.fullmatch(name) or name in names:
            fail("Marketplace plugin names must be unique valid identifiers.")
        names.add(name)
        if entry["source"] != {"source": "local", "path": f"./plugins/{name}"}:
            fail(f"Plugin {name} must use its local verified package.")
        if entry["policy"] != {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        }:
            fail(f"Plugin {name} has unsupported installation policy.")
        if not isinstance(entry["category"], str) or not entry["category"]:
            fail(f"Plugin {name} requires a category.")

        plugin_root = ROOT / "plugins" / name
        manifest = load_json(plugin_root / ".codex-plugin/plugin.json")
        portable = load_json(plugin_root / "plugin.json")
        adapter = load_json(plugin_root / ".mcp.json")
        receipt = load_json(ROOT / "receipts" / name / f"{portable.get('version')}.json")
        if manifest.get("name") != name or portable.get("name") != name:
            fail(f"Plugin {name} package identity does not match its directory.")
        if manifest.get("version") != portable.get("version"):
            fail(f"Plugin {name} manifest versions disagree.")
        if receipt.get("name") != name or receipt.get("version") != portable.get("version"):
            fail(f"Plugin {name} receipt identity does not match its package.")
        endpoint = receipt.get("endpoint")
        if not isinstance(endpoint, str) or not endpoint.startswith("https://") or not endpoint.endswith("/mcp"):
            fail(f"Plugin {name} receipt endpoint is not canonical HTTPS /mcp.")
        if adapter != {"mcpServers": {name: {"type": "http", "url": endpoint}}}:
            fail(f"Plugin {name} adapter is not bound to its receipt endpoint.")
        if receipt.get("tools") != TOOLS and name == "autograph-app-builder":
            fail("App Builder must expose exactly the five Autograph tools.")
        files = receipt.get("marketplaceFiles")
        if not isinstance(files, dict) or not files:
            fail(f"Plugin {name} receipt file inventory is absent.")
        actual: dict[str, str] = {}
        for path in sorted(plugin_root.rglob("*")):
            if path.is_symlink():
                fail(f"Plugin {name} contains a symbolic link.")
            if path.is_file():
                relative = path.relative_to(plugin_root).as_posix()
                actual[relative] = sha256(path)
        if actual != files or any(not HASH.fullmatch(value) for value in files.values()):
            fail(f"Plugin {name} files do not match its immutable receipt.")

    actual_dirs = sorted(path.name for path in (ROOT / "plugins").glob("*") if path.is_dir()) if (ROOT / "plugins").exists() else []
    if actual_dirs != sorted(names):
        fail("Plugin directories do not exactly match the marketplace catalog.")


if __name__ == "__main__":
    try:
        validate()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    print("Marketplace catalog and verified plugin packages are valid.")
