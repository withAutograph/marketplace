#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = [
    "autograph_start",
    "autograph_get",
    "autograph_send",
    "autograph_respond",
    "autograph_cancel",
]


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_member(member: tarfile.TarInfo) -> None:
    path = PurePosixPath(member.name)
    if (
        not member.isfile()
        or path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or member.issym()
        or member.islnk()
    ):
        raise ValueError(f"Unsafe marketplace archive member: {member.name}")


def verify_checksums(release_dir: Path) -> None:
    lines = (release_dir / "SHA256SUMS").read_text().splitlines()
    if len(lines) != 2:
        raise ValueError("SHA256SUMS must contain exactly the two release archives.")
    for line in lines:
        expected, separator, name = line.partition("  ")
        if not separator or Path(name).name != name or len(expected) != 64:
            raise ValueError("SHA256SUMS contained an invalid entry.")
        path = release_dir / name
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            raise ValueError(f"Release checksum failed for {name}.")


def import_release(release_dir: Path, repository: str, version: str) -> str:
    release_dir = release_dir.resolve(strict=True)
    verify_checksums(release_dir)
    receipt = load_json(release_dir / "release-receipt.json")
    required = {
        "format",
        "specification",
        "name",
        "version",
        "source",
        "endpoint",
        "archive",
        "codexMarketplaceArchive",
        "codexMarketplaceAssets",
        "coreFiles",
        "auxiliaryFiles",
        "tools",
    }
    if set(receipt) != required:
        raise ValueError("Release receipt keys are not closed.")
    if receipt["format"] != "autograph-portable-plugin-release-v3" or receipt["specification"] != "1.0.0":
        raise ValueError("Unsupported release receipt format.")
    if receipt["version"] != version or receipt["source"].get("repository") != repository:
        raise ValueError("Release identity did not match the requested immutable source.")
    name = receipt["name"]
    if not isinstance(name, str) or not name:
        raise ValueError("Release plugin name was invalid.")
    if name == "autograph-app-builder" and receipt["tools"] != EXPECTED_TOOLS:
        raise ValueError("App Builder release did not expose exactly five Autograph tools.")
    endpoint = receipt["endpoint"]
    if not isinstance(endpoint, str) or not endpoint.startswith("https://") or not endpoint.endswith("/mcp"):
        raise ValueError("Release endpoint must be canonical HTTPS /mcp.")
    archive_record = receipt["codexMarketplaceArchive"]
    archive = release_dir / archive_record["name"]
    if Path(archive_record["name"]).name != archive_record["name"] or digest(archive) != archive_record["sha256"]:
        raise ValueError("Marketplace archive did not match its release receipt.")

    with tempfile.TemporaryDirectory(prefix="autograph-marketplace-import-") as temporary:
        extracted = Path(temporary)
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            if not members:
                raise ValueError("Marketplace archive was empty.")
            for member in members:
                safe_member(member)
            bundle.extractall(extracted, members=members, filter="data")
        source = extracted / "plugins" / name
        if not source.is_dir():
            raise ValueError("Marketplace archive omitted its plugin package.")
        packaged_catalog = load_json(extracted / ".agents/plugins/marketplace.json")
        entries = packaged_catalog.get("plugins")
        if not isinstance(entries, list) or len(entries) != 1 or entries[0].get("name") != name:
            raise ValueError("Release marketplace catalog did not identify exactly its plugin.")
        expected_top = {".agents", "plugins"}
        if {path.name for path in extracted.iterdir()} != expected_top:
            raise ValueError("Marketplace archive contained unexpected top-level content.")

        destination = ROOT / "plugins" / name
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination)

    files = {
        path.relative_to(destination).as_posix(): digest(path)
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    }
    normalized = {
        "format": "autograph-marketplace-import-v1",
        "name": name,
        "version": version,
        "source": receipt["source"],
        "endpoint": endpoint,
        "releaseArchive": archive_record,
        "tools": receipt["tools"],
        "marketplaceFiles": files,
    }
    receipt_path = ROOT / "receipts" / name / f"{version}.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(normalized, indent=2) + "\n")

    catalog_path = ROOT / ".agents/plugins/marketplace.json"
    catalog = load_json(catalog_path)
    imported = entries[0]
    retained = [entry for entry in catalog.get("plugins", []) if entry.get("name") != name]
    catalog["plugins"] = sorted([*retained, imported], key=lambda entry: entry["name"])
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n")
    return name


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", required=True, type=Path)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-version", required=True)
    arguments = parser.parse_args()
    name = import_release(
        arguments.release_dir,
        arguments.expected_repository,
        arguments.expected_version,
    )
    print(f"Imported verified release for {name} {arguments.expected_version}.")


if __name__ == "__main__":
    main()
