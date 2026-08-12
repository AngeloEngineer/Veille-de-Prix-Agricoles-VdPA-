-- Schéma dédié à la couche staging : Copie typée brut MongoDB, aucune logique métier
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE staging.stg_food_prices (
    id BIGSERIAL PRIMARY KEY,
    country_iso3 CHAR(3) NOT NULL,
    price_date DATE NOT NULL,
    admin1 TEXT,
    admin2 TEXT,
    market TEXT NOT NULL,
    market_id INTEGER NOT NULL,
    latitude NUMERIC(9,6),
    longitude NUMERIC(9,6),
    category TEXT NOT NULL,
    commodity TEXT NOT NULL,
    commodity_id INTEGER NOT NULL,
    unit TEXT,
    priceflag TEXT NOT NULL,
    pricetype TEXT NOT NULL,
    currency CHAR(3) NOT NULL,
    price NUMERIC(14,4) NOT NULL,
    usdprice NUMERIC(14,4),
    source_dataset TEXT NOT NULL,
    source_url TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT uq_stg_food_prices_natural_key UNIQUE (country_iso3, market_id, commodity_id, price_date, pricetype)
);

CREATE INDEX idx_stg_food_prices_country_date ON staging.stg_food_prices (country_iso3, price_date);
CREATE INDEX idx_stg_food_prices_commodity ON staging.stg_food_prices (commodity_id);

