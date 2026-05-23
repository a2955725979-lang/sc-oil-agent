# Validation Samples

These files are test-only validation samples for the local MVP pipeline.

They are not real market data and must not be used for research, trading, or market judgment.

## Files

- `pass_dictionary.yaml` and `pass_input.json`: stable pass sample covering the local spread calculation chain.
- `warning_dictionary.yaml` and `warning_input.json`: stable warning sample with one controlled metadata warning.
- `fail_dictionary.yaml` and `fail_input.json`: stable fail sample with a missing required field.

The samples are intentionally independent from `config/data_dictionary.yaml` so validation tests remain stable while the production dictionary evolves.
