# Autograph Marketplace

The official Git-backed plugin marketplace for Autograph products. This
repository contains install-ready release artifacts, not product source code.
Every plugin directory is imported from a verified immutable release and must
match its retained receipt.

## Install

Register the marketplace once:

```sh
codex plugin marketplace add withAutograph/marketplace
```

Then install an available plugin:

```sh
codex plugin add autograph-app-builder@autograph
```

Refresh installed marketplace metadata with:

```sh
codex plugin marketplace upgrade autograph
```

## Publishing plugins

Product repositories publish deterministic Agent Plugins releases. Run the
**Import plugin release** workflow with the source `owner/repository` and exact
version. It downloads the complete immutable release, verifies GitHub's release
and artifact attestations, checks the release receipt, imports the packaged
Codex marketplace archive, and opens a reviewed pull request.

The same operation can be rehearsed locally with:

```sh
mise run marketplace:import -- \
  --release-dir /absolute/path/to/verified-release \
  --expected-repository https://github.com/withAutograph/example \
  --expected-version 1.2.3
```

The import operation replaces only the matching plugin directory, retains a
normalized receipt under `receipts/`, and regenerates the catalog. Do not edit
anything under `plugins/` or `receipts/` by hand.

Run `mise run check` before proposing a marketplace change.
