from __future__ import annotations

import ast
import base64
import datetime as dt
import hashlib
import subprocess
import traceback
from pathlib import Path

import pytest

from quantlab.errors import CloudUnavailableError, QuantLabError
from quantlab.qc import runner
from quantlab.qc.api import QCClient, _retry_delay, credentials_from_env
from quantlab.qc.objectstore import default_key, upload


class TestPreflightDegradation:
    def test_missing_lean_cli(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _: None)
        with pytest.raises(CloudUnavailableError, match=r"lean.*not installed"):
            runner.preflight()

    def test_missing_credentials(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/lean")
        monkeypatch.delenv("QC_USER_ID", raising=False)
        monkeypatch.delenv("QC_API_TOKEN", raising=False)
        with pytest.raises(CloudUnavailableError, match="QC_USER_ID"):
            runner.preflight()

    def test_error_message_points_to_simulator(self, monkeypatch) -> None:
        monkeypatch.delenv("QC_USER_ID", raising=False)
        monkeypatch.delenv("QC_API_TOKEN", raising=False)
        with pytest.raises(CloudUnavailableError, match="quant prop simulate"):
            credentials_from_env()


class TestParseIds:
    def test_url_pattern(self) -> None:
        out = (
            "Backtest complete: https://www.quantconnect.com/project/1234567/backtests/0a1b2c3d4e5f"
        )
        assert runner.parse_ids(out) == (1234567, "0a1b2c3d4e5f")

    def test_labelled_pattern(self) -> None:
        out = "Project id: 555\nStarted backtest\nbacktest id: deadbeef1234"
        assert runner.parse_ids(out) == (555, "deadbeef1234")

    def test_nothing_found(self) -> None:
        assert runner.parse_ids("no ids here") == (None, None)


class TestRunnerSecurity:
    def test_failed_command_redacts_api_token(self, monkeypatch) -> None:
        token = "SUPERSECRET"
        failed = subprocess.CompletedProcess(
            ["lean"], 1, stdout="", stderr=f"login rejected token {token}"
        )
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: failed)
        with pytest.raises(QuantLabError) as caught:
            runner._run(["lean", "login", "--api-token", token])
        assert token not in str(caught.value)
        assert "<redacted>" in str(caught.value)

    def test_timeout_is_wrapped_and_redacted(self, monkeypatch) -> None:
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

        monkeypatch.setattr(subprocess, "run", timeout)
        command = ["lean", "login", "-t", "SECRET"]
        with pytest.raises(QuantLabError, match="timed out") as caught:
            runner._run(command, timeout=1)
        assert "SECRET" not in str(caught.value)
        assert "SECRET" not in "".join(
            traceback.format_exception(caught.type, caught.value, caught.tb)
        )


class TestApiAuth:
    @pytest.mark.parametrize("header", ["nan", "inf", "-1"])
    def test_nonfinite_or_negative_retry_after_falls_back(self, header: str) -> None:
        assert _retry_delay(header, 2.0) == 2.0

    def test_hashed_timestamp_header(self, monkeypatch) -> None:
        monkeypatch.setattr("time.time", lambda: 1_750_000_000)
        client = QCClient(user_id="99999", api_token="secret-token")
        headers = client._headers()
        assert headers["Timestamp"] == "1750000000"
        expected_hash = hashlib.sha256(b"secret-token:1750000000").hexdigest()
        decoded = base64.b64decode(headers["Authorization"].split()[1]).decode()
        assert decoded == f"99999:{expected_hash}"

    def test_env_credentials_required(self, monkeypatch) -> None:
        monkeypatch.delenv("QC_USER_ID", raising=False)
        monkeypatch.delenv("QC_API_TOKEN", raising=False)
        with pytest.raises(CloudUnavailableError):
            QCClient()

    @pytest.mark.parametrize(
        "base_url",
        ["https://", "https:", "http://example.com/api", "ftp://example.com"],
    )
    def test_api_base_url_rejects_malformed_or_insecure_hosts(self, base_url: str) -> None:
        with pytest.raises(QuantLabError, match="base_url"):
            QCClient(user_id="1", api_token="secret", base_url=base_url)

    def test_api_base_url_allows_loopback_http_for_local_tests(self) -> None:
        client = QCClient(
            user_id="1", api_token="secret", base_url="http://127.0.0.1:8080/api/v2/"
        )
        assert client.base_url == "http://127.0.0.1:8080/api/v2"

    def test_transient_http_errors_retry_with_retry_after(self, monkeypatch) -> None:
        class Response:
            def __init__(self, status, payload=None, headers=None):
                self.status_code = status
                self._payload = payload or {}
                self.headers = headers or {}

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise __import__("requests").HTTPError(str(self.status_code))

            def json(self):
                return self._payload

        class Session:
            def __init__(self):
                self.responses = [
                    Response(429, headers={"Retry-After": "0"}),
                    Response(503),
                    Response(200, {"success": True, "value": 1}),
                ]

            def post(self, *args, **kwargs):
                return self.responses.pop(0)

        sleeps = []
        monkeypatch.setattr("time.sleep", sleeps.append)
        client = QCClient(user_id="1", api_token="secret", session=Session())
        assert client._post("test")["value"] == 1
        assert sleeps == [0.0, 2.0]

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"count": 1.5},
            {"max_polls": True},
            {"poll_seconds": float("nan")},
            {"start": -1},
            {"start": 2, "end": 1},
        ],
    )
    def test_chart_rejects_invalid_runtime_parameters(self, kwargs: dict) -> None:
        client = QCClient(user_id="1", api_token="secret")
        with pytest.raises(QuantLabError):
            client.read_backtest_chart(1, "abc", **kwargs)


