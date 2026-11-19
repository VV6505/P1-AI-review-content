import pytest

from worker.settings import CostLimitExceededError, MissingConfigError, Settings


def test_from_env_reads_and_strips() -> None:
    s = Settings.from_env(
        {
            "SUPABASE_URL": " http://x:54321/ ",
            "GEMINI_API_KEY": " k ",
            "JOB_COST_LIMIT_USD": "0.5",
        }
    )
    assert s.supabase_url == "http://x:54321"
    assert s.gemini_api_key.get_secret_value() == "k"
    assert s.job_cost_limit_usd == 0.5


def test_secrets_never_in_repr() -> None:
    s = Settings.from_env({
        "GEMINI_API_KEY": "super-secret",
        "FREEMODEL_API_KEY": "fm-secret",
        "N8N_SERVICE_TOKEN": "tok-123",
    })
    text = repr(s) + str(s.model_dump())
    assert "super-secret" not in text
    assert "fm-secret" not in text
    assert "tok-123" not in text


def test_missing_lists_names_in_order_without_duplicates() -> None:
    s = Settings.from_env({"SUPABASE_URL": "http://x"})
    assert s.missing("api", "extract", "script") == [
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "GEMINI_API_KEY",
    ]


def test_require_raises_with_names_only() -> None:
    s = Settings.from_env({"CLOUDFLARE_ACCOUNT_ID": "acc"})
    with pytest.raises(MissingConfigError) as e:
        s.require("ai_scene")
    assert e.value.names == ("CLOUDFLARE_API_TOKEN",)
    assert "acc" not in str(e.value)


def test_require_ok_when_all_present() -> None:
    Settings.from_env({"GEMINI_API_KEY": "k"}).require("extract")


def test_unknown_step_is_error() -> None:
    with pytest.raises(KeyError):
        Settings().missing("nope")


def test_cost_limit() -> None:
    Settings().check_cost(999)  # không đặt ngưỡng = không chặn
    s = Settings(job_cost_limit_usd=0.1)
    s.check_cost(0.1)
    with pytest.raises(CostLimitExceededError):
        s.check_cost(0.11)


def test_runner_settings_defaults_and_override() -> None:
    d = Settings.from_env({})
    assert (d.page_store_dir, d.runner_max_attempts, d.runner_poll_interval_s) == (
        "./data/pages",
        3,
        5.0,
    )
    s = Settings.from_env({"WORKER_PAGE_STORE_DIR": "D:/tmp/p", "RUNNER_MAX_ATTEMPTS": "5"})
    assert s.page_store_dir == "D:/tmp/p" and s.runner_max_attempts == 5
    assert Settings.from_env({"SUPABASE_URL": "http://x"}).missing("runner") == [
        "SUPABASE_SERVICE_ROLE_KEY"
    ]
