create table if not exists public.ohlcv_candles (
    symbol text not null,
    exchange_symbol text not null,
    timeframe text not null,
    open_time bigint not null,
    close_time bigint not null,
    open numeric not null,
    high numeric not null,
    low numeric not null,
    close numeric not null,
    volume numeric not null,
    quote_volume numeric,
    trade_count integer,
    taker_buy_base_volume numeric,
    taker_buy_quote_volume numeric,
    is_closed boolean not null default true,
    source text not null default 'binance_usdm_futures',
    updated_at timestamptz not null default now(),
    primary key (symbol, timeframe, open_time)
);

create index if not exists ohlcv_candles_symbol_tf_time_idx
    on public.ohlcv_candles (symbol, timeframe, open_time desc);
