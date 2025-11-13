# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Reorganize source files
- Log debug via uvicorn logger

## [2.6.0] - 2025-11-12

### Changed

- Fix collector model value.
- Add debug mode.

## [2.4.2] - 2025-11-12

### Changed

- Fix multiagent setup

## [2.4.1] - 2025-11-12

- Fix Dockerfile

## [2.4.0] - 2025-11-12

- Use a multiagent setup

## [2.3.0] - 2025-11-11

### Change

- Change endpoint to serve on / instead of /run

## [2.2.0] - 2025-11-11

### Change

- Change port of the service to 8000
- Improve prompt for single namespace permissions

## [2.1.0] - 2025-11-11

### Changed

- Change to only have org permissions, not cluster-wide permissions.

## [2.0.0] - 2025-11-11

### Changed

- Switch from Job to Deployment. FastAPI will serve an HTTP endpoint for AI debugging.

## [1.1.2] - 2025-10-24

### Changed

- Test release

## [1.1.1] - 2025-10-24

### Changed

- Tag latest when building from main.

## [1.1.0] - 2025-10-23

### Changed

- Use OpenTelemtry exporter directly, not logfire.

## [1.0.0] - 2025-10-23

### Changed

- First release using Pydantic AI and using a single MCP pointing to the


[Unreleased]: https://github.com/giantswarm/shoot/compare/v2.7.0...HEAD
[2.7.0]: https://github.com/giantswarm/shoot/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/giantswarm/shoot/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/giantswarm/shoot/compare/v2.4.2...v2.5.0
[2.4.2]: https://github.com/giantswarm/shoot/compare/v2.4.1...v2.4.2
[2.4.1]: https://github.com/giantswarm/shoot/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/giantswarm/shoot/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/giantswarm/shoot/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/giantswarm/shoot/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/giantswarm/shoot/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/giantswarm/shoot/compare/v1.1.2...v2.0.0
[1.1.2]: https://github.com/giantswarm/shoot/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/giantswarm/shoot/compare/v1.1.1...v1.1.1
[1.1.1]: https://github.com/giantswarm/shoot/compare/v1.0.0...v1.1.1
[1.0.0]: https://github.com/giantswarm/shoot/compare/v0.0.0...v1.0.0
[1.1.0]: https://github.com/giantswarm/shoot/compare/v1.0.0...v1.1.0
