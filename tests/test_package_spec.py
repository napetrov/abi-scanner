"""Unit tests for package_spec module."""

import tempfile
import unittest
from pathlib import Path
from abi_scanner.package_spec import PackageSpec, validate_spec


class TestPackageSpec(unittest.TestCase):
    """Test PackageSpec parser."""
    
    def test_standard_format(self):
        """Test standard channel:package=version format."""
        spec = PackageSpec.parse("conda-forge:dal=2025.9.0")
        self.assertEqual(spec.channel, "conda-forge")
        self.assertEqual(spec.package, "dal")
        self.assertEqual(spec.version, "2025.9.0")
        self.assertIsNone(spec.path)
    
    def test_intel_channel(self):
        """Test Intel channel."""
        spec = PackageSpec.parse("intel:mkl=2025.1.0")
        self.assertEqual(spec.channel, "intel")
        self.assertEqual(spec.package, "mkl")
        self.assertEqual(spec.version, "2025.1.0")
    
    def test_apt_channel(self):
        """Test APT channel."""
        spec = PackageSpec.parse("apt:intel-oneapi-dal=2025.9.0")
        self.assertEqual(spec.channel, "apt")
        self.assertEqual(spec.package, "intel-oneapi-dal")
        self.assertEqual(spec.version, "2025.9.0")
    
    def test_string_representation(self):
        """Test __str__ method."""
        spec = PackageSpec.parse("conda-forge:dal=2025.9.0")
        self.assertEqual(str(spec), "conda-forge:dal=2025.9.0")
    
    def test_missing_colon(self):
        """Test error on missing colon."""
        with self.assertRaises(ValueError) as cm:
            PackageSpec.parse("invalid-spec")
        self.assertIn("Invalid package spec", str(cm.exception))
    
    def test_missing_version(self):
        """Test error on missing version."""
        with self.assertRaises(ValueError) as cm:
            PackageSpec.parse("conda-forge:dal")
        self.assertIn("Invalid package spec", str(cm.exception))
    
    def test_empty_package(self):
        """Test error on empty package name."""
        with self.assertRaises(ValueError) as cm:
            PackageSpec.parse("conda-forge:=2025.9.0")
        self.assertIn("Empty package name", str(cm.exception))
    
    def test_empty_version(self):
        """Test error on empty version."""
        with self.assertRaises(ValueError) as cm:
            PackageSpec.parse("conda-forge:dal=")
        self.assertIn("Empty version", str(cm.exception))
    
    def test_whitespace_handling(self):
        """Test that whitespace is stripped."""
        spec = PackageSpec.parse("  conda-forge : dal = 2025.9.0  ")
        self.assertEqual(spec.channel, "conda-forge")
        self.assertEqual(spec.package, "dal")
        self.assertEqual(spec.version, "2025.9.0")
    
    def test_validate_spec_valid(self):
        """Test validate_spec with valid input."""
        self.assertTrue(validate_spec("conda-forge:dal=2025.9.0"))
    
    def test_validate_spec_invalid(self):
        """Test validate_spec with invalid input."""
        self.assertFalse(validate_spec("invalid"))
        self.assertFalse(validate_spec("conda-forge:dal"))

    def test_local_path(self):
        """Test local:/path parsing."""
        with tempfile.NamedTemporaryFile(suffix=".so") as tmp:
            spec = PackageSpec.parse(f"local:{tmp.name}")
            self.assertEqual(spec.channel, "local")
            self.assertEqual(spec.path, Path(tmp.name).resolve())
            self.assertEqual(spec.package, Path(tmp.name).stem)
            self.assertIsNone(spec.version)
            self.assertEqual(str(spec), f"local:{Path(tmp.name).resolve()}")

    def test_local_path_missing(self):
        """Test local path validation when file does not exist."""
        self.assertFalse(validate_spec("local:/definitely/not/found/lib.so"))

    def test_local_path_directory(self):
        """Test local path must be a file, not a directory."""
        with self.assertRaises(ValueError) as cm:
            PackageSpec.parse("local:.")
        self.assertIn("not a file", str(cm.exception))

    def test_unsupported_channel(self):
        """Test unsupported channel is rejected."""
        with self.assertRaises(ValueError) as cm:
            PackageSpec.parse("foo:dal=2025.9.0")
        self.assertIn("Unsupported channel", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
