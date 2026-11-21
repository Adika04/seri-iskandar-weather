# ESP32 Rain Alert (simulated hardware, Wokwi)

A standalone rain-alert module for Seri Iskandar, Perak. An ESP32 polls the
Open-Meteo API over Wi-Fi and warns when rain is imminent. It runs in the
[Wokwi](https://wokwi.com/) simulator, so it costs RM 0.00. It does **not** read
from or write to the Turso database, so it cannot affect the data collector.

**Live simulation:** https://wokwi.com/projects/481261368019490817

## Files
| File | Purpose |
|---|---|
| `rain_alert.ino` | ESP32 sketch (Wi-Fi, API request, alert logic) |
| `diagram.json` | Wokwi circuit: ESP32, red LED, resistor, buzzer |
| `libraries.txt` | Libraries required by the sketch in Wokwi |

## Alert logic
Every 30 seconds the ESP32 requests the next-hour precipitation probability
and expected rainfall (mm) for Seri Iskandar (4.35955 N, 100.97607 E, the same
coordinates as the collector). The alert is triggered when:

    rainProb >= 50  OR  rainMm > 0.1

When triggered, the red LED turns on and the buzzer sounds. Otherwise both are off.

## Wiring
| ESP32 pin | Connects to |
|---|---|
| GPIO 2 | 220 ohm resistor, then red LED, then GND |
| GPIO 4 | Active buzzer (+); buzzer (-) to GND |

## Run it
1. Open the Wokwi project link above.
2. Press the green **Start** button. The simulated ESP32 connects to the
   `Wokwi-GUEST` Wi-Fi network, which needs no password.
3. Watch the Serial Monitor for each reading and the red LED and buzzer for alerts.

## Estimated cost if built physically
ESP32 board (about RM 25), LED, 220 ohm resistor, active buzzer, breadboard and
jumper wires (about RM 10 to 17) gives roughly **RM 35 to 42**. These are
estimates, not receipts.

## Notes
- Open-Meteo values are model-based estimates, not readings from a physical
  weather station.
- No API key or database token is needed.
- This module is a simulation. It has not been built on physical hardware.
