# Documentation Index

This directory is organized by document purpose and implementation status.

## Project

- [Changelog](../CHANGELOG.md) - notable changes per release.
- [Migration Notes](../MIGRATION.md) - upgrade steps (DB migrations + env vars).

## Plan Status

### Complete

- [Reprocess / Retry Analysis Feature](plans/complete/reprocess-retry.md) - shipped backend endpoint, frontend retry actions, and focused tests.
- [Tauri Desktop Prototype](plans/complete/tauri-prototype.md) - prototype shell is present; the full desktop runtime is tracked separately.

### Partially Complete

- [Installable Local-First Architecture Roadmap](plans/partial/local-first-roadmap.md) - Tauri prototype exists, but packaged backend/worker/storage/queue runtime is not done.
- [Local Search Quality Roadmap](plans/partial/local-search-quality-roadmap.md) - semantic search exists; measurable evaluation, diagnostics, reranking, and scaling work remain planned.
- [Desktop Framework Evaluation](plans/partial/desktop-tauri-vs-electron-adr.md) - Tauri spike exists, but release-grade packaging and updater decisions remain open.
- [Personalization Research](plans/partial/personalization-research.md) - feedback collection exists; adaptive personalization is still planned.
- [Legacy Vault Encryption Design](plans/partial/vault-encryption-design.md) - documents the previous encrypted-blob format retained only for safe migration of existing vault items.
- [Small-Team Authentication](plans/partial/small-team-authentication.md) - backend authentication foundations exist; frontend UI, deletion-request workflow, audit log, and Instance management UI remain planned.

### Not Started

- [Provider-Neutral Object Storage ADR](plans/not-started/storage-provider-neutrality-adr.md)
- [Bulk Rename and Metadata Editing Design](plans/not-started/bulk-rename-metadata-design.md)
- [Desktop Runtime Design ADR](plans/not-started/desktop-runtime-adr.md)
- [Desktop Runtime Detailed Comparison](plans/not-started/desktop-runtime-comparison.md)
- [Desktop Runtime Quick Reference](plans/not-started/desktop-runtime-quick-reference.md)
- [Mobile Strategy ADR](plans/not-started/mobile-strategy.md)
- [Optional Self-Hosted Remote Acceleration](plans/not-started/remote-acceleration.md)

## Guides

- [Common Setup Errors](guides/common-setup-errors.md)
- [Privacy-Safe Diagnostics Bundle](diagnostics-bundle.md)
- [Image Loading Behavior](guides/image-loading.md)
- [Real ML Troubleshooting](guides/real-ml-troubleshooting.md)
- [Features Guide](guides/features.md)
- [Hardware Acceleration](guides/hardware-acceleration.md)
- [PR Triage Automation Dry Run](guides/pr-triage-dry-run.md)
- [TestSprite PR Testing](guides/testsprite-ci.md)

## Policies

- [Agent Security Policy](policies/agent-security.md)
- [Dependency Policy](policies/dependency-policy.md)

## Research

- [Vector Search Benchmark Evaluation](research/vector-search-benchmarks.md)

## Assets

Image and SVG assets used by the README and project documentation live in [assets/](assets/).
