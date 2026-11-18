from evals.capri_comprehensive.runners.live_components import rel08


def test_rel08_accepts_snapshot_restore_with_secure_forgetting(tmp_path):
    result = rel08(tmp_path)

    assert result.passed
    assert len(result.evidence) == 2
    assert all(item.passed for item in result.evidence)
    assert "retained records" in result.evidence[0].name
    assert "forgotten bytes" in result.evidence[1].name
