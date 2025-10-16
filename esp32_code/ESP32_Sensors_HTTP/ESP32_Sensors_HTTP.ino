/*
 * ESP32 DHT22 + MQ135 Sensor Data Logger
 * Sends sensor readings to FastAPI backend via HTTP POST
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

// ============================================
// CONFIGURATION (Edit these)
// ============================================

// WiFi credentials
const char* ssid = "ZDN5G";               // Your WiFi name
const char* password = "Basisth4@tech";   // Your WiFi password

// Backend API URL (use your PC's local IP from "ipconfig")
const char* serverUrl = "http://192.168.29.177:8000/sensor-data"; 
// Example: http://192.168.0.105:8000/sensor-data

// Sensor pins
#define DHTPIN 4
#define DHTTYPE DHT22
#define MQ135PIN 34

// ============================================
// GLOBAL VARIABLES
// ============================================
DHT dht(DHTPIN, DHTTYPE);
unsigned long lastTime = 0;
unsigned long timerDelay = 5000; // 5 seconds

// ============================================
// SETUP
// ============================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n========================================");
  Serial.println(" ESP32 IoT Sensor System - Starting...");
  Serial.println("========================================");

  // Initialize sensors
  dht.begin();
  pinMode(MQ135PIN, INPUT);

  Serial.println("✓ DHT22 and MQ135 initialized");

  // Connect to WiFi
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  Serial.print("Connecting to WiFi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 40) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✓ WiFi Connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n✗ WiFi Connection Failed! Check credentials or use 2.4GHz WiFi.");
  }

  Serial.print("Target Server: ");
  Serial.println(serverUrl);
  Serial.println("========================================\n");
}

// ============================================
// LOOP
// ============================================
void loop() {
  if ((millis() - lastTime) > timerDelay) {
    lastTime = millis();

    // Ensure WiFi connection
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("⚠ WiFi disconnected! Reconnecting...");
      WiFi.reconnect();
      delay(2000);
      return;
    }

    // Read sensors
    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();
    int mq135Raw = analogRead(MQ135PIN);
    float airQuality = (mq135Raw / 4095.0) * 100;

    if (isnan(temperature) || isnan(humidity)) {
      Serial.println("✗ Failed to read from DHT22 sensor!");
      return;
    }

    // Display readings
    Serial.println("\n┌──────────────────────────────────────┐");
    Serial.print("│ Temperature: "); Serial.print(temperature); Serial.println(" °C");
    Serial.print("│ Humidity:    "); Serial.print(humidity); Serial.println(" %");
    Serial.print("│ Air Quality: "); Serial.print(airQuality); Serial.println(" %");
    Serial.println("└──────────────────────────────────────┘");

    // Create JSON data
    StaticJsonDocument<256> jsonDoc;
    jsonDoc["device_id"] = "ESP32_001";
    jsonDoc["temperature"] = temperature;
    jsonDoc["humidity"] = humidity;
    jsonDoc["air_quality"] = airQuality;
    jsonDoc["air_quality_raw"] = mq135Raw;

    String payload;
    serializeJson(jsonDoc, payload);

    // Send data to backend
    Serial.println("\n🌐 Sending data to FastAPI backend...");
    Serial.println(payload);

  HTTPClient http;
  // Ensure we pass a String to http.begin to avoid overload ambiguity on some ESP cores
  http.begin(String(serverUrl));
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(8000);

    int httpCode = http.POST(payload);

    if (httpCode > 0) {
      Serial.print("📡 HTTP Response Code: ");
      Serial.println(httpCode);

      if (httpCode == 200) {
        String response = http.getString();
        Serial.println("✅ Data sent successfully!");
        Serial.print("Response: ");
        Serial.println(response);
      } else {
        Serial.println("⚠ Server returned non-200 code");
      }
    } else {
      Serial.print("❌ Connection failed, error: ");
      Serial.println(http.errorToString(httpCode));
      Serial.println("Possible causes:");
      Serial.println("1️⃣ Backend not running");
      Serial.println("2️⃣ Wrong IP in serverUrl");
      Serial.println("3️⃣ Firewall blocking Python");
      Serial.println("4️⃣ ESP32 and PC not on same WiFi");
    }

    http.end();
    Serial.println("──────────────────────────────────────\n");
  }
}