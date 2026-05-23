-- SC Oil Agent SQLite schema
-- Scope:
-- 1. Phase 1 minimal tables: data_snapshot, evidence_database, research_reports
-- 2. MVP formal tables: market_prices, fx_rates, spread_table, inventory_data,
--    oil_events, evidence_database, research_reports
--
-- WARNING:
-- This schema contains DROP TABLE statements. It is intended for new database
-- creation or explicit reset/rebuild flows only. Normal initialization must
-- not execute this file against an existing database with valuable data.

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS market_prices;
DROP TABLE IF EXISTS fx_rates;
DROP TABLE IF EXISTS spread_table;
DROP TABLE IF EXISTS inventory_data;
DROP TABLE IF EXISTS china_fundamental_data;
DROP TABLE IF EXISTS sentiment_data;
DROP TABLE IF EXISTS oil_events;
DROP TABLE IF EXISTS evidence_database;
DROP TABLE IF EXISTS research_reports;
DROP TABLE IF EXISTS data_snapshot;

CREATE TABLE data_snapshot (
    data_snapshot_id TEXT PRIMARY KEY,
    snapshot_date TEXT NOT NULL,
    report_date TEXT NOT NULL,
    raw_data_version TEXT,
    processed_data_version TEXT,
    prompt_version TEXT,
    calculation_version TEXT,
    code_version TEXT,
    source_status TEXT NOT NULL DEFAULT 'warning'
        CHECK (source_status IN ('pass', 'warning', 'fail')),
    quality_warnings TEXT,
    created_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE market_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    contract TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    settlement REAL,
    volume REAL,
    open_interest REAL,
    currency TEXT,
    unit TEXT,
    source TEXT NOT NULL,
    source_status TEXT NOT NULL DEFAULT 'warning'
        CHECK (source_status IN ('pass', 'warning', 'fail')),
    update_time TEXT,
    created_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (date, symbol, contract, source)
);

CREATE TABLE fx_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    pair TEXT NOT NULL,
    mid_price REAL,
    close REAL,
    intraday_price REAL,
    source TEXT NOT NULL,
    source_status TEXT NOT NULL DEFAULT 'warning'
        CHECK (source_status IN ('pass', 'warning', 'fail')),
    update_time TEXT,
    created_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (date, pair, source)
);

CREATE TABLE spread_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    sc_contract TEXT,
    sc_close REAL,
    brent_price REAL,
    wti_price REAL,
    oman_price REAL,
    dubai_price REAL,
    usd_cny REAL,
    sc_brent_spread REAL,
    sc_wti_spread REAL,
    sc_oman_spread REAL,
    sc_dubai_spread REAL,
    near_contract TEXT,
    far_contract TEXT,
    calendar_spread REAL,
    structure_type TEXT CHECK (
        structure_type IS NULL
        OR structure_type IN ('Backwardation', 'Contango', 'Flat')
    ),
    calculation_method TEXT NOT NULL DEFAULT 'simple_fx_adjusted_v1',
    data_alignment_note TEXT,
    source TEXT NOT NULL DEFAULT 'Python calculation',
    source_status TEXT NOT NULL DEFAULT 'warning'
        CHECK (source_status IN ('pass', 'warning', 'fail')),
    created_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (date, sc_contract, calculation_method, source)
);

CREATE TABLE inventory_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    country_or_region TEXT NOT NULL,
    crude_inventory REAL,
    gasoline_inventory REAL,
    distillate_inventory REAL,
    cushing_inventory REAL,
    port_inventory REAL,
    refinery_inventory REAL,
    unit TEXT,
    source TEXT NOT NULL,
    source_status TEXT NOT NULL DEFAULT 'warning'
        CHECK (source_status IN ('pass', 'warning', 'fail')),
    publish_time TEXT,
    created_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (date, country_or_region, source)
);

CREATE TABLE china_fundamental_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    crude_import REAL,
    refinery_run REAL,
    port_inventory REAL,
    refinery_inventory REAL,
    gasoline_demand REAL,
    diesel_demand REAL,
    jet_fuel_demand REAL,
    refinery_margin REAL,
    unit TEXT,
    source TEXT NOT NULL,
    source_status TEXT NOT NULL DEFAULT 'warning'
        CHECK (source_status IN ('pass', 'warning', 'fail')),
    publish_time TEXT,
    created_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (date, source)
);

