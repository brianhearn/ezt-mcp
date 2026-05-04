# CHANGELOG

All notable changes to EZT MCP are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Changed (2026-05-04)
- `VISION.md` v0.2.0 — locked MVP tool set (Geocode, Direct Build, Auto Build, Analyze); clarified GeoJSON-as-universal-wire-format; defined Part/Territory/Territory Solution terminology; documented EasyTerritory-hosted infrastructure model (no customer state in EZT MCP); added canonical TS format example
- `CONSTITUTION.md` v0.2.0 — removed separate geocoder microservice (geocoding is internal to MCP); removed per-customer schema model (Postgres holds shared reference data only); added GeoJSON wire format non-negotiable; added dissolve-is-internal non-negotiable; clarified no-customer-data-persisted rule; updated terminology table
- `README.md` — updated to reflect current architecture and MVP tool set

### Added (2026-04-24)
- `CONSTITUTION.md` v0.1.0 — initial architecture, security, stack, and convention non-negotiables
- `VISION.md` v0.1.0 — initial product intent and founding capability definition

---

*Project is pre-implementation. Changelog entries will accumulate as lifecycle phases complete.*
