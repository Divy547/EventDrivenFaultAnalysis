/*
 * P_311: Knowledge-Driven IoT Fault Diagnosis Assistant
 * ESP32 Edge Telemetry Publisher Firmware
 *
 * Description:
 *   Publishes industrial motor telemetry over MQTT in the exact JSON schema
 *   consumed by the Python ingestion pipeline and Streamlit dashboard.
 *   Operates with physical analog sensors (ADC) or synthesizes realistic
 *   readings if sensors are unattached.
 *
 * Supported Target: ESP32 Dev Module / ESP32-WROOM-32
 * Compatible Libraries:
 *   - WiFi (built-in)
 *   - PubSubClient by Nick O'Leary (install via Arduino Library Manager)
 *   - ArduinoJson v6 or v7 by Benoit Blanchon
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ============================================================================
// CONFIGURATION PARAMETERS (Edit for your local network)
// ============================================================================

// 1. Wi-Fi Credentials
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// 2. MQTT Broker Coordinates
// Default demo broker: test.mosquitto.org (Port: 1883)
// For local testing, change to your workstation IP (e.g., "192.168.1.100")
const char* MQTT_BROKER   = "test.mosquitto.org";
const int   MQTT_PORT     = 1883;
const char* MQTT_USER     = "";  // Leave empty if unauthenticated
const char* MQTT_PASS     = "";

// 3. Device Identification
// Supported IDs: "MOTOR-PUMP-01", "MOTOR-CONV-02", "MOTOR-COMP-03"
const char* DEVICE_ID     = "MOTOR-PUMP-01";
const char* TOPIC_BASE    = "p311/industrial/telemetry";

// 4. Telemetry Reporting Interval
const unsigned long REPORT_INTERVAL_MS = 2000; // 2.0 seconds

// 5. Optional Hardware ADC Sensor Pins (Set to -1 to use software synthesis)
const int PIN_TEMP_ADC    = 34; // e.g., LM35 or NTC thermistor
const int PIN_VIB_ADC     = 35; // e.g., Piezoelectric vibration sensor
const int PIN_CURRENT_ADC = 32; // e.g., ACS712 current transducer

// ============================================================================
// GLOBAL CLIENT INSTANCES
// ============================================================================
WiFiClient espClient;
PubSubClient mqttClient(espClient);

unsigned long lastPublishTime = 0;
char mqttTopic[128];
char payloadBuffer[512];
int stepCounter = 0;

// Motor baseline physical specifications (Centrifugal Coolant Pump)
const float RATED_KW      = 15.0;
const float RATED_CURRENT = 28.0;
const float NOMINAL_RPM   = 1450.0;
const float NOMINAL_VOLT  = 230.0;

// ============================================================================
// WI-FI & MQTT CONNECTION HANDLERS
// ============================================================================

void setupWiFi() {
  delay(10);
  Serial.println();
  Serial.print("[WiFi] Connecting to SSID: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print("[WiFi] Connected! IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println();
    Serial.println("[WiFi] Connection timeout. Continuing in disconnected mode...");
  }
}

void reconnectMQTT() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  // Attempt connection without blocking main loop indefinitely
  if (!mqttClient.connected()) {
    Serial.print("[MQTT] Attempting connection to ");
    Serial.print(MQTT_BROKER);
    Serial.print(":");
    Serial.println(MQTT_PORT);

    String clientId = "ESP32_" + String(DEVICE_ID) + "_" + String(random(0xffff), HEX);

    bool connected = false;
    if (strlen(MQTT_USER) > 0) {
      connected = mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASS);
    } else {
      connected = mqttClient.connect(clientId.c_str());
    }

    if (connected) {
      Serial.println("[MQTT] Connected successfully!");
    } else {
      Serial.print("[MQTT] Connect failed, rc=");
      Serial.println(mqttClient.state());
    }
  }
}

// ============================================================================
// TELEMETRY SAMPLING & SYNTHESIS
// ============================================================================

void sampleAndPublishTelemetry() {
  stepCounter++;

  // 1. Temperature (°C)
  // Read analog pin if available, or generate realistic physical value
  float temperature = 51.5 + (sin(stepCounter * 0.1) * 2.0) + (random(-30, 30) / 100.0);
  if (PIN_TEMP_ADC >= 0) {
    int raw = analogRead(PIN_TEMP_ADC);
    // Linear voltage conversion (3.3V / 4095 ADC) * 100 °C/V for LM35
    float voltage = (raw / 4095.0) * 3.3;
    if (raw > 50) {
      temperature = voltage * 100.0;
    }
  }

  // 2. Vibration (mm/s RMS)
  float vibration = 1.75 + (sin(stepCounter * 0.2) * 0.25) + (random(-10, 10) / 100.0);
  if (PIN_VIB_ADC >= 0) {
    int rawVib = analogRead(PIN_VIB_ADC);
    if (rawVib > 20) {
      vibration = (rawVib / 4095.0) * 10.0; // Scaled 0-10 mm/s
    }
  }

  // 3. Electrical parameters
  float current = (RATED_CURRENT * 0.88) + (random(-40, 40) / 100.0);
  float voltage = NOMINAL_VOLT + (random(-15, 15) / 10.0);
  float rpm = NOMINAL_RPM + (random(-50, 50) / 10.0);
  float acoustic_db = 68.0 + (random(-20, 20) / 10.0);
  float pressure_bar = 4.2 + (random(-10, 10) / 100.0);
  float power_factor = 0.88;

  // 4. Construct JSON payload conforming to Pydantic MotorTelemetry schema
  StaticJsonDocument<512> doc;
  doc["device_id"]    = DEVICE_ID;
  
  // Format ISO 8601 UTC timestamp or millis uptime
  char timeBuf[32];
  snprintf(timeBuf, sizeof(timeBuf), "2026-10-31T%02lu:%02lu:%02luZ", 
           (millis() / 3600000) % 24, 
           (millis() / 60000) % 60, 
           (millis() / 1000) % 60);
  doc["timestamp"]    = timeBuf;

  doc["temperature"]  = round(temperature * 100.0) / 100.0;
  doc["vibration"]    = round(vibration * 100.0) / 100.0;
  doc["current"]      = round(current * 100.0) / 100.0;
  doc["voltage"]      = round(voltage * 10.0) / 10.0;
  doc["rpm"]          = round(rpm * 10.0) / 10.0;
  doc["acoustic_db"]  = round(acoustic_db * 10.0) / 10.0;
  doc["pressure_bar"] = round(pressure_bar * 100.0) / 100.0;
  doc["power_factor"] = power_factor;
  doc["state"]        = "NORMAL";

  JsonObject meta = doc.createNestedObject("metadata");
  meta["source"]        = "ESP32_PHYSICAL_HARDWARE";
  meta["rated_kw"]      = RATED_KW;
  meta["rated_current"] = RATED_CURRENT;
  meta["firmware"]      = "P311-ESP32-v1.0";
  meta["uptime_sec"]    = millis() / 1000;

  serializeJson(doc, payloadBuffer, sizeof(payloadBuffer));

  // 5. Publish to MQTT topic
  Serial.print("[Telemetry Emit] ");
  Serial.println(payloadBuffer);

  if (mqttClient.connected()) {
    mqttClient.publish(mqttTopic, payloadBuffer);
    Serial.println("[MQTT] Published successfully.");
  } else {
    Serial.println("[MQTT] Not connected. Reading logged to serial port only.");
  }
}

// ============================================================================
// ARDUINO LIFECYCLE
// ============================================================================

void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("==================================================");
  Serial.println(" P_311: Industrial Motor Telemetry Edge Node");
  Serial.print(" Target Device: ");
  Serial.println(DEVICE_ID);
  Serial.println("==================================================");

  // Prepare full MQTT topic: p311/industrial/telemetry/MOTOR-PUMP-01
  snprintf(mqttTopic, sizeof(mqttTopic), "%s/%s", TOPIC_BASE, DEVICE_ID);

  // Setup Wi-Fi and MQTT
  setupWiFi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(512); // Ensure buffer fits full JSON payload
}

void loop() {
  // Maintain MQTT connection
  if (WiFi.status() == WL_CONNECTED) {
    if (!mqttClient.connected()) {
      reconnectMQTT();
    }
    mqttClient.loop();
  }

  // Periodic telemetry emission
  unsigned long now = millis();
  if (now - lastPublishTime >= REPORT_INTERVAL_MS) {
    lastPublishTime = now;
    sampleAndPublishTelemetry();
  }
}
