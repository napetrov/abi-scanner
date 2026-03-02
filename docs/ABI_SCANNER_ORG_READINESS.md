# ABI Scanner — Org Readiness RFC (Draft)

## Goal
Make `abi-scanner` usable as a standard compatibility gate across many products/channels (conda/apt/local), not tied to a single project.

## 1) Canonical Report Schema v1 (JSON)
```json
{
  "schema_version": "1.0",
  "run": {
    "run_id": "uuid",
    "timestamp_utc": "ISO-8601",
    "tool_version": "string",
    "command": "string",
    "env_fingerprint": "string",
    "policy_pack": "strict|balanced|exploratory"
  },
  "target": {
    "product": "string",
    "channel": "conda|apt|local",
    "package": "string",
    "library": "string"
  },
  "summary": {
    "transitions_total": 0,
    "transitions_scanned": 0,
    "transitions_skipped": 0,
    "semver_compliance_percent": 0.0,
    "status_counts": {"NO_CHANGE":0,"COMPATIBLE":0,"BREAKING":0},
    "risk_level": "low|medium|high"
  },
  "transitions": [
    {
      "id": "stable-id",
      "from_version": "string",
      "to_version": "string",
      "semver_type": "PATCH|MINOR|MAJOR|UNKNOWN",
      "status": "NO_CHANGE|COMPATIBLE|BREAKING|SKIPPED",
      "policy_decision": "ALLOW|WARN|BLOCK|SOFT_FAIL",
      "confidence": 0.0,
      "counts": {
        "public": {"removed":0,"added":0},
        "preview": {"removed":0,"added":0},
        "internal": {"removed":0,"added":0}
      },
      "skip": {
        "code": "LIB_NOT_FOUND|BASELINE_FAIL|EXTRACT_FAIL|TOOL_ERROR|TIMEOUT|N/A",
        "message": "string"
      },
      "artifacts": {
        "old_abi": "path",
        "new_abi": "path",
        "diff": "path"
      }
    }
  ],
  "metrics": {
    "duration_sec": 0.0,
    "cache_hit_ratio": 0.0,
    "bytes_processed": 0,
    "report_size_bytes": 0
  }
}
```

## 2) Policy Matrix (default)
- **BLOCK**: public removals in PATCH/MINOR, or confidence >= 0.8 breaking evidence.
- **WARN**: public additions-only, preview/internal churn, low-confidence break signal.
- **ALLOW**: no-change / compatible transitions.
- **SOFT_FAIL**: tool/infra failures above threshold (e.g., skipped > 20%).

## 3) Skip Taxonomy (required)
- `LIB_NOT_FOUND`
- `BASELINE_FAIL`
- `EXTRACT_FAIL`
- `DOWNLOAD_FAIL`
- `PARSER_FAIL`
- `TIMEOUT`
- `TOOL_ERROR`
- `POLICY_DISABLED`

## 4) Tiered Reporting
1. **L1 Exec Summary**: compliance %, risk level, top blockers, trend delta.
2. **L2 Release Table**: transition-by-transition decision and reason code.
3. **L3 Engineering Detail**: symbol lists (optional/top-N by default, full on demand).

## 5) CI Contract
Exit codes split by class:
- `0`: scan complete, policy ALLOW/WARN only
- `10`: policy BLOCK
- `20`: infra/tool partial failure (SOFT_FAIL)
- `30`: fatal tooling failure

## 6) Rollout Plan 30/60/90
### 0–30 days
- Freeze schema v1
- Implement skip taxonomy + confidence field
- Add policy packs and decision field

### 31–60 days
- Add portfolio aggregator (multi-product dashboard JSON)
- Add trend metrics and stable transition IDs
- Publish PR/nightly markdown templates

### 61–90 days
- Gate 3 pilot product lines in CI
- Define SLOs (runtime, skip ratio, false-block rate)
- Promote to org standard + onboarding checklist

## 7) Adoption Checklist (per team)
- [ ] Chosen policy pack documented
- [ ] Library target and channel normalized
- [ ] CI gate mapped to exit-code contract
- [ ] Skip threshold set and monitored
- [ ] Owner assigned for weekly report review
- [ ] Trend dashboard wired for release meetings
