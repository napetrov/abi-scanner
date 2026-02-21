#!/usr/bin/env python3
# abi_tracker/scripts/parse_headers.py
# Parse C++ headers to extract public API namespaces and classes

import os
import sys
import re
import json
from pathlib import Path

def find_headers(extract_dir):
    """Find all C/C++ header files"""
    patterns = ['**/*.h', '**/*.hpp', '**/*.hxx']
    headers = []
    for pattern in patterns:
        headers.extend(Path(extract_dir).glob(pattern))
    
    # Filter to only include/ directories
    return [h for h in headers if '/include/' in str(h)]

def parse_namespace_declarations(header_file):
    """Extract namespace declarations from a header"""
    namespaces = []
    
    with open(header_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Match: namespace foo { or namespace foo::bar {
    pattern = r'^\s*namespace\s+([\w:]+)\s*\{'
    for match in re.finditer(pattern, content, re.MULTILINE):
        ns = match.group(1)
        namespaces.append(ns)
    
    return namespaces

def parse_class_declarations(header_file):
    """Extract class declarations from a header"""
    classes = []
    
    with open(header_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Match: class ClassName or struct ClassName
    pattern = r'^\s*(?:class|struct)\s+(\w+)(?:\s+final)?(?:\s*:\s*public)?'
    for match in re.finditer(pattern, content, re.MULTILINE):
        cls = match.group(1)
        classes.append(cls)
    
    return classes

def is_private_namespace(namespace):
    """Determine if a namespace is private/internal"""
    private_keywords = ['detail', 'internal', 'backend', 'impl', '_internal']
    
    for keyword in private_keywords:
        if f'::{keyword}::' in namespace or namespace.startswith(f'{keyword}::') or namespace.endswith(f'::{keyword}'):
            return True
    
    return False

def analyze_headers(extract_dir, library='onedal'):
    """Analyze all headers and categorize API"""
    
    headers = find_headers(extract_dir)
    
    if not headers:
        print(f"No headers found in {extract_dir}", file=sys.stderr)
        return None
    
    print(f"Found {len(headers)} header files", file=sys.stderr)
    
    all_namespaces = set()
    all_classes = set()
    private_namespaces = set()
    public_namespaces = set()
    
    for header in headers:
        # Skip if header path contains private indicators
        header_str = str(header)
        is_private_header = any(keyword in header_str for keyword in ['/detail/', '/internal/', '/backend/'])
        
        namespaces = parse_namespace_declarations(header)
        classes = parse_class_declarations(header)
        
        for ns in namespaces:
            all_namespaces.add(ns)
            
            if is_private_header or is_private_namespace(ns):
                private_namespaces.add(ns)
            else:
                public_namespaces.add(ns)
        
        all_classes.update(classes)
    
    # Generate result
    result = {
        'library': library,
        'headers_count': len(headers),
        'namespaces': {
            'all': sorted(all_namespaces),
            'public': sorted(public_namespaces),
            'private': sorted(private_namespaces)
        },
        'classes_count': len(all_classes),
        'private_patterns': [
            '.*::detail::.*',
            '.*::backend::.*',
            '.*::internal::.*',
            '.*::impl::.*',
            '^mkl_.*',
            '^_.*',
            '^tbb::detail::.*'
        ]
    }
    
    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: parse_headers.py <extract_dir> [library_name]", file=sys.stderr)
        sys.exit(1)
    
    extract_dir = sys.argv[1]
    library = sys.argv[2] if len(sys.argv) > 2 else 'onedal'
    
    result = analyze_headers(extract_dir, library)
    
    if result:
        print(json.dumps(result, indent=2))
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