class TestObjectStoreValidation:
    def test_default_key_requires_symbol(self) -> None:
        with pytest.raises(QuantLabError, match="symbol"):
            default_key(" ")

    @pytest.mark.parametrize("key", ["../secret", "/absolute", "bad\\key", "bad\nkey"])
    def test_upload_rejects_unsafe_key_before_cloud_call(self, tmp_path, key: str) -> None:
        source = tmp_path / "bars.csv"
        source.write_text("date,close\n")
        with pytest.raises(QuantLabError, match="key"):
            upload(source, key)


class TestStrategiesParse:
    @staticmethod
    def _strategy_source(project: str) -> str:
        root = Path(__file__).resolve().parents[2] / "cloud" / "strategies" / project
        return (root / "main.py").read_text()

    @classmethod
    def _strategy_method(cls, project: str, method: str):
        tree = ast.parse(cls._strategy_source(project))
        function = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == method
        )
        module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        namespace = {}
        exec(compile(module, f"<{project}:{method}>", "exec"), namespace)
        return namespace[method]

    @pytest.mark.parametrize("project", ["sma_cross_futures", "orb_equity", "custom_data_demo"])
    def test_strategy_files_are_valid_python(self, project: str) -> None:
        root = Path(__file__).resolve().parents[2] / "cloud" / "strategies" / project
        source = self._strategy_source(project)
        ast.parse(source)  # LEAN imports aren't installed locally; syntax must hold
        assert (root / "config.json").exists()

    def test_orb_places_brackets_from_actual_fills(self) -> None:
        tree = ast.parse(self._strategy_source("orb_equity"))
        methods = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }
        on_data_calls = {
            node.func.attr
            for node in ast.walk(methods["on_data"])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        source = self._strategy_source("orb_equity")
        assert "stop_market_order" not in on_data_calls
        assert "limit_order" not in on_data_calls
        assert "OrderStatus.PARTIALLY_FILLED" in source
        assert "holding.average_price" in source
        assert "bracket double-fill reconciliation" in source

    def test_orb_starts_entry_locked_until_exchange_open_reset(self) -> None:
        source = self._strategy_source("orb_equity")
        initialize = next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name == "initialize"
        )
        assignments = [
            node
            for node in ast.walk(initialize)
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Attribute)
            and node.targets[0].attr == "_traded_today"
        ]
        assert len(assignments) == 1
        assert isinstance(assignments[0].value, ast.Constant)
        assert assignments[0].value.value is True

    def test_orb_new_session_clears_completed_async_flatten_before_first_bar(self) -> None:
        reset = self._strategy_method("orb_equity", "_reset_day")
        on_data = self._strategy_method("orb_equity", "on_data")

        class Holding:
            invested = False
            quantity = 0

        class Portfolio(dict):
            @property
            def invested(self):
                return False

        class Transactions:
            @staticmethod
            def get_open_orders(symbol):
                return []

        class Strategy:
            _spy = "SPY"
            RANGE_BARS = 15

            def __init__(self):
                self._startup_reconciled = True
                self._flattening = True
                self._flatten_ticket = object()
                self._exit_tickets = [object()]
                self.portfolio = Portfolio(SPY=Holding())
                self.transactions = Transactions()

        strategy = Strategy()
        reset(strategy)
        bar = type("Bar", (), {"high": 101.0, "low": 99.0, "close": 100.0})()
        slice_ = type("Slice", (), {"bars": {"SPY": bar}})()
        on_data(strategy, slice_)
        assert not strategy._flattening
        assert strategy._bars_seen == 1
        assert strategy._range_high == 101.0

    def test_orb_synchronous_entry_fill_gets_brackets_after_ticket_assignment(self) -> None:
        on_data = self._strategy_method("orb_equity", "on_data")

        class Holding:
            invested = False
            quantity = 0
            average_price = 101.0

        class Portfolio(dict):
            @property
            def invested(self):
                return self["SPY"].invested

        class Transactions:
            @staticmethod
            def get_open_orders(symbol):
                return []

        class Bars(dict):
            pass

        class Strategy:
            _spy = "SPY"
            RANGE_BARS = 15

            def __init__(self):
                self._startup_reconciled = True
                self._flattening = False
                self._bars_seen = 15
                self._range_high = 100.0
                self._range_low = 90.0
                self._traded_today = False
                self._entry_ticket = None
                self._entry_range_size = None
                self.portfolio = Portfolio(SPY=Holding())
                self.transactions = Transactions()
                self.synced = 0

            @staticmethod
            def calculate_order_quantity(symbol, fraction):
                return 1

            def market_order(self, symbol, quantity, **kwargs):
                self.portfolio[symbol].quantity = quantity
                self.portfolio[symbol].invested = True
                return type("Ticket", (), {"order_id": 7})()

            def _sync_brackets(self):
                self.synced += 1

        strategy = Strategy()
        bar = type("Bar", (), {"high": 101.0, "low": 99.0, "close": 101.0})()
        on_data(strategy, type("Slice", (), {"bars": Bars(SPY=bar)})())
        assert strategy._entry_ticket.order_id == 7
        assert strategy.synced == 1

    def test_orb_does_not_submit_sibling_after_immediate_stop_fill(self) -> None:
        sync = self._strategy_method("orb_equity", "_sync_brackets")
        statuses = type(
            "Statuses",
            (),
            {
                "FILLED": "filled",
                "PARTIALLY_FILLED": "partial",
                "INVALID": "invalid",
                "CANCELED": "canceled",
            },
        )
        sync.__globals__["OrderStatus"] = statuses

        class Holding:
            quantity = 2
            average_price = 100.0

        class Strategy:
            _spy = "SPY"
            _entry_range_size = 4.0

            def __init__(self):
                self.holding = Holding()
                self.portfolio = {"SPY": self.holding}
                self._exit_tickets = []
                self.targets = []
                self.flatten_reason = None

            def stop_market_order(self, *args, **kwargs):
                self.holding.quantity = 0
                return type("Ticket", (), {"status": "filled"})()

            def limit_order(self, *args, **kwargs):
                self.targets.append(args)

            def _begin_flatten(self, reason):
                self.flatten_reason = reason

        strategy = Strategy()
        sync(strategy)
        assert not strategy.targets
        assert strategy.flatten_reason == "stop resolved during bracket submission"

    def test_orb_recomputes_target_size_after_immediate_partial_stop(self) -> None:
        sync = self._strategy_method("orb_equity", "_sync_brackets")
        sync.__globals__["OrderStatus"] = type(
            "Statuses",
            (),
            {
                "FILLED": "filled",
                "PARTIALLY_FILLED": "partial",
                "INVALID": "invalid",
                "CANCELED": "canceled",
            },
        )

        class Holding:
            quantity = 2
            average_price = 100.0

        class Strategy:
            _spy = "SPY"
            _entry_range_size = 4.0

            def __init__(self):
                self.holding = Holding()
                self.portfolio = {"SPY": self.holding}
                self._exit_tickets = []
                self.target_quantities = []

            def stop_market_order(self, *args, **kwargs):
                self.holding.quantity = 1
                return type("Ticket", (), {"status": "partial", "order_id": 1})()

            def limit_order(self, symbol, quantity, *args, **kwargs):
                self.target_quantities.append(quantity)
                return type("Ticket", (), {"status": "submitted", "order_id": 2})()

            def _begin_flatten(self, reason):
                raise AssertionError(reason)

            def _resize_sibling(self, order_id):
                raise AssertionError("target was not partially filled")

        strategy = Strategy()
        sync(strategy)
        assert strategy.target_quantities == [-1]

    def test_orb_partial_exit_resizes_sibling_by_total_order_quantity(self) -> None:
        resize = self._strategy_method("orb_equity", "_resize_sibling")

        class Response:
            is_success = True

        class Ticket:
            def __init__(self, order_id, quantity_filled):
                self.order_id = order_id
                self.quantity_filled = quantity_filled
                self.updates = []

            def update_quantity(self, quantity, tag):
                self.updates.append(quantity)
                return Response()

        class Holding:
            quantity = 5

        class Strategy:
            _spy = "SPY"

            def __init__(self):
                self.stop = Ticket(1, -3)
                self.target = Ticket(2, -2)
                self._exit_tickets = [self.stop, self.target]
                self.portfolio = {"SPY": Holding()}

            def _begin_flatten(self, reason):
                raise AssertionError(reason)

        strategy = Strategy()
        resize(strategy, 2)
        assert strategy.stop.updates == [-8]  # -3 filled plus -5 still protecting

        strategy.portfolio["SPY"].quantity = 4
        strategy.stop.quantity_filled = -4
        resize(strategy, 1)
        assert strategy.target.updates == [-6]  # -2 filled plus -4 still protecting

    def test_orb_later_entry_fill_preserves_prior_exit_fills_in_totals(self) -> None:
        sync = self._strategy_method("orb_equity", "_sync_brackets")

        class Response:
            is_success = True

        class Ticket:
            def __init__(self, quantity_filled):
                self.quantity_filled = quantity_filled
                self.quantity_updates = []

            def update_quantity(self, quantity, tag):
                self.quantity_updates.append(quantity)
                return Response()

            def update_stop_price(self, price, tag):
                return Response()

            def update_limit_price(self, price, tag):
                return Response()

        class Holding:
            quantity = 6
            average_price = 100.0

        class Strategy:
            _spy = "SPY"
            _entry_range_size = 4.0

            def __init__(self):
                self.stop = Ticket(-3)
                self.target = Ticket(-2)
                self._exit_tickets = [self.stop, self.target]
                self.portfolio = {"SPY": Holding()}

            def _begin_flatten(self, reason):
                raise AssertionError(reason)

        strategy = Strategy()
        sync(strategy)
        assert strategy.stop.quantity_updates == [-9]
        assert strategy.target.quantity_updates == [-8]

    def test_orb_partial_exit_at_zero_cancels_and_reconciles(self) -> None:
        resize = self._strategy_method("orb_equity", "_resize_sibling")

        class Holding:
            quantity = 0

        class Strategy:
            _spy = "SPY"

            def __init__(self):
                self.portfolio = {"SPY": Holding()}
                self.canceled_except = None
                self.reason = None

            def _cancel_exits(self, except_order_id=None):
                self.canceled_except = except_order_id

            def _begin_flatten(self, reason):
                self.reason = reason

        strategy = Strategy()
        resize(strategy, 7)
        assert strategy.canceled_except == 7
        assert strategy.reason == "partial exit exhausted or inverted position"

    def test_orb_incomplete_existing_bracket_fails_safe(self) -> None:
        sync = self._strategy_method("orb_equity", "_sync_brackets")

        class Holding:
            quantity = 1
            average_price = 100.0

        class Strategy:
            _spy = "SPY"
            _entry_range_size = 2.0

            def __init__(self):
                self.portfolio = {"SPY": Holding()}
                self._exit_tickets = [object()]
                self.reason = None

            def _begin_flatten(self, reason):
                self.reason = reason

        strategy = Strategy()
        sync(strategy)
        assert strategy.reason == "incomplete protective bracket state"

    def test_future_strategy_reconciles_contract_rolls(self) -> None:
        source = self._strategy_source("sma_cross_futures")
        assert "symbol_changed_events" in source
        assert "changed.old_symbol" in source
        assert "changed.new_symbol" in source
        assert "get_open_orders(mapped)" in source
        assert "before_market_close(self._continuous, 15)" in source

    def test_future_scheduled_flatten_uses_current_mapped_contract(self) -> None:
        flatten = self._strategy_method("sma_cross_futures", "_scheduled_flatten")

        class Continuous:
            mapped = "CURRENT"

        class Strategy:
            _continuous = "CONTINUOUS"

            def __init__(self):
                self.time = dt.datetime(2026, 11, 27, 11, 45)
                self.securities = {"CONTINUOUS": Continuous()}
                self._contract = None
                self._retiring_contracts = set()
                self._entry_locked_date = None
                self.calls = []

            def _reconcile_retiring(self, tag):
                self.calls.append(tag)

        strategy = Strategy()
        flatten(strategy)
        assert strategy._contract == "CURRENT"
        assert strategy._retiring_contracts == {"CURRENT"}
        assert strategy._entry_locked_date == dt.date(2026, 11, 27)
        assert strategy.calls == ["scheduled session flatten"]

    def test_future_close_lock_persists_until_next_date(self) -> None:
        locked = self._strategy_method("sma_cross_futures", "_entries_locked")

        class Strategy:
            _entry_locked_date = dt.date(2026, 11, 27)
            time = dt.datetime(2026, 11, 27, 11, 46)

        strategy = Strategy()
        assert locked(strategy)
        strategy.time = dt.datetime(2026, 11, 28, 8, 45)
        assert not locked(strategy)
        assert strategy._entry_locked_date is None

    def test_future_flatten_waits_for_cancels_then_retries_to_zero(self) -> None:
        reconcile = self._strategy_method("sma_cross_futures", "_reconcile_retiring")

        class Order:
            def __init__(self, order_id):
                self.id = order_id

        class Holding:
            quantity = 2

        class Transactions:
            def __init__(self):
                self.open_orders = [Order(1)]
                self.canceled = []

            def get_open_orders(self, symbol):
                return self.open_orders

            def cancel_order(self, order_id, tag=""):
                self.canceled.append(order_id)

        class Strategy:
            def __init__(self):
                self._retiring_contracts = {"OLD"}
                self._flatten_tickets = {}
                self.portfolio = {"OLD": Holding()}
                self.transactions = Transactions()
                self.placed = []

            def market_order(self, symbol, quantity, **kwargs):
                self.placed.append((symbol, quantity, kwargs))
                return type("Ticket", (), {"order_id": 9})()

        strategy = Strategy()
        reconcile(strategy, "roll")
        assert strategy.transactions.canceled == [1]
        assert not strategy.placed
        strategy.transactions.open_orders = []
        reconcile(strategy, "roll")
        assert strategy.placed == [("OLD", -2, {"asynchronous": True, "tag": "roll"})]
        strategy.portfolio["OLD"].quantity = 0
        reconcile(strategy, "roll")
        assert not strategy._retiring_contracts

    def test_future_startup_discovers_stale_holdings_and_orders(self) -> None:
        reconcile = self._strategy_method("sma_cross_futures", "_reconcile_startup")

        class Holding:
            def __init__(self, invested):
                self.invested = invested

        class Order:
            def __init__(self, symbol):
                self.symbol = symbol

        class Security:
            def __init__(self, symbol):
                self.symbol = symbol

        class Transactions:
            @staticmethod
            def get_open_orders():
                return [Order("PENDING_OLD"), Order("CURRENT")]

        class Strategy:
            def __init__(self):
                self._continuous = "CONTINUOUS"
                self._startup_reconciled = False
                self._retiring_contracts = set()
                self.securities = {
                    symbol: Security(symbol)
                    for symbol in ("CONTINUOUS", "CURRENT", "STALE")
                }
                self.portfolio = {
                    "CONTINUOUS": Holding(False),
                    "CURRENT": Holding(False),
                    "STALE": Holding(True),
                }
                self.transactions = Transactions()

        strategy = Strategy()
        reconcile(strategy, "CURRENT")
        assert strategy._startup_reconciled
        assert strategy._retiring_contracts == {"STALE", "PENDING_OLD"}

    def test_orb_flatten_waits_for_stale_order_cancellation(self) -> None:
        reconcile = self._strategy_method("orb_equity", "_reconcile_flatten")

        class Order:
            def __init__(self, order_id):
                self.id = order_id

        class Holding:
            quantity = 3

        class Transactions:
            def __init__(self):
                self.open_orders = [Order(4)]
                self.canceled = []

            def get_open_orders(self, symbol):
                return self.open_orders

            def cancel_order(self, order_id, tag=""):
                self.canceled.append(order_id)

        class Strategy:
            _spy = "SPY"

            def __init__(self):
                self._flatten_ticket = None
                self._flattening = True
                self.portfolio = {"SPY": Holding()}
                self.transactions = Transactions()
                self.placed = []

            def market_order(self, symbol, quantity, **kwargs):
                self.placed.append((symbol, quantity, kwargs))
                return type("Ticket", (), {"order_id": 5})()

        strategy = Strategy()
        reconcile(strategy)
        assert strategy.transactions.canceled == [4]
        assert not strategy.placed
        strategy.transactions.open_orders = []
        reconcile(strategy)
        assert strategy.placed[0][0:2] == ("SPY", -3)

    def test_orb_flatten_locks_entries_until_next_session_reset(self) -> None:
        begin = self._strategy_method("orb_equity", "_begin_flatten")

        class Strategy:
            _traded_today = False
            _flattening = False

            def _cancel_exits(self):
                pass

            def _reconcile_flatten(self, tag):
                self.reconciled = tag

        strategy = Strategy()
        begin(strategy, "scheduled end-of-day flatten")
        assert strategy._traded_today
        assert strategy._flattening

    def test_custom_signal_trades_only_the_proxy_during_market_hours(self) -> None:
        tree = ast.parse(self._strategy_source("custom_data_demo"))
        on_data = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "on_data"
        )
        calls = [
            node
            for node in ast.walk(on_data)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        trade_calls = [node for node in calls if node.func.attr in {"set_holdings", "liquidate"}]
        assert trade_calls
        assert all(
            isinstance(call.args[0], ast.Attribute) and call.args[0].attr == "_trade_symbol"
            for call in trade_calls
        )
        assert "extended_market_hours=False" in self._strategy_source("custom_data_demo")

    def test_custom_signal_flattens_unexpected_short_before_signal_logic(self) -> None:
        on_data = self._strategy_method("custom_data_demo", "on_data")

        class Ready:
            is_ready = True

        class ExchangeHours:
            @staticmethod
            def is_open(time, extended_market_hours=False):
                return True

        class Strategy:
            _symbol = "DEMO"
            _trade_symbol = "SPY"
            is_warming_up = False
            _slow = Ready()
            time = dt.datetime(2026, 1, 5, 15, tzinfo=dt.UTC)

            def __init__(self):
                self.securities = {
                    "SPY": type(
                        "Security",
                        (),
                        {
                            "is_tradable": True,
                            "exchange": type("Exchange", (), {"hours": ExchangeHours()})(),
                        },
                    )()
                }
                self.transactions = type(
                    "Transactions",
                    (),
                    {"get_open_orders": staticmethod(lambda symbol: [])},
                )()
                self.portfolio = {"SPY": type("Holding", (), {"quantity": -2})()}
                self.liquidated = []

            def liquidate(self, symbol):
                self.liquidated.append(symbol)

            def set_holdings(self, symbol, target):
                raise AssertionError("must flatten the short before entering")

        strategy = Strategy()
        on_data(strategy, {"DEMO": object()})
        assert strategy.liquidated == ["SPY"]

    def test_custom_data_reader_rejects_nonpositive_prices(self) -> None:
        import math

        reader = self._strategy_method("custom_data_demo", "reader")

        class Bar(dict):
            pass

        reader.__globals__.update(
            {
                "isfinite": math.isfinite,
                "datetime": dt.datetime,
                "timedelta": dt.timedelta,
                "ObjectStoreBars": Bar,
            }
        )
        config = type("Config", (), {"symbol": "DEMO"})()
        assert (
            reader(
                object(),
                config,
                "2026-01-05T14:30:00Z,-1,2,-2,1,100",
                dt.datetime(2026, 1, 5),
                False,
            )
            is None
        )
