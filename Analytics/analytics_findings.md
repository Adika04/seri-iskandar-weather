
# IoT Weather Monitoring - Analytics Findings

## 1. Dataset Overview
- Data source: Open-Meteo API
- Location: Seri Iskandar, Perak
- Total hourly observation records: 75
- Data period: 18 November 2026, 15:00 to 21 November 2026, 20:00
- Weather parameters: Temperature, Humidity, Precipitation, Wind Speed

## 2. Data Quality
- Total expected hourly records: 78
- Actual records: 75
- Missing hourly records: 3
- Data coverage: 96.15%
- No duplicate timestamps were found.
- No missing parameter values were found in the analysed dataset.

## 3. Forecast Accuracy
| Parameter | MAE | RMSE | Samples |
|---|---:|---:|---:|
| Temperature | 0.557 | 0.842 | 75 |
| Humidity | 2.107 | 3.844 | 75 |
| Precipitation | 0.823 | 1.903 | 75 |
| Wind Speed | 2.459 | 3.125 | 75 |

Temperature recorded the lowest MAE, while wind speed recorded the highest MAE.

## 4. Analytics Outputs
- cleaned_weather_data.csv
- forecast_accuracy.csv
- temperature.png
- humidity.png
- precipitation.png
- wind_speed.png
- forecast_accuracy.png

## 5. Conclusion
The analytics process successfully cleaned and analysed 75 hourly weather observations.
Forecast accuracy was evaluated using Mean Absolute Error (MAE) and Root Mean Squared Error (RMSE).
The results can support the development of the interactive weather monitoring dashboard.
