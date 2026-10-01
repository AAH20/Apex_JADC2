"""Tests for sovereign AI enclave — air-gapped deployment, zero external deps, supply chain."""

import hashlib
from datetime import datetime, timezone

import pytest

from src.federation.sovereign import (
    AirGapManifest,
    AirGapVerifier,
    Artifact,
    Attestation,
    DependencyScanner,
    DeploymentResult,
    EnclaveConfig,
    EnclaveDeployer,
    ImportRecord,
    ProvenanceRecord,
    SupplyChainAttestor,
)


class TestDependencyScanner:
    """Tests for DependencyScanner."""

    def test_scan_source_finds_stdlib_imports(self):
        source = "import os\nimport sys\nimport hashlib\n"
        scanner = DependencyScanner()
        records = scanner.scan_source(source)
        modules = {r.module for r in records}
        assert "os" in modules
        assert "sys" in modules
        assert "hashlib" in modules

    def test_scan_source_finds_from_imports(self):
        source = "from os.path import join\nfrom collections import OrderedDict\n"
        scanner = DependencyScanner()
        records = scanner.scan_source(source)
        modules = {r.module for r in records}
        assert "os.path" in modules
        assert "collections" in modules

    def test_scan_source_finds_external_imports(self):
        source = "import requests\nimport numpy as np\n"
        scanner = DependencyScanner()
        records = scanner.scan_source(source)
        modules = {r.module for r in records}
        assert "requests" in modules
        assert "numpy" in modules

    def test_scan_source_finds_internal_imports(self):
        source = "from src.c2.f2t2ea import F2T2EAChain\nimport src.federation.sovereign\n"
        scanner = DependencyScanner()
        records = scanner.scan_source(source)
        modules = {r.module for r in records}
        assert "src.c2.f2t2ea" in modules
        assert "src.federation.sovereign" in modules

    def test_scan_source_empty_code(self):
        scanner = DependencyScanner()
        records = scanner.scan_source("")
        assert records == []

    def test_scan_source_no_imports(self):
        source = "x = 1\ny = 2\nprint(x + y)\n"
        scanner = DependencyScanner()
        records = scanner.scan_source(source)
        assert records == []

    def test_classify_stdlib_module(self):
        scanner = DependencyScanner()
        assert scanner.classify("os") == "stdlib"
        assert scanner.classify("sys") == "stdlib"
        assert scanner.classify("hashlib") == "stdlib"

    def test_classify_external_module(self):
        scanner = DependencyScanner()
        assert scanner.classify("requests") == "external"
        assert scanner.classify("numpy") == "external"

    def test_classify_internal_module(self):
        scanner = DependencyScanner()
        assert scanner.classify("src.c2.f2t2ea") == "internal"
        assert scanner.classify("src.federation.sovereign") == "internal"

    def test_scan_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("import os\nimport requests\n")
        scanner = DependencyScanner()
        records = scanner.scan_file(str(f))
        modules = {r.module for r in records}
        assert "os" in modules
        assert "requests" in modules


class TestAirGapVerifier:
    """Tests for AirGapVerifier."""

    def _make_manifest(self, **kwargs):
        defaults = {
            "name": "test-enclave",
            "version": "1.0.0",
            "artifacts": [],
            "dependencies": [],
            "network_endpoints": [],
        }
        defaults.update(kwargs)
        return AirGapManifest(**defaults)

    def test_clean_manifest_passes(self):
        manifest = self._make_manifest()
        verifier = AirGapVerifier()
        assert verifier.is_compliant(manifest) is True
        assert verifier.verify(manifest) == []

    def test_external_url_in_dependencies_detected(self):
        manifest = self._make_manifest(dependencies=["https://example.com/package"])
        verifier = AirGapVerifier()
        assert verifier.is_compliant(manifest) is False
        violations = verifier.verify(manifest)
        assert len(violations) > 0
        assert any("https://example.com" in v for v in violations)

    def test_external_package_in_dependencies_detected(self):
        manifest = self._make_manifest(dependencies=["requests", "numpy"])
        verifier = AirGapVerifier()
        assert verifier.is_compliant(manifest) is False

    def test_network_endpoint_detected(self):
        manifest = self._make_manifest(network_endpoints=["https://api.example.com"])
        verifier = AirGapVerifier()
        assert verifier.is_compliant(manifest) is False

    def test_multiple_violations_reported(self):
        manifest = self._make_manifest(
            dependencies=["requests"],
            network_endpoints=["https://evil.com"],
        )
        verifier = AirGapVerifier()
        violations = verifier.verify(manifest)
        assert len(violations) >= 2

    def test_localhost_allowed_when_configured(self):
        manifest = self._make_manifest(network_endpoints=["http://localhost:8080"])
        verifier = AirGapVerifier(allow_localhost=True)
        assert verifier.is_compliant(manifest) is True

    def test_localhost_rejected_by_default(self):
        manifest = self._make_manifest(network_endpoints=["http://localhost:8080"])
        verifier = AirGapVerifier()
        assert verifier.is_compliant(manifest) is False


