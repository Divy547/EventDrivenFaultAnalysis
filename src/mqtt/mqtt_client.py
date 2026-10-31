"""Resilient MQTT client with automatic reconnection and seamless local fallback mode.

Supports Paho MQTT v2/v1 APIs, handles network timeouts and unreachable brokers,
and automatically routes telemetry through a local event dispatcher when MQTT is unavailable.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Any, Callable, Optional

import paho.mqtt.client as mqtt
from config import MQTTConfig, settings
from src.database.db_manager import DatabaseManager
from src.fault_detection.detector import FaultDetector
from src.models.telemetry import FaultEvent, MotorTelemetry

logger = logging.getLogger(__name__)


class MQTTManager:
    """Manages MQTT connection lifecycle, telemetry ingestion, and local fallback queue."""

    def __init__(
        self,
        config: Optional[MQTTConfig] = None,
        db_manager: Optional[DatabaseManager] = None,
        fault_detector: Optional[FaultDetector] = None,
        on_telemetry_callback: Optional[Callable[[MotorTelemetry, list[FaultEvent]], None]] = None
    ) -> None:
        self.config = config or settings.mqtt
        self.db = db_manager or DatabaseManager()
        self.detector = fault_detector or FaultDetector(db_manager=self.db)
        self.on_telemetry = on_telemetry_callback

        self._client: Optional[mqtt.Client] = None
        self._is_connected = False
        self._fallback_mode = not self.config.enabled
        self._connection_state = "INITIALIZING"
        self._last_error = ""

        # Local fallback queue & worker thread
        self._fallback_queue: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=5000)
        self._running = False
        self._fallback_worker_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Telemetry ingestion counter
        self.ingested_count = 0
        self.fault_trigger_count = 0

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def is_fallback_mode(self) -> bool:
        return self._fallback_mode

    @property
    def connection_state(self) -> str:
        return self._connection_state

    @property
    def last_error(self) -> str:
        return self._last_error

    def start(self) -> None:
        """Start the ingestion subsystem and attempt MQTT connection."""
        self._running = True

        # Always start fallback processing thread so messages can be ingested immediately
        if self._fallback_worker_thread is None or not self._fallback_worker_thread.is_alive():
            self._fallback_worker_thread = threading.Thread(
                target=self._process_fallback_queue,
                daemon=True,
                name="FallbackIngestionWorker"
            )
            self._fallback_worker_thread.start()

        if self.config.enabled:
            self._connect_mqtt_async()
        else:
            self._fallback_mode = True
            self._connection_state = "LOCAL_FALLBACK_MODE"

    def stop(self) -> None:
        """Stop MQTT client and fallback processing."""
        self._running = False
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception as exc:
                logger.warning("Error disconnecting MQTT client: %s", exc)
        self._is_connected = False
        self._connection_state = "STOPPED"

    def _connect_mqtt_async(self) -> None:
        """Attempt non-blocking connection to the configured MQTT broker."""
        self._connection_state = "CONNECTING"
        thread = threading.Thread(target=self._init_and_connect_client, daemon=True, name="MQTTConnectThread")
        thread.start()

    def _init_and_connect_client(self) -> None:
        """Initialize Paho client and connect with timeout handling."""
        try:
            # Use CallbackAPIVersion.VERSION2 if supported by Paho
            if hasattr(mqtt, "CallbackAPIVersion"):
                client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id=f"{self.config.client_id}_{int(time.time())}",
                )
            else:
                client = mqtt.Client(client_id=f"{self.config.client_id}_{int(time.time())}")

            if self.config.username and self.config.password:
                client.username_pw_set(self.config.username, self.config.password)

            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message
            client.reconnect_delay_set(min_delay=2, max_delay=30)

            self._client = client
            logger.info("Connecting to MQTT broker at %s:%d ...", self.config.broker, self.config.port)

            # Connect with short timeout
            client.connect_async(self.config.broker, self.config.port, keepalive=self.config.keepalive)
            client.loop_start()

            # Wait briefly to confirm connection or fallback
            wait_seconds = 4.0
            start_wait = time.time()
            while time.time() - start_wait < wait_seconds:
                if self._is_connected:
                    return
                time.sleep(0.2)

            if not self._is_connected and self.config.fallback_if_unavailable:
                logger.warning(
                    "MQTT Broker (%s:%d) not responding within %.1fs. Activating Local Fallback Mode.",
                    self.config.broker, self.config.port, wait_seconds
                )
                self._fallback_mode = True
                self._connection_state = "LOCAL_FALLBACK (Broker unreachable)"
                self._last_error = f"Connection to {self.config.broker}:{self.config.port} timed out"

        except Exception as exc:
            self._last_error = str(exc)
            logger.error("Failed to connect to MQTT broker: %s", exc)
            if self.config.fallback_if_unavailable:
                self._fallback_mode = True
                self._connection_state = f"LOCAL_FALLBACK ({type(exc).__name__})"
            else:
                self._connection_state = "FAILED"

    def reconnect(self, new_broker: Optional[str] = None, new_port: Optional[int] = None) -> None:
        """Manually trigger reconnection, optionally updating broker coordinates."""
        if new_broker:
            self.config.broker = new_broker
        if new_port:
            self.config.port = new_port
        self.stop()
        self.start()

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, properties: Any = None) -> None:
        # rc in Paho 2.x is a ReasonCode object; in 1.x it is an integer 0
        is_success = (rc == 0) or (hasattr(rc, "is_failure") and not rc.is_failure)
        if is_success:
            self._is_connected = True
            self._fallback_mode = False
            self._connection_state = "CONNECTED"
            self._last_error = ""
            logger.info("Successfully connected to MQTT broker %s:%d", self.config.broker, self.config.port)

            # Subscribe to telemetry topic
            client.subscribe(f"{self.config.telemetry_topic}/#", qos=1)
            logger.info("Subscribed to topic: %s/#", self.config.telemetry_topic)
        else:
            self._is_connected = False
            self._connection_state = f"CONNECT_FAILED (rc={rc})"
            self._last_error = f"Connection rejected with return code {rc}"
            if self.config.fallback_if_unavailable:
                self._fallback_mode = True

    def _on_disconnect(self, client: Any, userdata: Any, flags_or_rc: Any, rc: Any = None, properties: Any = None) -> None:
        self._is_connected = False
        self._connection_state = "DISCONNECTED (Auto-reconnecting)"
        logger.warning("Disconnected from MQTT broker. Paho will attempt auto-reconnect.")
        if self.config.fallback_if_unavailable:
            self._fallback_mode = True

    def _on_message(self, client: Any, userdata: Any, message: Any) -> None:
        """Ingest incoming telemetry payload from MQTT message."""
        try:
            payload_str = message.payload.decode("utf-8")
            self._ingest_payload(payload_str)
        except Exception as exc:
            logger.error("Error processing incoming MQTT message: %s", exc)

    def publish_telemetry(self, telemetry: MotorTelemetry) -> bool:
        """Publish telemetry to MQTT broker if connected, or route to fallback queue."""
        payload_str = telemetry.to_json_str()
        topic = f"{self.config.telemetry_topic}/{telemetry.device_id}"

        if self._is_connected and self._client:
            try:
                res = self._client.publish(topic, payload_str, qos=0)
                # Also directly process for low-latency local dashboard responsiveness
                self._ingest_payload(payload_str)
                return res.rc == mqtt.MQTT_ERR_SUCCESS
            except Exception as exc:
                logger.warning("MQTT publish failed (%s). Falling back to local ingestion.", exc)
                self._fallback_queue.put((topic, payload_str))
                return False
        else:
            # Fallback mode: route through local queue
            try:
                self._fallback_queue.put_nowait((topic, payload_str))
                return True
            except queue.Full:
                logger.warning("Fallback ingestion queue full. Dropping packet.")
                return False

    def _process_fallback_queue(self) -> None:
        """Background worker consuming messages from local fallback queue."""
        while self._running:
            try:
                topic, payload_str = self._fallback_queue.get(timeout=0.5)
                self._ingest_payload(payload_str)
                self._fallback_queue.task_done()
            except queue.Empty:
                continue
            except Exception as exc:
                logger.error("Error in fallback queue processing: %s", exc)

    def _ingest_payload(self, payload_str: str) -> Optional[MotorTelemetry]:
        """Validate telemetry, run fault detection, and persist to SQLite."""
        try:
            # 1. Validation
            telemetry = MotorTelemetry.from_raw_json(payload_str)

            # 2. Fault Detection & Deduplication
            state, faults = self.detector.analyze_telemetry(telemetry)

            # 3. Persistence
            self.db.insert_telemetry(telemetry)

            self.ingested_count += 1
            if faults:
                self.fault_trigger_count += len(faults)

            # 4. Notify UI callback
            if self.on_telemetry:
                try:
                    self.on_telemetry(telemetry, faults)
                except Exception as exc:
                    logger.error("Error invoking on_telemetry callback: %s", exc)

            return telemetry
        except Exception as exc:
            logger.error("Telemetry ingestion validation error: %s", exc)
            return None
