# Kailash Python SDK - Release Management

This directory contains all release-related documentation organized by type and version.

## Directory Structure

```
releases/
├── notes/           # Detailed release notes for each version
├── checklists/      # Release checklists and procedures
├── announcements/   # Public announcements and summaries
├── CURRENT.md       # Current release information
└── README.md        # This file
```

## Release Notes Organization

### Version Naming Convention
- **Major releases**: `v1.0.0`, `v2.0.0` (breaking changes)
- **Minor releases**: `v0.1.0`, `v0.2.0` (new features)
- **Patch releases**: `v0.1.1`, `v0.1.2` (bug fixes)

### File Naming Convention
- **Release Notes**: `notes/v{version}.md` (e.g., `notes/v0.1.5.md`)
- **Checklists**: `checklists/v{version}-checklist.md`
- **Announcements**: `announcements/v{version}-announcement.md`

## Release Process

1. **Create Release Notes**: Document all changes in `notes/v{version}.md`
2. **Create Checklist**: Use template in `checklists/v{version}-checklist.md`
3. **Update Version**: Bump version in `pyproject.toml`, `CHANGELOG.md`
4. **Create Announcement**: Summary for `announcements/v{version}-announcement.md`
5. **Update Current**: Update `CURRENT.md` with latest release info

## Templates

See the `templates/` subdirectory for standardized templates for:
- Release notes
- Release checklists
- Announcements
- Migration guides

## Archive Policy

- Keep the last 3 major versions
- Keep all minor versions for current major version
- Archive older releases to `archive/` directory when needed
