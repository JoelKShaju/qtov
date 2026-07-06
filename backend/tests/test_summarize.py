from __future__ import annotations

from app.agent.summarize import _payload, sanitize_citations
from app.schemas.query import ChartType
from app.schemas.visualization import (
    AxisEncoding,
    ChartConfig,
    Citation,
    Encoding,
    TrialRef,
    Visualization,
    VizMetadata,
)


def _viz(data, chart=ChartType.BAR, data_caveat=None):
    return Visualization(
        type=chart,
        title="t",
        data=data,
        encoding=Encoding(x=AxisEncoding(field="x", type="ordinal")),
        metadata=VizMetadata(
            total_records=10,
            filters_applied="none",
            timestamp="t",
            chart_config=ChartConfig(),
            data_caveat=data_caveat,
        ),
    )


def test_sanitize_strips_unknown_nct_ids():
    allowed = {"NCT00000001"}
    text = "Real (NCT00000001) and fake (NCT01234567, NCT07654321) examples."
    out = sanitize_citations(text, allowed)
    assert "NCT00000001" in out
    assert "NCT01234567" not in out and "NCT07654321" not in out
    assert "()" not in out  # leftover empty parens cleaned


def test_sanitize_keeps_partial_group():
    allowed = {"NCT00000002"}
    out = sanitize_citations("Foo (NCT01234567, NCT00000002).", allowed)
    assert "(NCT00000002)" in out
    assert "NCT01234567" not in out


def test_payload_includes_network_nct_ids():
    network = {"nodes": [{"name": "Acme", "value": 2, "nct_ids": ["NCT1", "NCT2"]}], "links": []}
    payload, allowed = _payload(_viz(network, ChartType.NETWORK), [])
    assert payload["points"][0]["nct_ids"] == ["NCT1", "NCT2"]
    assert allowed == {"NCT1", "NCT2"}


def test_payload_chart_allows_bucket_ids():
    citations = [Citation(bucket="2019", value=2, nct_ids=["NCT9"], trials=[
        TrialRef(nct_id="NCT9", title="t", url="u")
    ])]
    _, allowed = _payload(_viz([{"x": "2019", "y": 2}]), citations)
    assert allowed == {"NCT9"}


def test_payload_carries_incomplete_status_and_caveat():
    data = [
        {"x": "2024", "y": 50},
        {"x": "2026", "y": 30, "partial": True},
        {"x": "2027", "y": 2, "projected": True},
    ]
    citations = [
        Citation(bucket="2024", value=50, nct_ids=["NCT1"], trials=[]),
        Citation(bucket="2026", value=30, nct_ids=["NCT2"], trials=[]),
        Citation(bucket="2027", value=2, nct_ids=["NCT3"], trials=[]),
    ]
    payload, _ = _payload(
        _viz(data, ChartType.LINE, data_caveat="2026 is still in progress; 2027 is anticipated."),
        citations,
    )
    by_bucket = {p["bucket"]: p for p in payload["points"]}
    assert "status" not in by_bucket["2024"]
    assert by_bucket["2026"]["status"] == "partial"
    assert by_bucket["2027"]["status"] == "projected"
    assert "in progress" in payload["caveat"]
