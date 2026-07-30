# Real-time Telegram Pattern Notifications

## Scope

`notifications/` is a research-alert subsystem isolated from trading, backtest,
and report enablement. It scans the latest 201 closed candles on `1h` and `4h`
for every enabled symbol in `config/symbols.json`.

The 201st candle is treated as an unconfirmed right-edge anchor. No right-side
Pivot/Swing window is required for that final candle. Earlier structural
anchors still use the existing confirmed Swing logic. Messages therefore
describe early observations and are not Buy/Sell signals.

## Rules

The notification scanner evaluates `PATTERN_002` through `PATTERN_008`.
`PATTERN_005`, `PATTERN_006`, and `PATTERN_008` are available inside this
subsystem even though their existing trading/report policy remains unchanged.
`FIXED_COMBO_006` is likewise evaluated only by the notification-specific
combination scorer.

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

The process bootstraps 201 completed Binance USD-M futures candles per
symbol/timeframe, immediately scans the latest completed window once, then
sleeps until the next UTC+8 whole hour. Durable event identities prevent this
startup scan from resending an event already delivered. The process does not
subscribe to a continuously active WebSocket scan.

## Hourly Schedule

At every UTC+8 whole hour, the service waits `scan_delay_seconds` (default:
5 seconds) for the exchange to settle the just-closed candle and performs one
REST reconciliation:

- `1h` has one newly completed candle and is scanned once every hour.
- `4h` is scanned only when its next Binance 4h candle has completed.
- If no new completed candle exists, the durable scan cursor prevents a repeat.

`scan_delay_seconds` is restricted to 5–10 seconds. Values outside that range,
including zero, are rejected during startup.

The service remains under systemd supervision but is asleep between hourly
ticks. Telegram Outbox retries remain independent so a temporary delivery
failure can recover without waiting for the next market scan.

## Production Reliability

Binance REST is the scheduled source. At each hourly tick, an empty, short,
discontinuous, or lagging cache is reloaded or backfilled. Missing
closed candles are replayed in chronological order, so each repaired right
edge is scanned rather than jumping directly to the newest candle.

The last successfully scanned candle is also stored in SQLite. After a process
or host restart, missed closes are rebuilt with their preceding 200-candle
context and replayed in order. `max_restart_replay_bars` bounds this catch-up
(default: 1000 closes); if the bound is exceeded, the service logs the cap and
replays the most recent bounded range.

Pattern detection is refused unless the cache contains exactly 201 closed,
chronological, interval-continuous candles. Market discovery and failed
warm-ups are retried. Telegram delivery runs through a SQLite Outbox, so a
Telegram outage does not block candle ingestion and pending images survive a
process restart.

Health transitions are sent to Telegram when one stream becomes abnormal or
recovers. The service also writes health and pending-Outbox counts after
scheduled checks. The delay, retry intervals, replay bound, and lag threshold
are configurable in `config/notifications.json`.

## Delivery and De-duplication

Each match sends one PNG containing all 201 candles, Pattern lines, anchors,
and UTC+8 anchor timestamps. Its caption includes symbol, Pattern rule,
timeframe, score, fixed-combination ID, and matched conditions.

Successfully sent identities are persisted in
`logs/notifications/state.sqlite3`, preventing duplicates after repeated REST
checks or process restarts. A payload is first committed to the Outbox and is
moved atomically to sent history only after Telegram accepts it.

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
