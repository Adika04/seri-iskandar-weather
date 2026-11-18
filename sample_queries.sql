-- Check latest current-condition records
SELECT * FROM weather_observations
ORDER BY observed_at DESC
LIMIT 10;

-- Count collected observations
SELECT COUNT(*) AS observation_count
FROM weather_observations;

-- Count forecast snapshots
SELECT COUNT(*) AS forecast_count
FROM weather_forecasts;

-- View forecasts retrieved most recently
SELECT *
FROM weather_forecasts
ORDER BY forecast_retrieved_at DESC, forecast_for ASC
LIMIT 20;
