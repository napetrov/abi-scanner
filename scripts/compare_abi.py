#!/usr/bin/env python3
# abi_tracker/scripts/compare_abi.py
# Compare two ABI baselines and categorize changes by public/private API

import sys
import json
import subprocess
import re
from pathlib import Path

def load_public_api(api_file):
    """Load public API definition from JSON"""
    if not Path(api_file).exists():
        return {"public": [], "private": []}
    
    with open(api_file) as f:
        data = json.load(f)
    
    return {
        "public": data.get("namespaces", {}).get("public", []),
        "private": data.get("namespaces", {}).get("private", [])
    }

def is_public_symbol(symbol, public_api):
    """Check if a symbol belongs to public API"""
    # Extract namespace from mangled C++ symbol
    # Simple heuristic: check if symbol contains public namespace
    
    for ns in public_api.get("public", []):
        if ns in symbol:
            return True
    
    # Check against private patterns
    private_patterns = [
        "::detail::", "::backend::", "::internal::", "::impl::",
        "mkl_", "tbb::detail::", "_Z.*internal"
    ]
    
    for pattern in private_patterns:
        if re.search(pattern, symbol):
            return False
    
    return True

def parse_abidiff_output(output, public_api_old, public_api_new):
    """Parse abidiff output and categorize changes"""
    
    result = {
        "summary": {},
        "public": {"added": [], "removed": [], "changed": []},
        "private": {"added": [], "removed": [], "changed": []}
    }
    
    # Parse summary line
    summary_match = re.search(
        r"Functions changes summary: (\d+) Removed, (\d+) Changed, (\d+) Added",
        output
    )
    if summary_match:
        result["summary"]["functions"] = {
            "removed": int(summary_match.group(1)),
            "changed": int(summary_match.group(2)),
            "added": int(summary_match.group(3))
        }
    
    var_summary_match = re.search(
        r"Variables changes summary: (\d+) Removed, (\d+) Changed, (\d+) Added",
        output
    )
    if var_summary_match:
        result["summary"]["variables"] = {
            "removed": int(var_summary_match.group(1)),
            "changed": int(var_summary_match.group(2)),
            "added": int(var_summary_match.group(3))
        }
    
    # Parse removed symbols
    in_removed_section = False
    for line in output.split('\n'):
        if "Removed function symbols" in line or "Removed variable symbols" in line:
            in_removed_section = True
            continue
        
        if "Added function symbols" in line or "Added variable symbols" in line:
            in_removed_section = False
            continue
        
        if in_removed_section and line.strip().startswith('[D]'):
            symbol = line.strip()[4:].strip()
            if is_public_symbol(symbol, public_api_old):
                result["public"]["removed"].append(symbol)
            else:
                result["private"]["removed"].append(symbol)
    
    # Parse added symbols
    in_added_section = False
    for line in output.split('\n'):
        if "Added function symbols" in line or "Added variable symbols" in line:
            in_added_section = True
            continue
        
        if in_added_section and line.strip().startswith('[A]'):
            symbol = line.strip()[4:].strip()
            if is_public_symbol(symbol, public_api_new):
                result["public"]["added"].append(symbol)
            else:
                result["private"]["added"].append(symbol)
    
    return result

def run_abidiff(baseline_old, baseline_new, suppressions=None):
    """Run abidiff and capture output"""
    cmd = ["abidiff"]
    
    if suppressions and Path(suppressions).exists():
        cmd.extend(["--suppressions", suppressions])
    
    cmd.extend([baseline_old, baseline_new])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr
    }

def categorize_exit_code(exit_code):
    """Categorize abidiff exit code"""
    if exit_code == 0:
        return "NO_CHANGE"
    elif exit_code == 4:
        return "COMPATIBLE"  # Additions only
    elif exit_code == 8:
        return "INCOMPATIBLE"  # ABI changes
    elif exit_code == 12:
        return "BREAKING"  # Symbols removed/changed
    else:
        return "UNKNOWN"

def main():
    if len(sys.argv) < 5:
        print("Usage: compare_abi.py <baseline_old> <baseline_new> <public_api_old> <public_api_new> [suppressions]", file=sys.stderr)
        sys.exit(1)
    
    baseline_old = sys.argv[1]
    baseline_new = sys.argv[2]
    api_old_file = sys.argv[3]
    api_new_file = sys.argv[4]
    suppressions = sys.argv[5] if len(sys.argv) > 5 else None
    
    # Load public API definitions
    api_old = load_public_api(api_old_file)
    api_new = load_public_api(api_new_file)
    
    # Run abidiff
    diff_result = run_abidiff(baseline_old, baseline_new, suppressions)
    
    # Parse output
    changes = parse_abidiff_output(diff_result["stdout"], api_old, api_new)
    
    # Build report
    report = {
        "comparison": f"{Path(baseline_old).stem} → {Path(baseline_new).stem}",
        "exit_code": diff_result["exit_code"],
        "verdict": categorize_exit_code(diff_result["exit_code"]),
        "summary": changes["summary"],
        "changes": {
            "public": {
                "added": len(changes["public"]["added"]),
                "removed": len(changes["public"]["removed"]),
                "changed": len(changes["public"]["changed"])
            },
            "private": {
                "added": len(changes["private"]["added"]),
                "removed": len(changes["private"]["removed"]),
                "changed": len(changes["private"]["changed"])
            }
        },
        "details": {
            "public_removed": changes["public"]["removed"][:10],  # First 10
            "public_added": changes["public"]["added"][:10],
            "private_removed": changes["private"]["removed"][:10],
            "private_added": changes["private"]["added"][:10]
        }
    }
    
    # Output JSON
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
