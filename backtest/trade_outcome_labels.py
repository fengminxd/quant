"""Structured labels parsed from retrospective anchor-trade reports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


UTC_PLUS_8 = timezone(timedelta(hours=8))
TRADE_LINE = re.compile(
    r"^symbol=(?P<symbol>\S+) timeframe=(?P<timeframe>\S+) "
    r"pattern=(?P<pattern>\S+) rule=(?P<rule>\S+) "
    r"outcome=(?P<outcome>\S+).*? direction=(?P<direction>\S+) "
    r"entry_rule='(?P<entry_rule>[^']+)' "
    r"(?:structure_time=\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC\+8 "
    r"structure_level=-?\d+(?:\.\d+)? )?"
    r"entry_time=(?P<entry_time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC\+8 "
    r"entry=(?P<entry>\d+(?:\.\d+)?) "
    r"stop=(?P<stop>\d+(?:\.\d+)?) "
    r"target=(?P<target>\d+(?:\.\d+)?) "
    r"(?:lock_trigger=(?P<lock_trigger>\d+(?:\.\d+)?) "
    r"locked_stop=(?P<locked_stop>\d+(?:\.\d+)?) "
    r"lock_time=(?:(?P<lock_time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC\+8|-) )?"
    r"exit_time=(?:(?P<exit_time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC\+8|-) "
    r"(?:exit=(?P<exit>\d+(?:\.\d+)?|-) )?"
    r"bars_held="
)


@dataclass(frozen=True)
class AnchorTrade:
    """One retrospective trade label parsed from the outcome report."""

    trade_id: int
    pattern: str
    rule: str
    outcome: str
    direction: str
    entry_time: datetime
    entry: float
    stop: float
    target: float
    exit_time: datetime | None
    exit_price: float | None = None
    lock_trigger: float | None = None
    locked_stop: float | None = None
    lock_time: datetime | None = None


def parse_anchor_trades(
    path: str | Path,
    *,
    allow_empty: bool = False,
) -> list[AnchorTrade]:
    """Parse every qualified trade, preserving report order."""

    trades: list[AnchorTrade] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = TRADE_LINE.match(line)
        if not match:
            continue
        fields = match.groupdict()
        exit_price = _exit_price(fields)
        trades.append(
            AnchorTrade(
                trade_id=len(trades) + 1,
                pattern=fields["pattern"],
                rule=fields["rule"],
                outcome=fields["outcome"],
                direction=fields["direction"],
                entry_time=_parse_utc_plus_8(fields["entry_time"]),
                entry=float(fields["entry"]),
                stop=float(fields["stop"]),
                target=float(fields["target"]),
                exit_time=(
                    _parse_utc_plus_8(fields["exit_time"])
                    if fields["exit_time"]
                    else None
                ),
                exit_price=exit_price,
                lock_trigger=(
                    float(fields["lock_trigger"])
                    if fields["lock_trigger"]
                    else None
                ),
                locked_stop=(
                    float(fields["locked_stop"])
                    if fields["locked_stop"]
                    else None
                ),
                lock_time=(
                    _parse_utc_plus_8(fields["lock_time"])
                    if fields["lock_time"]
                    else None
                ),
            )
        )
    if not trades and not allow_empty:
        raise ValueError(f"no qualified trades found in {path}")
    return trades


def timestamp_to_utc_plus_8(value: int | str | datetime) -> datetime:
    """Normalize framework timestamps to a timezone-aware UTC+8 datetime."""

    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        moment = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(UTC_PLUS_8)


def _parse_utc_plus_8(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC_PLUS_8)


def _exit_price(fields: dict[str, str | None]) -> float | None:
    value = fields["exit"]
    if value and value != "-":
        return float(value)
    if fields["outcome"] == "take_profit":
        return float(fields["target"])
    if fields["outcome"] == "stop_loss":
        return float(fields["stop"])
    return None
