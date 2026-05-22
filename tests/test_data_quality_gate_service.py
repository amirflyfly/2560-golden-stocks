from backend.application.data_quality_gate_service import DataQualityGateService


def test_quality_gate_preserves_paper_trade_reason_contract():
    service = DataQualityGateService()

    assert (
        service.paper_trade_block_reason(
            {"data_quality": "mock", "market_data_source": "mock"},
            {"enforce_market_data_quality_gate": True},
        )
        == "mock_market_data"
    )
    assert (
        service.paper_trade_block_reason(
            {"data_quality": "fallback", "fallback_used": True},
            {"enforce_market_data_quality_gate": True},
        )
        == "degraded_market_data"
    )
    assert (
        service.paper_trade_block_reason(
            {"data_quality": "fallback", "fallback_used": True},
            {"enforce_market_data_quality_gate": True, "allow_degraded_market_data": True},
        )
        == ""
    )
    assert service.paper_trade_block_reason({"data_quality": "mock"}, {}) == ""


def test_quality_gate_disclosure_warns_without_blocking_when_not_enforced():
    service = DataQualityGateService()

    decision = service.decision(
        "scan_result",
        {"data_quality": "fallback", "market_data_source": "akshare", "fallback_used": True},
        enforce=False,
        allow_degraded=True,
    )

    assert decision["status"] == "warning"
    assert decision["blocked"] is False
    assert decision["quality_reason"] == "degraded_market_data"
    assert decision["reason"] == ""
    assert decision["data_quality"] == "fallback"
    assert "next_action" in decision
    assert "人工复核" in decision["next_action"]


def test_quality_gate_next_action_blocks_mock_in_enforced_flow():
    service = DataQualityGateService()

    decision = service.decision(
        "scan",
        {"data_quality": "mock", "market_data_source": "mock"},
        enforce=True,
    )

    assert decision["status"] == "blocked"
    assert decision["blocked"] is True
    assert decision["reason"] == "mock_market_data"
    assert "next_action" in decision
    assert "禁止" in decision["next_action"]
