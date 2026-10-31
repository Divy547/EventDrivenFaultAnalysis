"""Configuration module for P_311 IoT Fault Diagnosis Assistant.

Loads settings from environment variables or .env file with production-ready
defaults for offline operation, MQTT brokers, thresholds, and AI models.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the repository
BASE_DIR = Path(__file__).resolve().parent

# Load .env file if it exists
load_dotenv(BASE_DIR / ".env")


@dataclass
class MQTTConfig:
    broker: str = field(
        default_factory=lambda: os.getenv("MQTT_BROKER", "test.mosquitto.org")
    )
    port: int = field(
        default_factory=lambda: int(os.getenv("MQTT_PORT", "1883"))
    )
    keepalive: int = field(
        default_factory=lambda: int(os.getenv("MQTT_KEEPALIVE", "60"))
    )
    client_id: str = field(
        default_factory=lambda: os.getenv("MQTT_CLIENT_ID", "p311_iot_assistant")
    )
    telemetry_topic: str = field(
        default_factory=lambda: os.getenv("MQTT_TELEMETRY_TOPIC", "p311/industrial/telemetry")
    )
    alerts_topic: str = field(
        default_factory=lambda: os.getenv("MQTT_ALERTS_TOPIC", "p311/industrial/alerts")
    )
    username: str | None = field(
        default_factory=lambda: os.getenv("MQTT_USERNAME") or None
    )
    password: str | None = field(
        default_factory=lambda: os.getenv("MQTT_PASSWORD") or None
    )
    enabled: bool = field(
        default_factory=lambda: os.getenv("MQTT_ENABLED", "true").lower() in ("true", "1", "yes")
    )
    fallback_if_unavailable: bool = field(
        default_factory=lambda: os.getenv("MQTT_USE_FALLBACK_IF_UNAVAILABLE", "true").lower() in ("true", "1", "yes")
    )


@dataclass
class DatabaseConfig:
    path: Path = field(
        default_factory=lambda: BASE_DIR / os.getenv("DB_PATH", "data/iot_fault_diagnosis.db")
    )


@dataclass
class FaultThresholds:
    deduplication_window_sec: float = field(
        default_factory=lambda: float(os.getenv("FAULT_DEDUPLICATION_WINDOW_SEC", "60.0"))
    )
    temp_warning: float = field(
        default_factory=lambda: float(os.getenv("TEMP_WARNING_THRESHOLD", "75.0"))
    )
    temp_critical: float = field(
        default_factory=lambda: float(os.getenv("TEMP_CRITICAL_THRESHOLD", "90.0"))
    )
    vibration_warning: float = field(
        default_factory=lambda: float(os.getenv("VIBRATION_WARNING_THRESHOLD", "4.5"))
    )
    vibration_critical: float = field(
        default_factory=lambda: float(os.getenv("VIBRATION_CRITICAL_THRESHOLD", "7.1"))
    )
    voltage_low_warning: float = field(
        default_factory=lambda: float(os.getenv("VOLTAGE_LOW_WARNING", "207.0"))
    )
    voltage_low_critical: float = field(
        default_factory=lambda: float(os.getenv("VOLTAGE_LOW_CRITICAL", "195.0"))
    )
    acoustic_warning: float = field(
        default_factory=lambda: float(os.getenv("ACOUSTIC_WARNING_THRESHOLD", "85.0"))
    )
    acoustic_critical: float = field(
        default_factory=lambda: float(os.getenv("ACOUSTIC_CRITICAL_THRESHOLD", "95.0"))
    )


@dataclass
class SimulatorConfig:
    interval_sec: float = field(
        default_factory=lambda: float(os.getenv("SIMULATOR_INTERVAL_SEC", "2.0"))
    )
    auto_start: bool = field(
        default_factory=lambda: os.getenv("SIMULATOR_AUTO_START", "false").lower() in ("true", "1", "yes")
    )


@dataclass
class AIConfig:
    api_key: str | None = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY") or None
    )
    model: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    )

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key and self.api_key.strip())


@dataclass
class AppConfig:
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    manuals_dir: Path = BASE_DIR / "data" / "manuals"
    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    thresholds: FaultThresholds = field(default_factory=FaultThresholds)
    simulator: SimulatorConfig = field(default_factory=SimulatorConfig)
    ai: AIConfig = field(default_factory=AIConfig)

    def ensure_directories(self) -> None:
        """Create necessary directories if they do not exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.manuals_dir.mkdir(parents=True, exist_ok=True)
        self.db.path.parent.mkdir(parents=True, exist_ok=True)


# Global singleton configuration
settings = AppConfig()
settings.ensure_directories()
