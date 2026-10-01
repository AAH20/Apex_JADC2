"""Sovereign AI Enclave — air-gapped deployment, zero external deps, supply chain attestation."""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SovereignError(Exception):
    """Base exception for sovereign enclave operations."""


class AirGapViolation(SovereignError):
    """Raised when air-gap compliance check fails."""


class AttestationError(SovereignError):
    """Raised when supply chain attestation verification fails."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DependencyClass(str, Enum):
    """Classification of a dependency."""

    STDLIB = "stdlib"
    EXTERNAL = "external"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class ImportRecord:
    """A single import found in source code."""

    module: str
    line: int
    is_from_import: bool = False


@dataclass
class Artifact:
    """A deployable artifact."""

    name: str
    path: str
    sha256: str
    size_bytes: int


@dataclass
class ProvenanceRecord:
    """Build provenance information."""

    builder_id: str
    build_timestamp: datetime
    source_url: str = ""
    commit_hash: str = ""
    reproducible: bool = False


@dataclass
class Attestation:
    """A supply chain attestation for an artifact."""

    artifact_name: str
    artifact_sha256: str
    algorithm: str
    provenance: ProvenanceRecord
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AirGapManifest:
    """Manifest describing an air-gapped deployment."""

    name: str
    version: str
    artifacts: list[Artifact] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    network_endpoints: list[str] = field(default_factory=list)


@dataclass
class EnclaveConfig:
    """Configuration for the enclave deployer."""

    enclave_name: str
    version: str
    strict_mode: bool = True
    allow_localhost: bool = False


@dataclass
class DeploymentResult:
    """Result of a deployment attempt."""

    success: bool
    deployed_artifacts: list[Artifact] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Dependency Scanner
# ---------------------------------------------------------------------------


class DependencyScanner:
    """Scans source code for import dependencies."""

    _STDLIB_MODULES = {
        "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
        "asyncore", "atexit", "base64", "bdb", "binascii", "binhex",
        "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb", "chunk",
        "cmath", "cmd", "code", "codecs", "codeop", "collections",
        "colorsys", "compileall", "concurrent", "configparser", "contextlib",
        "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv",
        "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
        "difflib", "dis", "distutils", "doctest", "email", "encodings",
        "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
        "fnmatch", "formatter", "fractions", "ftplib", "functools", "gc",
        "getopt", "getpass", "gettext", "glob", "grp", "gzip", "hashlib",
        "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr",
        "imp", "importlib", "inspect", "io", "ipaddress", "itertools",
        "json", "keyword", "lib2to3", "linecache", "locale", "logging",
        "lzma", "mailbox", "mailcap", "marshal", "math", "mimetypes",
        "mmap", "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
        "numbers", "operator", "optparse", "os", "ossaudiodev", "parser",
        "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
        "platform", "plistlib", "poplib", "posix", "posixpath", "pprint",
        "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
        "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib",
        "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
        "selectors", "shelve", "shlex", "shutil", "signal", "site",
        "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "spwd",
        "sqlite3", "ssl", "stat", "statistics", "string", "stringprep",
        "struct", "subprocess", "sunau", "symtable", "sys", "sysconfig",
        "syslog", "tabnanny", "tarfile", "telnetlib", "tempfile", "termios",
        "test", "textwrap", "threading", "time", "timeit", "tkinter",
        "token", "tokenize", "trace", "traceback", "tracemalloc", "tty",
        "turtle", "turtledemo", "types", "typing", "unicodedata",
        "unittest", "urllib", "uu", "uuid", "venv", "warnings", "wave",
        "weakref", "webbrowser", "winreg", "winsound", "wsgiref",
        "xdrlib", "xml", "xmlrpc", "zipapp", "zipfile", "zipimport",
        "zlib",
    }

    def scan_source(self, source: str) -> list[ImportRecord]:
        """Scan Python source code for imports."""
        records: list[ImportRecord] = []
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return records

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    records.append(ImportRecord(
                        module=alias.name,
                        line=node.lineno,
                        is_from_import=False,
                    ))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    records.append(ImportRecord(
                        module=node.module,
                        line=node.lineno,
                        is_from_import=True,
                    ))
        return records

    def scan_file(self, path: str) -> list[ImportRecord]:
        """Scan a Python file for imports."""
        source = Path(path).read_text(encoding="utf-8")
        return self.scan_source(source)

    def classify(self, module: str) -> str:
        """Classify a module as stdlib, external, or internal."""
        top_level = module.split(".")[0]
        if top_level in self._STDLIB_MODULES:
            return DependencyClass.STDLIB.value
        if top_level == "src" or module.startswith("src."):
            return DependencyClass.INTERNAL.value
        return DependencyClass.EXTERNAL.value


# ---------------------------------------------------------------------------
# Air Gap Verifier
# ---------------------------------------------------------------------------


class AirGapVerifier:
    """Verifies air-gap compliance of a manifest."""

    _URL_PATTERN = re.compile(r"https?://[^\s\"']+")

    def __init__(self, allow_localhost: bool = False):
        self.allow_localhost = allow_localhost

    def verify(self, manifest: AirGapManifest) -> list[str]:
        """Verify air-gap compliance. Returns list of violations."""
        violations: list[str] = []

        for dep in manifest.dependencies:
            if self._is_external(dep):
                violations.append(f"External dependency detected: {dep}")

        for endpoint in manifest.network_endpoints:
            if self._is_external_endpoint(endpoint):
                violations.append(f"External network endpoint detected: {endpoint}")

        return violations

    def is_compliant(self, manifest: AirGapManifest) -> bool:
        """Check if manifest is air-gap compliant."""
        return len(self.verify(manifest)) == 0

    def _is_external(self, dep: str) -> bool:
        """Check if a dependency string is external."""
        if self._URL_PATTERN.search(dep):
            return True
        top_level = dep.split(".")[0].split("==")[0].split(">=")[0].split("<=")[0].strip()
        if top_level in DependencyScanner._STDLIB_MODULES:
            return False
        if top_level == "src" or dep.startswith("src."):
            return False
        return True

    def _is_external_endpoint(self, endpoint: str) -> bool:
        """Check if a network endpoint is external."""
        if self.allow_localhost and "localhost" in endpoint:
            return False
        if "127.0.0.1" in endpoint and self.allow_localhost:
            return False
        return bool(self._URL_PATTERN.search(endpoint))


# ---------------------------------------------------------------------------
# Supply Chain Attestor
# ---------------------------------------------------------------------------


class SupplyChainAttestor:
    """Creates and verifies supply chain attestations."""

    def attest(self, artifact: Artifact, provenance: ProvenanceRecord) -> Attestation:
        """Create an attestation for an artifact."""
        return Attestation(
            artifact_name=artifact.name,
            artifact_sha256=artifact.sha256,
            algorithm="sha256",
            provenance=provenance,
        )

    def verify(self, attestation: Attestation, artifact: Artifact) -> bool:
        """Verify an attestation against an artifact."""
        if attestation.artifact_name != artifact.name:
            return False
        if attestation.artifact_sha256 != artifact.sha256:
            return False
        return True

    def compute_hash(self, data: bytes) -> str:
        """Compute SHA-256 hash of data."""
        return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Enclave Deployer
# ---------------------------------------------------------------------------


class EnclaveDeployer:
    """Orchestrates air-gapped enclave deployment."""

    def __init__(self, config: EnclaveConfig):
        self.config = config
        self.air_gap_verifier = AirGapVerifier(allow_localhost=config.allow_localhost)
        self.attestor = SupplyChainAttestor()

    def deploy(
        self,
        manifest: AirGapManifest,
        attestations: list[Attestation],
    ) -> DeploymentResult:
        """Deploy artifacts to the enclave."""
        violations: list[str] = []

        # Check air-gap compliance
        ag_violations = self.air_gap_verifier.verify(manifest)
        violations.extend(ag_violations)

        # Verify attestations
        attestation_map = {a.artifact_name: a for a in attestations}
        for artifact in manifest.artifacts:
            if artifact.name not in attestation_map:
                violations.append(f"Missing attestation for artifact: {artifact.name}")
                continue
            attestation = attestation_map[artifact.name]
            if not self.attestor.verify(attestation, artifact):
                violations.append(f"Attestation verification failed for artifact: {artifact.name}")

        if violations and self.config.strict_mode:
            return DeploymentResult(
                success=False,
                violations=violations,
            )

        return DeploymentResult(
            success=True,
            deployed_artifacts=list(manifest.artifacts),
        )
