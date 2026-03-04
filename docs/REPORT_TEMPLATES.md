# ABI Scanner Report Templates

## 1) PR Comment Template (short)

```markdown
### ABI Compatibility Gate
- Target: `<channel>:<package>` (`<library>`)
- Compared: `<from_version>` → `<to_version>` (`<semver_type>`)
- Status: `<NO_CHANGE|COMPATIBLE|BREAKING|SKIPPED>`
- Policy decision: `<ALLOW|WARN|BLOCK|SOFT_FAIL>`
- Confidence: `<0.00-1.00>`

Counts:
- Public: `-<removed> +<added>`
- Preview: `-<removed> +<added>`
- Internal: `-<removed> +<added>`

If skipped:
- Skip code: `<SKIP_CODE>`
- Reason: `<message>`

Artifacts:
- Report: `<link-or-path>`
- Diff: `<link-or-path>`
```

---

## 2) Nightly Dashboard Template (portfolio)

```markdown
# Nightly ABI Health
Date: `<YYYY-MM-DD>`

## Portfolio Summary
- Products scanned: `<N>`
- Transitions total: `<N>`
- Scanned: `<N>`
- Skipped: `<N>` (`<percent>%`)
- SemVer compliance (weighted): `<percent>%`

## Decision Distribution
- ALLOW: `<N>`
- WARN: `<N>`
- BLOCK: `<N>`
- SOFT_FAIL: `<N>`

## Top Risks
| Product | Transition | Decision | Reason |
|---|---|---|---|
| `<product>` | `<from→to>` | `<BLOCK>` | `<public removals in patch>` |

## Skip Breakdown
| Skip code | Count | % |
|---|---:|---:|
| LIB_NOT_FOUND | `<N>` | `<%>` |
| BASELINE_FAIL | `<N>` | `<%>` |
| EXTRACT_FAIL | `<N>` | `<%>` |
| DOWNLOAD_FAIL | `<N>` | `<%>` |
| PARSER_FAIL | `<N>` | `<%>` |
| POLICY_DISABLED | `<N>` | `<%>` |
| TOOL_ERROR | `<N>` | `<%>` |
| TIMEOUT | `<N>` | `<%>` |

## Runtime/Cost Metrics
- Median run duration: `<sec>`
- P95 duration: `<sec>`
- Cache hit ratio: `<percent>%`
- Total report size: `<MB>`
```

---

## 3) Exec Summary Template (one-pager)

```markdown
# ABI Compatibility Executive Summary
Period: `<week/month>`

## Headline
- Overall compatibility posture: `<GREEN|YELLOW|RED>`
- SemVer compliance: `<percent>%` (Δ `<+/-x%>` vs previous period)
- Blocking transitions: `<N>`
- Tool reliability (non-skipped scan ratio): `<percent>%`

## What changed
- New high-risk products: `<list>`
- Improved products: `<list>`
- Recurring failure classes: `<skip_code list>`

## Recommendations (optional)
- `<recommended focus area>`
- `<risk to monitor>`
- `<suggested follow-up>`
```

---

## 4) Machine-readable Minimal JSON (PR/nightly)

```json
{
  "schema_version": "1.0",
  "target": {"channel": "conda", "package": "oneccl-cpu", "library": "libccl.so"},
  "summary": {
    "transitions_total": 9,
    "transitions_scanned": 9,
    "transitions_skipped": 0,
    "semver_compliance_percent": 66.7,
    "status_counts": {"NO_CHANGE": 4, "COMPATIBLE": 2, "BREAKING": 3}
  },
  "top_findings": [
    {
      "from_version": "2021.14.1",
      "to_version": "2021.15.0",
      "semver_type": "MINOR",
      "status": "BREAKING",
      "policy_decision": "BLOCK",
      "confidence": 0.92,
      "counts": {"public": {"removed": 2, "added": 20}}
    }
  ]
}
```
