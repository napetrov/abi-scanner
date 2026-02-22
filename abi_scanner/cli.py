"""CLI interface for abi-scanner."""

import sys
import argparse
from pathlib import Path

from .package_spec import PackageSpec


def create_parser():
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="abi-scanner",
        description="ABI Scanner — Universal ABI compatibility checker for C/C++ libraries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare two conda-forge versions
  abi-scanner compare conda-forge:dal=2025.9.0 conda-forge:dal=2025.10.0
  
  # Cross-channel comparison
  abi-scanner compare conda-forge:dal=2025.9.0 intel:dal=2025.9.0
  
  # Compare with local build
  abi-scanner compare conda-forge:dal=2025.9.0 local:./libonedal.so
  
  # JSON output for CI
  abi-scanner compare --format json conda-forge:dal=2025.9.0 conda-forge:dal=2025.10.0

Exit codes:
  0 = No ABI changes (compatible)
  4 = Additions only (forward-compatible)
  8 = Changes but no removals (possibly compatible)
  12 = Breaking changes (removals)
"""
    )
    
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0-dev")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # compare command
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare ABI between two package versions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Compare ABI between two package versions",
        epilog="""
Examples:
  abi-scanner compare conda-forge:dal=2025.9.0 conda-forge:dal=2025.10.0
  abi-scanner compare --format json conda-forge:dal=2025.9.0 intel:dal=2025.9.0
"""
    )
    compare_parser.add_argument("old", help="Old package spec (channel:package=version)")
    compare_parser.add_argument("new", help="New package spec (channel:package=version)")
    compare_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    compare_parser.add_argument(
        "--output",
        type=Path,
        help="Write output to file instead of stdout"
    )
    compare_parser.add_argument(
        "--fail-on",
        choices=["breaking", "any", "none"],
        default="none",
        help="Exit with error on specified change level (default: none)"
    )
    compare_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    # compatible command
    compatible_parser = subparsers.add_parser(
        "compatible",
        help="Find compatible versions for a package",
        description="Find compatible versions for a package"
    )
    compatible_parser.add_argument("spec", help="Package spec (channel:package=version)")
    compatible_parser.add_argument(
        "--newer",
        action="store_true",
        help="Show only newer compatible versions"
    )
    compatible_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format"
    )
    
    # validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate SemVer compliance for package versions",
        description="Validate SemVer compliance for package versions"
    )
    validate_parser.add_argument("spec", help="Package spec (channel:package)")
    validate_parser.add_argument(
        "--versions",
        help="Version range (e.g., 2025.0.0:2025.10.0)"
    )
    validate_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format"
    )
    
    # list command
    list_parser = subparsers.add_parser(
        "list",
        help="List available versions for a package",
        description="List available versions for a package"
    )
    list_parser.add_argument("spec", help="Package spec (channel:package)")
    list_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format"
    )
    
    return parser


def cmd_compare(args):
    """Execute compare command."""
    try:
        # Parse specs
        old_spec = PackageSpec.parse(args.old)
        new_spec = PackageSpec.parse(args.new)
        
        if args.verbose:
            print(f"Old: {old_spec}", file=sys.stderr)
            print(f"New: {new_spec}", file=sys.stderr)
        
        # TODO: Implement actual comparison logic
        output = (
            f"Comparing {old_spec} → {new_spec}\n"
            f"Status: ✅ COMPATIBLE (exit code: 0)\n"
            f"(Implementation in progress)\n"
        )
        
        # Handle output destination
        if args.output:
            args.output.write_text(output)
            if args.verbose:
                print(f"Output written to {args.output}", file=sys.stderr)
        else:
            print(output, end='')
        
        # TODO: Return proper exit codes after comparison logic implemented
        # Exit codes: 0=no change, 4=additions, 8=changes, 12=breaking
        return 0
        
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        if args.verbose:
            raise
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


def cmd_compatible(args):
    """Execute compatible command."""
    try:
        pkg_spec = PackageSpec.parse(args.spec)
        print(f"Finding compatible versions for {pkg_spec}")
        print("(Implementation in progress)")
        return 0
        
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_validate(args):
    """Execute validate command."""
    try:
        # Parse spec (may be package-only, no version)
        # TODO: Implement spec parser for channel:package format
        print(f"Validating SemVer compliance for {args.spec}")
        print("(Implementation in progress)")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_list(args):
    """Execute list command."""
    try:
        # Parse spec (package-only format)
        # TODO: Implement spec parser for channel:package format
        print(f"Listing versions for {args.spec}")
        print("(Implementation in progress)")
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main():
    """Entry point for CLI."""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Dispatch to command handler
    handlers = {
        "compare": cmd_compare,
        "compatible": cmd_compatible,
        "validate": cmd_validate,
        "list": cmd_list,
    }
    
    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
