#!/usr/bin/env python3
import os, subprocess, glob

BASELINES = "/workspace/abi_tracker_workspace/baselines/dal"
REPORTS = "/workspace/abi_tracker_workspace/reports/dal"
SUPPRESSIONS = "/workspace/abi_tracker/suppressions/onedal.txt"

os.makedirs(REPORTS, exist_ok=True)

# Get sorted versions
abi_files = sorted(glob.glob(f"{BASELINES}/dal_*.abi"))
versions = [os.path.basename(f).replace("dal_", "").replace(".abi", "") for f in abi_files]

# Sort by version
from packaging.version import Version
try:
    versions = sorted(versions, key=lambda v: Version(v))
except:
    versions = sorted(versions)

print(f"Total versions: {len(versions)}")
print(f"Total comparisons: {len(versions)-1}")
print()

results = []

for i in range(len(versions) - 1):
    old = versions[i]
    new = versions[i+1]
    report = f"{REPORTS}/{old}_to_{new}.txt"

    if os.path.exists(report):
        # Read existing
        with open(report) as f:
            content = f.read()
        # Parse exit code from content (re-run to get)
        result = subprocess.run(
            ["abidiff", "--suppressions", SUPPRESSIONS,
             f"{BASELINES}/dal_{old}.abi", f"{BASELINES}/dal_{new}.abi"],
            capture_output=True, text=True
        )
        exit_code = result.returncode
    else:
        result = subprocess.run(
            ["abidiff", "--suppressions", SUPPRESSIONS,
             f"{BASELINES}/dal_{old}.abi", f"{BASELINES}/dal_{new}.abi"],
            capture_output=True, text=True
        )
        exit_code = result.returncode
        with open(report, "w") as f:
            f.write(result.stdout)

    # Parse summary
    removed = added = 0
    for line in result.stdout.splitlines():
        if "Function symbols changes summary:" in line:
            parts = line.split()
            try:
                removed = int(parts[5])
                added = int(parts[-4])
            except: pass

    status = {0: "✅ NO_CHANGE", 4: "✅ COMPATIBLE", 8: "⚠️  INCOMPAT", 12: "❌ BREAKING"}.get(exit_code, f"?({exit_code})")
    line = f"{status} | {old} → {new} | removed={removed} added={added}"
    print(line)
    results.append({"old": old, "new": new, "exit_code": exit_code, "removed": removed, "added": added})

# Summary
print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
breaking = [r for r in results if r["exit_code"] == 12]
compat = [r for r in results if r["exit_code"] == 4]
no_change = [r for r in results if r["exit_code"] == 0]

print(f"✅ NO_CHANGE:  {len(no_change)}")
print(f"✅ COMPATIBLE: {len(compat)}")
print(f"❌ BREAKING:   {len(breaking)}")
if breaking:
    print("\nBreaking changes:")
    for r in breaking:
        print(f"  {r['old']} → {r['new']} (removed={r['removed']})")
