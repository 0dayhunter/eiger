from halcyon import m4_answers, scan_artifact


def test_poisoned_artifact_hash_matches_answer():
    r = scan_artifact.scan("labs/m4/artifacts/community_model.pkl")
    assert r["malicious"] is True
    assert r["sha256"] == m4_answers.POISONED_ARTIFACT_SHA256


def test_normalizers():
    assert m4_answers.normalize_package("PyYAML==5.3.1") == "pyyaml==5.3.1"
    assert m4_answers.normalize_hash("SHA256:ABCD") == "abcd"


def test_stretch_requires_version_pin():
    from halcyon import m4_answers

    assert m4_answers.normalize_package("pyyaml") != m4_answers.VULNERABLE_PACKAGE       # bare fails
    assert m4_answers.normalize_package("PyYAML==5.3.1") == m4_answers.VULNERABLE_PACKAGE  # pin passes
