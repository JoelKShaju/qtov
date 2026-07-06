from __future__ import annotations

from app.config import Settings


def test_openai_model_drives_both_agents_when_chains_unset():
    s = Settings(openai_model="gpt-4o", classifier_models="", summarizer_models="")
    assert s.classifier_model_list == ["gpt-4o"]
    assert s.summarizer_model_list == ["gpt-4o"]


def test_classifier_chain_overrides_only_the_classifier():
    s = Settings(
        openai_model="gpt-4o",
        classifier_models="gpt-4o,gpt-4o-mini",  # overrides classifier only
        summarizer_models="",
    )
    assert s.classifier_model_list == ["gpt-4o", "gpt-4o-mini"]
    assert s.summarizer_model_list == ["gpt-4o"]  # still follows openai_model


def test_database_url_coerced_to_asyncpg_scheme():
    # Managed hosts hand out postgres:// or postgresql://; the async engine needs asyncpg.
    assert Settings(database_url="postgres://u:p@h:5432/db").database_url == (
        "postgresql+asyncpg://u:p@h:5432/db"
    )
    assert Settings(database_url="postgresql://u:p@h/db").database_url == (
        "postgresql+asyncpg://u:p@h/db"
    )
    # Already-correct scheme is left alone.
    assert Settings(database_url="postgresql+asyncpg://u:p@h/db").database_url == (
        "postgresql+asyncpg://u:p@h/db"
    )


def test_database_url_strips_sslmode_param_asyncpg_rejects():
    assert Settings(database_url="postgresql://u:p@h/db?sslmode=require").database_url == (
        "postgresql+asyncpg://u:p@h/db"
    )
