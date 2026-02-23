# Phase 3 FK Staged Apply Report

- **Generated (UTC):** 2026-02-22 02:49:23Z
- **Mode:** EXECUTE
- **enable_runtime_fks:** False
- **validate_safe:** False

| Check | Status | Value |
|---|---|---|
| `FK_IS_UID_IID_LI:orphans` | `OK` | `0` |
| `FK_FR_UID_BID_LI:orphans` | `OK` | `0` |
| `FK_CNT_UID_BID_LI:orphans` | `OK` | `0` |
| `FK_IF_UID_BID_LI:orphans` | `OK` | `0` |
| `FK_IS_UID_IID_LI:apply` | `OK` | `ENABLE_NOVALIDATE->ENABLED/NOT VALIDATED` |
| `FK_FR_UID_BID_LI:apply` | `OK` | `ENABLE_NOVALIDATE->ENABLED/NOT VALIDATED` |
| `FK_CNT_UID_BID_LI:apply` | `OK` | `DISABLE_NOVALIDATE->DISABLED/NOT VALIDATED` |
| `FK_IF_UID_BID_LI:apply` | `OK` | `DISABLE_NOVALIDATE->DISABLED/NOT VALIDATED` |
| `FK_IS_UID_IID_LI:final` | `OK` | `ENABLED/NOT VALIDATED` |
| `FK_FR_UID_BID_LI:final` | `OK` | `ENABLED/NOT VALIDATED` |
| `FK_CNT_UID_BID_LI:final` | `OK` | `DISABLED/NOT VALIDATED` |
| `FK_IF_UID_BID_LI:final` | `OK` | `DISABLED/NOT VALIDATED` |
| `FK_CONTENT_BOOK:legacy` | `OK` | `DISABLED/NOT VALIDATED` |

## Notes

- Runtime-sensitive FKs (`TOMEHUB_CONTENT`, `TOMEHUB_INGESTED_FILES`) remain disabled by default in this stage.
- Enable them only after write-path ordering is verified under load.
