# Kailash SDK Changelog

This directory contains the organized changelog for the Kailash Python SDK.

## Structure

- **[unreleased/](unreleased/)** - Changes that haven't been released yet
- **[releases/](releases/)** - Individual release changelogs organized by version and date

## Current Version

The current version is **0.9.5** (released 2025-07-31).

## Recent Releases

- [v0.9.5 - 2025-07-31](releases/v0.9.5-2025-07-31.md) - PythonCodeNode Serialization Stability & Testing
- [v0.9.4 - 2025-07-31](releases/v0.9.4-2025-07-31.md) - Critical DataFlow Fixes & Runtime Enhancements
- [v0.9.3 - 2025-01-30](releases/v0.9.3-2025-01-30.md) - ParallelRuntime Test Fix
- [v0.9.0 - 2025-07-27](releases/v0.9.0-2025-07-27.md) - CycleBuilder API Migration
- [v0.8.7 - 2025-01-25](releases/v0.8.7-2025-01-25.md) - MCP Parameter Validation & Phase 2 Enhancements
- [v0.8.6 - 2025-07-22](releases/v0.8.6-2025-07-22.md) - Enhanced Parameter Validation & Debugging
- [v0.8.5 - 2025-01-22](releases/v0.8.5-2025-01-22.md) - Test Infrastructure & Application Framework Enhancement
- [v0.7.0 - 2025-07-10](releases/v0.7.0-2025-07-10.md) - Major Framework Release
- [v0.6.6 - 2025-07-08](releases/v0.6.6-2025-07-08.md) - Infrastructure Enhancements
- [v0.6.5 - 2025-07-08](releases/v0.6.5-2025-07-08.md) - Real MCP Execution Default

## All Releases

### 2025

#### July
- [v0.9.5 - 2025-07-31](releases/v0.9.5-2025-07-31.md) - PythonCodeNode Serialization Stability & Testing
- [v0.9.4 - 2025-07-31](releases/v0.9.4-2025-07-31.md) - Critical DataFlow Fixes & Runtime Enhancements
- [v0.9.0 - 2025-07-27](releases/v0.9.0-2025-07-27.md) - CycleBuilder API Migration

#### January
- [v0.9.3 - 2025-01-30](releases/v0.9.3-2025-01-30.md) - ParallelRuntime Test Fix
- [v0.8.7 - 2025-01-25](releases/v0.8.7-2025-01-25.md) - MCP Parameter Validation & Phase 2 Enhancements
- [v0.8.6 - 2025-07-22](releases/v0.8.6-2025-07-22.md) - Enhanced Parameter Validation & Debugging
- [v0.8.5 - 2025-01-22](releases/v0.8.5-2025-01-22.md) - Test Infrastructure & Application Framework Enhancement

#### Previous July
- [v0.7.0 - 2025-07-10](releases/v0.7.0-2025-07-10.md)
- [v0.6.6 - 2025-07-08](releases/v0.6.6-2025-07-08.md)
- [v0.6.5 - 2025-07-08](releases/v0.6.5-2025-07-08.md)
- [v0.6.4 - 2025-07-06](releases/v0.6.4-2025-07-06.md)
- [v0.6.3 - 2025-07-05](releases/v0.6.3-2025-07-05.md)

#### June
- [v0.4.2 - 2025-06-18](releases/v0.4.2-2025-06-18.md)
- [v0.4.1 - 2025-06-16](releases/v0.4.1-2025-06-16.md)
- [v0.4.0 - 2025-06-15](releases/v0.4.0-2025-06-15.md)
- [v0.3.2 - 2025-06-11](releases/v0.3.2-2025-06-11.md)
- [v0.3.1 - 2025-06-11](releases/v0.3.1-2025-06-11.md)
- [v0.3.0 - 2025-06-10](releases/v0.3.0-2025-06-10.md)
- [v0.2.2 - 2025-06-10](releases/v0.2.2-2025-06-10.md)
- [v0.2.1 - 2025-06-09](releases/v0.2.1-2025-06-09.md)
- [v0.2.0 - 2025-06-08](releases/v0.2.0-2025-06-08.md)
- [v0.1.6 - 2025-06-05](releases/v0.1.6-2025-06-05.md)
- [v0.1.5 - 2025-06-05](releases/v0.1.5-2025-06-05.md)
- [v0.1.4 - 2025-06-04](releases/v0.1.4-2025-06-04.md)
- [v0.1.3 - 2025-06-03](releases/v0.1.3-2025-06-03.md)
- [v0.1.2 - 2025-06-03](releases/v0.1.2-2025-06-03.md)
- [v0.1.1 - 2025-06-02](releases/v0.1.1-2025-06-02.md)

#### May
- [v0.1.4 - 2025-05-31](releases/v0.1.4-2025-05-31.md)
- [v0.1.1 - 2025-05-31](releases/v0.1.1-2025-05-31.md)
- [v0.1.0 - 2025-05-31](releases/v0.1.0-2025-05-31.md)

## Format

All changelogs follow the [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) format and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Website Integration

This changelog structure is designed to be easily parseable by static site generators and changelog aggregation services. Each release file contains:

- Version number and release date in the filename
- Markdown-formatted content with consistent section headings
- Standard Keep a Changelog sections (Added, Changed, Deprecated, Removed, Fixed, Security)

Common tools that can parse this structure:
- [Changesets](https://github.com/changesets/changesets)
- [Release Drafter](https://github.com/release-drafter/release-drafter)
- [Conventional Changelog](https://github.com/conventional-changelog/conventional-changelog)
- Jekyll/Hugo/Gatsby with custom parsers
- GitHub's release notes generator