CREATE TABLE sentiment_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    data_time TEXT,
    sentiment_source TEXT NOT NULL,
    sentiment_type TEXT,
    related_asset TEXT DEFAULT 'SC',
    sentiment_score REAL,
    sentiment_label TEXT CHECK (
        sentiment_label IS NULL
        OR sentiment_label IN ('positive', 'neutral', 'negative', '利多', '中性', '利空')
    ),
    sample_size INTEGER,
    summary TEXT,
    keywords TEXT,
    source TEXT NOT NULL,
    source_status TEXT NOT NULL DEFAULT 'warning'
        CHECK (source_status IN ('pass', 'warning', 'fail')),
    publish_time TEXT,
    created_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (date, sentiment_source, related_asset, source)
);

CREATE TABLE oil_events (
    event_id TEXT PRIMARY KEY,
    event_time TEXT,
    publish_time TEXT,
    event_type TEXT,
    region TEXT,
    description TEXT NOT NULL,
    affected_factor TEXT,
    expected_impact TEXT,
    actual_market_response TEXT,
    source TEXT NOT NULL,
    source_level TEXT,
    source_status TEXT NOT NULL DEFAULT 'warning'
        CHECK (source_status IN ('pass', 'warning', 'fail')),
    created_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE research_reports (
    report_id TEXT PRIMARY KEY,
    data_snapshot_id TEXT,
    date TEXT NOT NULL,
    topic TEXT,
    conclusion TEXT,
    evidence_ids TEXT,
    confidence TEXT CHECK (
        confidence IS NULL
        OR confidence IN ('高', '中', '低', 'high', 'medium', 'low')
    ),
    report_status TEXT NOT NULL DEFAULT 'warning'
        CHECK (report_status IN ('pass', 'warning', 'fail')),
    prompt_version TEXT,
    calculation_version TEXT,
    code_version TEXT,
    report_path TEXT,
    report_markdown TEXT,
    analyst_review TEXT,
    error_type TEXT CHECK (
        error_type IS NULL
        OR error_type IN (
            '数据错误',
            '口径错误',
            '逻辑错误',
            '归因过度',
            '结论过强',
            '遗漏变量'
        )
    ),
    severity TEXT CHECK (
        severity IS NULL
        OR severity IN ('高', '中', '低', 'high', 'medium', 'low')
    ),
    error_points TEXT,
    need_update_data_source INTEGER NOT NULL DEFAULT 0
        CHECK (need_update_data_source IN (0, 1)),
    need_update_calculation_rule INTEGER NOT NULL DEFAULT 0
        CHECK (need_update_calculation_rule IN (0, 1)),
    need_update_prompt INTEGER NOT NULL DEFAULT 0
        CHECK (need_update_prompt IN (0, 1)),
    correction TEXT,
    created_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (data_snapshot_id) REFERENCES data_snapshot (data_snapshot_id)
);

CREATE TABLE evidence_database (
    evidence_id TEXT PRIMARY KEY,
    report_id TEXT,
    data_snapshot_id TEXT,
    source_name TEXT NOT NULL,
    source_level TEXT,
    evidence_type TEXT,
    publish_time TEXT,
    data_time TEXT,
    extracted_fact TEXT NOT NULL,
    raw_value TEXT,
    normalized_value REAL,
    unit TEXT,
    related_variable TEXT,
    conclusion_impact TEXT,
    confidence TEXT CHECK (
        confidence IS NULL
        OR confidence IN ('高', '中', '低', 'high', 'medium', 'low')
    ),
    url_or_reference TEXT,
    source_status TEXT NOT NULL DEFAULT 'warning'
        CHECK (source_status IN ('pass', 'warning', 'fail')),
    created_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (report_id) REFERENCES research_reports (report_id),
    FOREIGN KEY (data_snapshot_id) REFERENCES data_snapshot (data_snapshot_id)
);

CREATE INDEX idx_market_prices_date_symbol
    ON market_prices (date, symbol);

CREATE INDEX idx_market_prices_contract
    ON market_prices (contract);

CREATE INDEX idx_fx_rates_date_pair
    ON fx_rates (date, pair);

CREATE INDEX idx_spread_table_date_contract
    ON spread_table (date, sc_contract);

CREATE INDEX idx_inventory_data_date_region
    ON inventory_data (date, country_or_region);

CREATE INDEX idx_sentiment_data_date_asset
    ON sentiment_data (date, related_asset);

CREATE INDEX idx_oil_events_time_type
    ON oil_events (event_time, event_type);

CREATE INDEX idx_evidence_report
    ON evidence_database (report_id);

CREATE INDEX idx_evidence_snapshot
    ON evidence_database (data_snapshot_id);

CREATE INDEX idx_reports_date
    ON research_reports (date);
