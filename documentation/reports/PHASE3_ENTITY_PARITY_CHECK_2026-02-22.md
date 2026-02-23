# Phase 3 Entity Parity Check Report

- **Generated (UTC):** 2026-02-22 23:08:22Z
- **Include test users:** False

## Summary

| UID | Status | FS Total | ORA Total | FS Supported | ORA Supported | Missing in Oracle | Extra in Oracle | Failed Items | Note |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `vpq1p0UzcCSLAh1d18WgZZWPBE63` | `WARN` | 226 | 226 | 181 | 226 | 0 | 45 | 0 | oracle_extra_items=45 (oracle_native=45, non_native=0) |

- `vpq1p0UzcCSLAh1d18WgZZWPBE63` FS by type: `{'ARTICLE': 2, 'BOOK': 160, 'PERSONAL_NOTE': 15, 'WEBSITE': 4}`
- `vpq1p0UzcCSLAh1d18WgZZWPBE63` ORA by type: `{'ARTICLE': 2, 'BOOK': 205, 'PERSONAL_NOTE': 15, 'WEBSITE': 4}`
- `vpq1p0UzcCSLAh1d18WgZZWPBE63` ORA by type (FS-key overlap): `{'ARTICLE': 2, 'BOOK': 160, 'PERSONAL_NOTE': 15, 'WEBSITE': 4}`
