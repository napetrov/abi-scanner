#!/usr/bin/env python3
"""Compare two ABI baselines and output JSON report.

Backward-compatible wrapper around abi_scanner.analyzer.
"""

import json
import sys
from pathlib import Path

from abi_scanner.analyzer import ABIAnalyzer, PublicAPIFilter


def main() -> int:
    if len(sys.argv) < 5:
        print(
            "Usage: compare_abi.py <baseline_old> <baseline_new> <public_api_old> <public_api_new> [suppressions]",
            file=sys.stderr,
        )
        return 1

    baseline_old = Path(sys.argv[1])
    baseline_new = Path(sys.argv[2])
    api_old_file = Path(sys.argv[3])
    api_new_file = Path(sys.argv[4])
    suppressions = Path(sys.argv[5]) if len(sys.argv) > 5 else None

    if not api_old_file.exists():
        print(f"Public API JSON not found: {api_old_file}", file=sys.stderr)
        return 1
    if not api_new_file.exists():
        print(f"Public API JSON not found: {api_new_file}", file=sys.stderr)
        return 1

    analyzer = ABIAnalyzer(suppressions=suppressions)
    filter_old = PublicAPIFilter.from_json(api_old_file)
    filter_new = PublicAPIFilter.from_json(api_new_file)

    result = analyzer.compare(baseline_old, baseline_new, filter_old, filter_new)
    print(json.dumps(result.to_dict(), indent=2))

    # Propagate abidiff exit code for CI integration
    # 0=no change, 4=additions, 8=changes, 12=breaking
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
