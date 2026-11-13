"""Worker lifecycle shared by the standalone worker (`python -m app.worker`) and the
embedded mode (API process, RUN_EMBEDDED_WORKER=true, for single-process development)."""
import logging
import threading

from app.core.config import settings
from app.workers.jobs import run_cycle

logger = logging.getLogger(__name__)


class WorkerRunner:
    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self.mqtt = None

    def start(self):
        if settings.MQTT_ENABLED:
            from app.workers.mqtt_ingestor import ingestor
            self.mqtt = ingestor
            try:
                ingestor.start()
            except Exception as exc:
                logger.error("MQTT ingestor failed to start: %s", exc)
        if settings.SIMULATION_ENABLED:
            from app.services.simulation import engine
            engine.start()
        self._thread = threading.Thread(target=self._loop, name="coldguard-scheduler", daemon=True)
        self._thread.start()
        logger.info("Background worker started (tick=%ss, mqtt=%s)", settings.WORKER_TICK_SECONDS, settings.MQTT_ENABLED)

    def _loop(self):
        tick = 0
        while not self._stop.is_set():
            run_cycle(tick)
            tick += 1
            self._stop.wait(settings.WORKER_TICK_SECONDS)

    def stop(self):
        self._stop.set()
        if self.mqtt:
            self.mqtt.stop()
        if settings.SIMULATION_ENABLED:
            from app.services.simulation import engine
            engine.stop()

    def join(self):
        while self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)


runner = WorkerRunner()