class TestSupplyChainAttestor:
    """Tests for SupplyChainAttestor."""

    def _make_artifact(self, data: bytes = b"test data") -> Artifact:
        return Artifact(
            name="test-artifact",
            path="/tmp/test",
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )

    def _make_provenance(self) -> ProvenanceRecord:
        return ProvenanceRecord(
            builder_id="ci-builder-1",
            build_timestamp=datetime.now(timezone.utc),
            source_url="https://github.com/example/repo",
            commit_hash="abc123",
            reproducible=True,
        )

    def test_attest_creates_valid_attestation(self):
        attestor = SupplyChainAttestor()
        artifact = self._make_artifact()
        provenance = self._make_provenance()
        attestation = attestor.attest(artifact, provenance)
        assert attestation.artifact_name == "test-artifact"
        assert attestation.algorithm == "sha256"
        assert attestation.provenance == provenance

    def test_verify_valid_attestation(self):
        attestor = SupplyChainAttestor()
        artifact = self._make_artifact()
        provenance = self._make_provenance()
        attestation = attestor.attest(artifact, provenance)
        assert attestor.verify(attestation, artifact) is True

    def test_verify_tampered_artifact_fails(self):
        attestor = SupplyChainAttestor()
        artifact = self._make_artifact(b"original")
        provenance = self._make_provenance()
        attestation = attestor.attest(artifact, provenance)
        tampered = Artifact(
            name="test-artifact",
            path="/tmp/test",
            sha256=hashlib.sha256(b"tampered").hexdigest(),
            size_bytes=8,
        )
        assert attestor.verify(attestation, tampered) is False

    def test_verify_wrong_hash_fails(self):
        attestor = SupplyChainAttestor()
        artifact = self._make_artifact()
        provenance = self._make_provenance()
        attestation = attestor.attest(artifact, provenance)
        wrong = Artifact(
            name="test-artifact",
            path="/tmp/test",
            sha256="0" * 64,
            size_bytes=9,
        )
        assert attestor.verify(attestation, wrong) is False

    def test_compute_hash_deterministic(self):
        attestor = SupplyChainAttestor()
        data = b"deterministic data"
        h1 = attestor.compute_hash(data)
        h2 = attestor.compute_hash(data)
        assert h1 == h2
        assert len(h1) == 64

    def test_compute_hash_different_data(self):
        attestor = SupplyChainAttestor()
        h1 = attestor.compute_hash(b"data1")
        h2 = attestor.compute_hash(b"data2")
        assert h1 != h2


class TestEnclaveDeployer:
    """Tests for EnclaveDeployer."""

    def _make_config(self, **kwargs):
        defaults = {
            "enclave_name": "test-enclave",
            "version": "1.0.0",
            "strict_mode": True,
        }
        defaults.update(kwargs)
        return EnclaveConfig(**defaults)

    def _make_artifact(self, name: str, data: bytes = b"artifact data") -> Artifact:
        return Artifact(
            name=name,
            path=f"/tmp/{name}",
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )

    def _make_provenance(self) -> ProvenanceRecord:
        return ProvenanceRecord(
            builder_id="ci-builder-1",
            build_timestamp=datetime.now(timezone.utc),
            reproducible=True,
        )

    def test_successful_deployment(self):
        config = self._make_config()
        deployer = EnclaveDeployer(config)
        artifact = self._make_artifact("clean-artifact")
        manifest = AirGapManifest(
            name="test-enclave",
            version="1.0.0",
            artifacts=[artifact],
            dependencies=[],
            network_endpoints=[],
        )
        attestor = SupplyChainAttestor()
        provenance = self._make_provenance()
        attestation = attestor.attest(artifact, provenance)
        result = deployer.deploy(manifest, [attestation])
        assert result.success is True
        assert len(result.deployed_artifacts) == 1

    def test_rejects_external_dependency(self):
        config = self._make_config()
        deployer = EnclaveDeployer(config)
        artifact = self._make_artifact("clean-artifact")
        manifest = AirGapManifest(
            name="test-enclave",
            version="1.0.0",
            artifacts=[artifact],
            dependencies=["requests"],
            network_endpoints=[],
        )
        attestor = SupplyChainAttestor()
        provenance = self._make_provenance()
        attestation = attestor.attest(artifact, provenance)
        result = deployer.deploy(manifest, [attestation])
        assert result.success is False
        assert len(result.violations) > 0

    def test_rejects_invalid_attestation(self):
        config = self._make_config()
        deployer = EnclaveDeployer(config)
        artifact = self._make_artifact("clean-artifact")
        manifest = AirGapManifest(
            name="test-enclave",
            version="1.0.0",
            artifacts=[artifact],
            dependencies=[],
            network_endpoints=[],
        )
        wrong_artifact = self._make_artifact("clean-artifact", b"different data")
        attestor = SupplyChainAttestor()
        provenance = self._make_provenance()
        attestation = attestor.attest(wrong_artifact, provenance)
        result = deployer.deploy(manifest, [attestation])
        assert result.success is False

    def test_rejects_tampered_artifact(self):
        config = self._make_config()
        deployer = EnclaveDeployer(config)
        artifact = self._make_artifact("clean-artifact", b"original")
        manifest = AirGapManifest(
            name="test-enclave",
            version="1.0.0",
            artifacts=[artifact],
            dependencies=[],
            network_endpoints=[],
        )
        attestor = SupplyChainAttestor()
        provenance = self._make_provenance()
        attestation = attestor.attest(artifact, provenance)
        tampered = Artifact(
            name="clean-artifact",
            path="/tmp/clean-artifact",
            sha256=hashlib.sha256(b"tampered").hexdigest(),
            size_bytes=8,
        )
        manifest.artifacts = [tampered]
        result = deployer.deploy(manifest, [attestation])
        assert result.success is False

    def test_deployment_result_contains_timestamp(self):
        config = self._make_config()
        deployer = EnclaveDeployer(config)
        artifact = self._make_artifact("clean-artifact")
        manifest = AirGapManifest(
            name="test-enclave",
            version="1.0.0",
            artifacts=[artifact],
            dependencies=[],
            network_endpoints=[],
        )
        attestor = SupplyChainAttestor()
        provenance = self._make_provenance()
        attestation = attestor.attest(artifact, provenance)
        result = deployer.deploy(manifest, [attestation])
        assert result.timestamp is not None
