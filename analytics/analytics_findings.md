
# IoT Weather Monitoring - Analytics Findings

## 1. Dataset Overview

The weather dataset contains 70 actual weather observation records
collected from 17 November 2026 to 20 November 2026 in Seri Iskandar,
Perak.

The cleaned dataset contains five columns:
- Datetime
- Temperature (°C)
- Humidity (%)
- Precipitation (mm)
- Wind Speed (km/h)

Three hourly timestamps were missing:
- 19 November 2026, 00:00
- 19 November 2026, 12:00
- 19 November 2026, 21:00

Therefore, the dataset covers the intended time period but does not
represent fully uninterrupted hourly observations.

## 2. Weather Data Visualization

Four graphs were generated to visualize changes in:
- Temperature
- Humidity
- Precipitation
- Wind Speed

These visualizations help identify weather patterns and changes
throughout the observation period.

## 3. Forecast Accuracy Evaluation

A total of 253 forecast records were retrieved from the database.
After matching forecast values with actual observations and selecting
the latest forecast available before each observation, 31 matched
records were used for evaluation.

The evaluation used Mean Absolute Error (MAE) and
Root Mean Squared Error (RMSE).

| Parameter | MAE | RMSE | Samples |
|---|---:|---:|---:|
| Temperature (°C) | 0.465 | 0.674 | 31 |
| Humidity (%) | 1.613 | 2.489 | 31 |
| Precipitation (mm) | 1.171 | 2.496 | 31 |
| Wind Speed (km/h) | 2.255 | 2.691 | 31 |

## 4. Findings

Temperature recorded the lowest MAE of 0.465°C, indicating the
smallest average absolute forecast error among the four parameters.

Wind speed recorded the highest MAE of 2.255 km/h.

The results show that forecast errors vary across weather parameters.
These results are based on 31 matched records and should be interpreted
within that sample.

## 5. Limitations

- Three hourly observation timestamps were missing.
- Only 31 actual observations had eligible matching forecast records.
- Forecast lead times varied because the latest available forecast
  before each observation was selected.
- The accuracy results therefore do not represent a single fixed
  forecast horizon.

## 6. Conclusion

The analytics process successfully produced a cleaned weather dataset,
four weather visualization graphs, and forecast accuracy measurements
using MAE and RMSE.

Further data collection and evaluation using a fixed forecast horizon
would improve the reliability and depth of the analysis.
