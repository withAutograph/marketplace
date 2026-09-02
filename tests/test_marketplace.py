from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


validator = load_module("validate_marketplace", ROOT / "scripts/validate_marketplace.py")
importer = load_module("import_release", ROOT / "scripts/import_release.py")


class MarketplaceTests(unittest.TestCase):
    def test_app_builder_adapter_binds_oauth_resource_when_present(self) -> None:
        import json

        adapter = json.loads((ROOT / "plugins/app-builder/.mcp.json").read_text())
        server = adapter["mcpServers"]["app-builder"]
        endpoint = json.loads(
            (ROOT / "receipts/app-builder/0.2.5.json").read_text()
        )["endpoint"]
        self.assertEqual(server["url"], endpoint)
        if "oauth_resource" in server:
            self.assertEqual(server["oauth_resource"], endpoint)

    def test_app_builder_authenticates_on_first_use(self) -> None:
        import json

        catalog = json.loads(
            (ROOT / ".agents/plugins/marketplace.json").read_text()
        )
        app_builder = next(
            plugin for plugin in catalog["plugins"] if plugin["name"] == "app-builder"
        )
        self.assertEqual(app_builder["policy"]["authentication"], "ON_USE")

    def test_release_asset_verification_uses_downloaded_path(self) -> None:
        workflow = (ROOT / ".github/workflows/import-release.yml").read_text()
        self.assertIn(
            'gh release verify-asset "v$RELEASE_VERSION" "$asset"', workflow
        )
        self.assertNotIn(
            'gh release verify-asset "v$RELEASE_VERSION" "$(basename "$asset")"',
            workflow,
        )

    def test_empty_catalog_is_valid(self) -> None:
        validator.validate()

    def test_rejects_unsafe_archive_member(self) -> None:
        import tarfile

        member = tarfile.TarInfo("../escape")
        member.type = tarfile.REGTYPE
        with self.assertRaisesRegex(ValueError, "Unsafe marketplace archive member"):
            importer.safe_member(member)

    def test_rejects_non_file_archive_member(self) -> None:
        import tarfile

        member = tarfile.TarInfo("plugins/example")
        member.type = tarfile.DIRTYPE
        with self.assertRaisesRegex(ValueError, "Unsafe marketplace archive member"):
            importer.safe_member(member)

    def test_checksum_inventory_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SHA256SUMS").write_text("")
            with self.assertRaisesRegex(ValueError, "exactly the two release archives"):
                importer.verify_checksums(root)


if __name__ == "__main__":
    unittest.main()
