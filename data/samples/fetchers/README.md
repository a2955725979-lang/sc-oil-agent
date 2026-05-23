# Fetcher Contract Samples

These files are test-only samples for the `raw_data_contract_v1` fetcher interface.

They are not real market data and must not be used for research, trading, or market judgment.

## Files

- `raw_pass.json`: valid raw_data records that can be converted to `daily_input`.
- `raw_warning_duplicate_field.json`: valid raw_data with a duplicate field that should produce a conversion warning.
- `raw_fail.json`: structured fetch failure that should not be treated as usable pipeline input.

These samples do not call AKShare, EIA, FRED, yfinance, or any external API.
