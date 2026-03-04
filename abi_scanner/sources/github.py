"""GitHub Releases package source adapter.

Supports downloading .deb assets from GitHub releases.

Spec format:  github:<owner>/<repo>
Example:      github:intel/compute-runtime
              github:intel/intel-graphics-compiler

Use --pkg-pattern to filter which .deb asset to download per release.
Example: --pkg-pattern '^libze-intel-gpu1_'
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

from .apt import AptSource
from .base import PackageSource


class GitHubReleasesSource(PackageSource):
    """Adapter for GitHub Releases (.deb assets).

    Downloads .deb files from GitHub release assets.
    Reuses AptSource.extract() since the package format is the same.
    """

    GITHUB_API = "https://api.github.com"
    # Max pages to paginate (100 per page = up to 1000 releases)
    MAX_PAGES = 10

    def __init__(self, token: Optional[str] = None):
        """Initialize with optional GitHub token for higher rate limits.

        Without a token: 60 req/hour. With token: 5000 req/hour.
        Token can also be set via GITHUB_TOKEN env var.
        """
        import os
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self._apt = AptSource()  # delegate extract/find to AptSource

    # ── internal HTTP ──────────────────────────────────────────────────────────

    def _get(self, url: str) -> object:
        """Make authenticated GET to GitHub API; return parsed JSON."""
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def _releases(self, repo: str) -> List[dict]:
        """Fetch all releases for a repo, paginated."""
        releases = []
        for page in range(1, self.MAX_PAGES + 1):
            url = f"{self.GITHUB_API}/repos/{repo}/releases?per_page=100&page={page}"
            batch = self._get(url)
            if not batch:
                break
            releases.extend(batch)
            if len(batch) < 100:
                break
        return releases

    # ── PackageSource interface ────────────────────────────────────────────────

    def list_versions(
        self,
        repo: str,
        asset_pattern: Optional[str] = None,
        include_prereleases: bool = False,
    ) -> List[Tuple[str, str, str]]:
        """List available versions for a GitHub repo.

        Args:
            repo: GitHub repo in owner/repo format (e.g. intel/compute-runtime)
            asset_pattern: Regex to filter .deb asset names. If None, returns
                           any .deb asset found in each release.
            include_prereleases: Include pre-release/draft releases (default False)

        Returns:
            Sorted list of (version_tag, download_url, asset_name) tuples.
            version_tag is the GitHub release tag (e.g. "26.05.37020.3").
        """
        pat = re.compile(asset_pattern) if asset_pattern else None
        releases = self._releases(repo)

        results = []
        for rel in releases:
            if rel.get("draft"):
                continue
            if rel.get("prerelease") and not include_prereleases:
                continue
            tag = rel["tag_name"].lstrip("v")  # normalise: "v2.28.4" → "2.28.4"
            for asset in rel.get("assets", []):
                name = asset["name"]
                if not name.endswith(".deb"):
                    continue
                if pat and not pat.search(name):
                    continue
                url = asset["browser_download_url"]
                results.append((tag, url, name))
                break  # one asset per release (first match)

        # Sort by tag ascending (semver-ish; fall back to string sort)
        def _sort_key(t: Tuple[str, str, str]) -> tuple:
            parts = re.split(r"[.\-]", t[0])
            nums = []
            for p in parts:
                try:
                    nums.append(int(p))
                except ValueError:
                    nums.append(0)
            return tuple(nums)

        return sorted(results, key=_sort_key)

    def resolve_url(self, repo: str, version: str,
                    asset_pattern: Optional[str] = None) -> str:
        """Resolve download URL for a specific release tag.

        Args:
            repo: GitHub repo in owner/repo format
            version: Release tag (with or without leading 'v')
            asset_pattern: Regex to select the .deb asset

        Returns:
            Direct download URL for the .deb asset
        """
        pat = re.compile(asset_pattern) if asset_pattern else None
        # Try tag as-is and with 'v' prefix
        for tag in (version, f"v{version}"):
            url = f"{self.GITHUB_API}/repos/{repo}/releases/tags/{tag}"
            try:
                rel = self._get(url)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                raise
            for asset in rel.get("assets", []):
                name = asset["name"]
                if not name.endswith(".deb"):
                    continue
                if pat and not pat.search(name):
                    continue
                return asset["browser_download_url"]
        raise ValueError(
            f"No matching .deb asset found for {repo}@{version} "
            f"(pattern={asset_pattern!r})"
        )

    def download(self, url_or_name: str, version: str, output_dir: Path) -> Path:
        """Download a .deb from a GitHub asset URL.

        Args:
            url_or_name: Direct https:// URL to the .deb asset
            version: Version string (used only for cache filename if URL not given)
            output_dir: Directory to save the file

        Returns:
            Path to the downloaded .deb file
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        if not url_or_name.startswith("https://"):
            raise ValueError(
                f"GitHubReleasesSource.download() expects a full https:// URL, got: {url_or_name!r}"
            )

        filename = Path(url_or_name).name
        output_file = output_dir / filename

        if output_file.exists() and output_file.stat().st_size > 0:
            print(f"✓ {filename} already downloaded", file=sys.stderr)
            return output_file

        print(f"Downloading {url_or_name}...", file=sys.stderr)
        req = urllib.request.Request(url_or_name)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                output_file.write_bytes(r.read())
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            raise RuntimeError(f"Failed to download {url_or_name}: {e}") from e
        return output_file

    def extract(self, package_file: Path, extract_dir: Path) -> Path:
        """Extract a .deb file (delegates to AptSource)."""
        return self._apt.extract(package_file, extract_dir)

    def find_libraries(self, extract_dir: Path, package_name: str) -> List[Path]:
        return self._apt.find_libraries(extract_dir, package_name)

    def find_headers(self, extract_dir: Path) -> List[Path]:
        return self._apt.find_headers(extract_dir)
