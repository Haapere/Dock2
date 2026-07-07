import pandas as pd
import pytest

from strategylab import paper
from strategylab.data import generate_synthetic


@pytest.fixture
def df():
    return generate_synthetic(days=600, seed=9)


def test_init_and_status(tmp_path):
    account_path = tmp_path / "paper.json"
    account = paper.init_account(
        account_path, "sma_cross", {"fast": 10, "slow": 50}, start_date="2022-01-01"
    )
    assert account_path.exists()
    text = paper.status_text(account)
    assert "sma_cross" in text
    assert "2022-01-01" in text


def test_init_validates_strategy(tmp_path):
    with pytest.raises(KeyError):
        paper.init_account(tmp_path / "x.json", "unknown_strategy", {})
    with pytest.raises(ValueError):
        paper.init_account(tmp_path / "x.json", "sma_cross", {"bogus": 1})


def test_update_only_counts_forward_period(tmp_path, df):
    account_path = tmp_path / "paper.json"
    start = df.index[400].date().isoformat()
    paper.init_account(account_path, "buy_hold", {}, start_date=start, initial_capital=10_000)

    account = paper.update_account(account_path, df)
    assert len(account.history) == 200
    assert account.history[0]["date"] == start

    # Buy & Hold ohne Umschichtung nach Einstieg: Equity folgt dem Kurs ab Start
    first_equity = account.history[0]["equity"]
    last_equity = account.history[-1]["equity"]
    price_ratio = df["Close"].iloc[-1] / df["Close"].iloc[400]
    assert last_equity / first_equity == pytest.approx(price_ratio, rel=1e-6)


def test_update_is_reproducible(tmp_path, df):
    account_path = tmp_path / "paper.json"
    start = df.index[500].date().isoformat()
    paper.init_account(account_path, "sma_cross", {"fast": 10, "slow": 50}, start_date=start)

    first = paper.update_account(account_path, df)
    second = paper.update_account(account_path, df)
    assert first.history == second.history


def test_update_without_future_data_raises(tmp_path, df):
    account_path = tmp_path / "paper.json"
    paper.init_account(account_path, "buy_hold", {}, start_date="2099-01-01")
    with pytest.raises(ValueError):
        paper.update_account(account_path, df)
