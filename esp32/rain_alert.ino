#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* ssid = "Wokwi-GUEST";
const char* password = "";

// Coordinates for Seri Iskandar, Perak (matched with config.py)
const String apiUrl = "https://api.open-meteo.com/v1/forecast?latitude=4.35955&longitude=100.97607&current=temperature_2m,precipitation&hourly=precipitation_probability,precipitation&forecast_days=1&timezone=Asia%2FKuala_Lumpur";

const int LED_PIN = 2;
const int BUZZER_PIN = 4;

// Alert thresholds
const int RAIN_PROB_THRESHOLD = 50;     // Percentage (%)
const float RAIN_MM_THRESHOLD = 0.1;    // Millimeters (mm)

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  Serial.print("Connecting to WiFi");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected Successfully!");
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(apiUrl);
    int httpCode = http.GET();

    if (httpCode > 0) {
      String payload = http.getString();
      JsonDocument doc;
      DeserializationError error = deserializeJson(doc, payload);

      if (!error) {
        String currentTime = doc["current"]["time"].as<String>();
        JsonArray times = doc["hourly"]["time"];
        JsonArray probs = doc["hourly"]["precipitation_probability"];
        JsonArray precips = doc["hourly"]["precipitation"];

        // Find the index of the next forecast hour strictly after current time
        int nextHourIndex = 0;
        for (int i = 0; i < times.size(); i++) {
          if (times[i].as<String>() > currentTime) {
            nextHourIndex = i;
            break;
          }
        }

        String nextHour = times[nextHourIndex].as<String>();
        int rainProb = probs[nextHourIndex];
        float rainMm = precips[nextHourIndex];

        Serial.print("Current Time: ");
        Serial.print(currentTime);
        Serial.print(" | Next Hour Forecast (");
        Serial.print(nextHour);
        Serial.print("): ");
        Serial.print(rainProb);
        Serial.print("% | ");
        Serial.print(rainMm);
        Serial.println(" mm");

        // Trigger visual and audio alert if upcoming rain exceeds threshold
        if (rainProb >= RAIN_PROB_THRESHOLD || rainMm > RAIN_MM_THRESHOLD) {
          Serial.println("ALERT: Imminent rain forecasted! Activating LED and buzzer...");
          digitalWrite(LED_PIN, HIGH);
          tone(BUZZER_PIN, 1000);
        } else {
          Serial.println("Status: Clear weather / No rain alert.");
          digitalWrite(LED_PIN, LOW);
          noTone(BUZZER_PIN);
        }
      } else {
        Serial.println("Error: Failed to parse JSON response.");
      }
    } else {
      Serial.print("HTTP Request Error: ");
      Serial.println(httpCode);
    }
    http.end();
  } else {
    Serial.println("Error: WiFi disconnected.");
  }

  // Poll API every 30 seconds for demonstration purposes
  delay(30000);
}
