# Real-time Telegram Pattern Notifications

## Scope

`notifications/` is a research-alert subsystem isolated from trading, backtest,
and report enablement. It scans `15m`, `1h` and `4h` closed candles for crypto
symbols in `config/symbols.json`; TradeFi symbols use only `1h` and `4h`.
The `15m` and `1h` levels retain exactly 201
candles; `4h` retains `four_hour_history_bars` (default 401) and is never
promoted to `1d` merely because its window contains more than 201 candles.

The latest candle is treated as an unconfirmed right-edge anchor. No right-side
Pivot/Swing window is required for that final candle. Earlier structural
anchors still use the existing confirmed Swing logic. Messages therefore
describe early observations and are not Buy/Sell signals.

## Rules

The notification scanner evaluates only `PATTERN_002` (triangle),
`PATTERN_003` (three-point trendline support), `PATTERN_004` (horizontal
support), and `PATTERN_007` (inverse head and shoulders).
`PATTERN_005`, `PATTERN_006`, `PATTERN_008`, and `PATTERN_009` are disabled
for notifications, including previously queued alerts. Trading/report policy
is unchanged.

`notifications/policy.py` defines the TradeFi symbols: `XAU`, `XAG`, `CL`,
`SPCX`, `MU`, `SNDK`, `SKHYNIX`, `NVDA`, `DRAM`, `SOXL`, `KORU`, and `MSTR`.
They are excluded from 15m warm-up, scanning, health checks and delivery.
Other symbols, including `ONDO`, use all three notification levels. Update
this explicit list when adding another TradeFi symbol; new symbols otherwise
receive 15m notifications. Symbol matching also accepts `USDT` pair names.

## Telegram Configuration

`config/notifications.json` names the environment variables containing the
Telegram credentials:

```bash
export TELEGRAM_BOT_TOKEN='...'
export TELEGRAM_CHAT_ID='...'
```

Do not commit literal production credentials.

## Run

```bash
.venv/bin/python -m notifications.run
```

or, after installing the project entry points:

```bash
pattern-notifications
```

The process bootstraps 201 completed Binance USD-M futures candles for `15m`/`1h`,
and up to `four_hour_history_bars` candles for `4h`. Startup only warms the data:
it discards pending payloads from previous runs and waits for the next scheduled
boundary. It never scans or sends historical alerts at startup and does not
subscribe to a continuously active WebSocket scan.

## Interval Schedule

With crypto 15m notifications configured, the service wakes at each UTC+8
quarter-hour. With only TradeFi symbols, it wakes hourly (or every four hours
if only `4h` is configured). It
waits `scan_delay_seconds` (default: 5 seconds) for exchange settlement and
performs one REST reconciliation:

- At whole-hour boundaries, eligible `15m` and `1h` streams are scanned.
- `4h` streams are scanned only at UTC+8 hours `00`, `04`, `08`, `12`, `16`, `20`.
- At minutes `15`, `30`, and `45`, only eligible crypto `15m` streams are reconciled.
- Only the candle closing at the scheduled boundary can generate a new alert.
- If no new completed candle exists, the durable scan cursor prevents a repeat.

`scan_delay_seconds` is restricted to 5–10 seconds. Values outside that range,
including zero, are rejected during startup.

The service sleeps between scheduled ticks. If a wake-up is more than 10 seconds
late, that tick is skipped. Scanning and delivery form one scheduled batch;
there is no independent Outbox retry loop. A batch expires at the next scheduled
scan time, including any in-flight Telegram retries. Failed or expired alerts
are dropped rather than sent at a later tick or after a restart.

## Production Reliability

Binance REST is the scheduled source. An empty, short, discontinuous, or lagging
cache is refreshed with the latest retained history. Historical candles are
loaded only as context: missing closes are never replayed through the scanner.
The latest candle must match the current scheduled close; stale data is skipped.

Pattern detection is refused unless the cache contains the required closed,
chronological, interval-continuous candles: exactly 201 for `15m`/`1h`, and at
least 201 for `4h`. Market discovery and failed warm-ups can be retried, but
missed reminders are deliberately not recovered. Durable scan cursors prevent
repeated scans of the same close.

Health transitions are sent during scheduled batches when a stream becomes
abnormal or recovers. Health and pending-Outbox counts are also logged. The
settlement delay, bootstrap retry interval, and lag threshold are configurable
in `config/notifications.json`. The former `max_restart_replay_bars` and
`delivery_retry_interval_seconds` settings are no longer used.

## Delivery and De-duplication

Each match sends one PNG containing the complete scan window, Pattern lines,
anchors, and UTC+8 anchor timestamps. Its caption includes symbol, Pattern rule,
timeframe, score, fixed-combination ID, and matched conditions.

Successfully sent identities are persisted in
`logs/notifications/state.sqlite3`, preventing duplicates after repeated REST
checks or process restarts. A payload is first committed to the Outbox and is
moved atomically to sent history only after Telegram accepts it.
The Outbox holds only the current scheduled batch. All unsent payloads are
removed at startup and at the start/end of every batch, including disabled
patterns and symbol/timeframe pairs. Discarded alerts are not marked as sent;
successfully sent history remains intact. This intentionally trades missed
alerts during downtime or Telegram failures for strictly live-only delivery.

## systemd 24/7 Operation

The repository includes `deploy/pattern-notifications.service`. It is a
deployment template for this workspace path; creating system services remains
an explicit host-administration step.

```bash
cp config/notifications.env.example config/notifications.env
# Edit config/notifications.env and set the real token/chat ID.
mkdir -p logs/notifications
sudo cp deploy/pattern-notifications.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pattern-notifications
sudo systemctl status pattern-notifications
```

Follow logs with:

```bash
journalctl -u pattern-notifications -f
```

After code or configuration changes:

```bash
sudo systemctl restart pattern-notifications
```

The unit restarts the process after failures, waits for network availability,
uses a private temporary directory, keeps credentials outside source control,
and grants write access only to `logs/notifications` within the project.

Before relying on it unattended, run a real exchange-and-Telegram soak test
with production credentials and verify at least one controlled stop/restart,
one network interruption, one Telegram interruption, and the corresponding
recovery messages.

## Causality and Risk

Only closed candles enter the scanner. The final anchor is intentionally
provisional because no right-side confirmation is required. A later candle can
therefore invalidate the observation. The notification policy must never be
used as evidence that a disabled rule has been enabled for trading.
