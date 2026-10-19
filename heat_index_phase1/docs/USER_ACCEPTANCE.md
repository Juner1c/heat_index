# ThermoCast user acceptance checklist

Record the tester, date, dataset filename, artifact version, result, and notes for every item.

## Data monitoring

- The dashboard opens without an API error and identifies the expected CSV.
- Record count and date coverage agree with an independent CSV inspection.
- A deliberately omitted hour increases the missing-hour count.
- A duplicated timestamp and a blank cell appear in the quality warnings.
- Configured collection dates produce the expected download-completion percentage.
- Recognized Himawari bands appear in the spectral-band selector and chart.

## Locations and observations

- Every station/location in the CSV appears once in the selector.
- Selecting a station changes records, charts, forecasts, and alerts to that station only.
- Coordinates and row counts agree with the selected station's source rows.
- Temperature, humidity, and heat-index time series use correct units and timestamps.

## Forecasting and evaluation

- The model-status response rejects an incomplete or incompatible artifact.
- A validated artifact enables the LNN option and displays prediction timestamps.
- The baseline remains selectable for comparison.
- Train, validation, and test ranges are chronological and non-overlapping.
- Independently recalculated test MAE and RMSE match the displayed values within rounding tolerance.
- The downloaded report contains dataset, quality, model, and evaluation sections.

## Alerts and failures

- Values at 27, 33, 42, and 52 °C enter caution, extreme caution, danger, and extreme danger respectively.
- Alert timestamps and values match the selected model forecast.
- Missing CSV, unknown station, insufficient history, and invalid horizon produce readable errors.
- The interface never labels the persistence baseline as an LNN forecast.

## Sign-off

Acceptance requires all items to pass on the actual Mariveles dataset and the final trained artifact. Attach the downloaded validation report and screenshots of each dashboard tab to the capstone testing record.
