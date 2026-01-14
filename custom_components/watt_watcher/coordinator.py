"""Coordinator for Watt Watcher."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    CONF_POWER_SENSOR,
    CONF_STATES,
    CONF_STATE_NAME,
    CONF_THRESHOLD,
    CONF_COMPARISON,
    CONF_ICON,
    CONF_ACTIVE_DELAY,
    CONF_FINISHED_DELAY,
    CONF_IDLE_DELAY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_ACTIVE_DELAY,
    DEFAULT_FINISHED_DELAY,
    DEFAULT_IDLE_DELAY,
    COMPARISON_GREATER,
    COMPARISON_LESS,
)

_LOGGER = logging.getLogger(__name__)


FINISH_KEYWORDS = {"bitti", "bitmiş", "tamamlandı", "finish", "sonlandı", "bitiş", "ended", "done"}


class WattWatcherCoordinator(DataUpdateCoordinator):
    """Coordinator for Watt Watcher."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self.entry = entry
        self.config = dict(entry.data)

        # State tracking
        self.current_power = 0.0
        self.current_state = "idle"
        self.state_start_time = datetime.now()
        self.cycle_start_time = None

        # Timing tracking
        self.active_timer_start: datetime | None = None
        self.finished_timer_start: datetime | None = None
        self.bitti_start_time: datetime | None = None

        # Configuration
        self.scan_interval = self.config.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        self.active_delay = self.config.get(CONF_ACTIVE_DELAY, DEFAULT_ACTIVE_DELAY)
        self.finished_delay = self.config.get(CONF_FINISHED_DELAY, DEFAULT_FINISHED_DELAY)
        self.idle_delay = self.config.get(CONF_IDLE_DELAY, DEFAULT_IDLE_DELAY)

        # States configuration
        self.states_config = self.config.get(CONF_STATES, [])
        self.state_icons = {
            state[CONF_STATE_NAME]: state.get(CONF_ICON, "mdi:circle")
            for state in self.states_config
        }

        # Bitiş durumunu tespit et
        self.finish_state_name = self._detect_finish_state_name()
        self.has_finish_state = self.finish_state_name is not None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.scan_interval),
        )

    def _detect_finish_state_name(self) -> str | None:
        """Bitiş durumunun adını bulmaya çalış."""
        if not self.states_config:
            return None

        # 1. Son durum genellikle bitiş olur
        last_state = self.states_config[-1][CONF_STATE_NAME]
        if last_state.lower() in FINISH_KEYWORDS or "bit" in last_state.lower() or "end" in last_state.lower():
            return last_state

        # 2. İçerikte bitiş kelimeleri geçen herhangi bir durum
        for state in self.states_config:
            name = state[CONF_STATE_NAME].lower()
            if any(kw in name for kw in FINISH_KEYWORDS):
                return state[CONF_STATE_NAME]

        # Bulunamadı
        return None

    async def _async_update_data(self) -> Dict[str, Any]:
        if not self.last_update_success or self.data is None:
            _LOGGER.debug("İlk veri veya hata sonrası → idle varsayılıyor")
            default_data = self._create_idle_data()
            self.data = default_data
            return default_data

        try:
            power_entity = self.config[CONF_POWER_SENSOR]
            state = self.hass.states.get(power_entity)

            if state is None or state.state in ["unknown", "unavailable"]:
                _LOGGER.warning("Power sensor unavailable: %s", power_entity)
                return self._create_idle_data()

            power = float(state.state)
            self.current_power = power

            threshold_state = self._determine_state_by_thresholds(power)
            new_state = self._apply_delays(threshold_state, power)
            new_state = self._check_idle_delay(new_state)

            if new_state != self.current_state:
                self._on_state_change(new_state)

            is_active = self.current_state not in ["idle", self.finish_state_name or "unknown"]
            current_icon = self.state_icons.get(self.current_state, "mdi:circle")

            finish_duration = 0
            if self.current_state == self.finish_state_name and self.bitti_start_time:
                finish_duration = int((datetime.now() - self.bitti_start_time).total_seconds())

            data = {
                "current_power": self.current_power,
                "current_state": self.current_state,
                "current_icon": current_icon,
                "state_duration": self._get_state_duration(),
                "cycle_duration": self._get_cycle_duration(),
                "is_active": is_active,
                "bitti_duration": finish_duration,
                "idle_remaining": max(0, self.idle_delay - finish_duration)
                if self.current_state == self.finish_state_name
                else 0,
                "timing_settings": {
                    "active_delay": self.active_delay,
                    "finished_delay": self.finished_delay,
                    "idle_delay": self.idle_delay,
                },
                "states_config": self.states_config,
                "timers": {
                    "active_timer": self._get_timer_duration(self.active_timer_start),
                    "finished_timer": self._get_timer_duration(self.finished_timer_start),
                },
            }

            _LOGGER.debug(
                "Karar | güç=%.1f | threshold=%s | gecikme sonrası=%s | son=%s | finish süresi=%d",
                power, threshold_state, new_state, self.current_state, finish_duration
            )

            return data

        except (ValueError, AttributeError, TypeError) as err:
            _LOGGER.error("Güç verisi güncellenirken hata: %s", err)
            return self._create_idle_data()

    def _create_idle_data(self) -> Dict[str, Any]:
        return {
            "current_power": 0.0,
            "current_state": "idle",
            "current_icon": "mdi:power-off",
            "state_duration": 0,
            "cycle_duration": 0,
            "is_active": False,
            "bitti_duration": 0,
            "idle_remaining": 0,
            "timing_settings": {
                "active_delay": self.active_delay,
                "finished_delay": self.finished_delay,
                "idle_delay": self.idle_delay,
            },
            "states_config": self.states_config,
            "timers": {"active_timer": 0, "finished_timer": 0},
        }

    def _determine_state_by_thresholds(self, power: float) -> str:
        greater = [s for s in self.states_config if s[CONF_COMPARISON] == COMPARISON_GREATER]
        less = [s for s in self.states_config if s[CONF_COMPARISON] == COMPARISON_LESS]

        greater.sort(key=lambda x: x[CONF_THRESHOLD], reverse=True)
        less.sort(key=lambda x: x[CONF_THRESHOLD])

        for s in greater:
            if power > s[CONF_THRESHOLD]:
                return s[CONF_STATE_NAME]

        for s in less:
            if power < s[CONF_THRESHOLD]:
                return s[CONF_STATE_NAME]

        if power < 1.0 and not self.has_finish_state:
            return "idle"

        return "unknown"

    def _apply_delays(self, threshold_state: str, power: float) -> str:
        current = self.current_state

        # idle → aktif
        if current == "idle":
            if threshold_state not in ["idle", "unknown"]:
                if self.active_timer_start is None:
                    self.active_timer_start = datetime.now()
                if (datetime.now() - self.active_timer_start).total_seconds() >= self.active_delay:
                    self.active_timer_start = None
                    return threshold_state
                return "idle"
            self.active_timer_start = None
            return "idle"

        # aktif durumdayken
        if current not in ["idle", self.finish_state_name or "unknown"]:

            # finish durumuna geçiş?
            if self.has_finish_state and threshold_state == self.finish_state_name:
                if self.finished_timer_start is None:
                    self.finished_timer_start = datetime.now()
                if (datetime.now() - self.finished_timer_start).total_seconds() >= self.finished_delay:
                    self.finished_timer_start = None
                    self.bitti_start_time = datetime.now()
                    return self.finish_state_name
                return current

            # finish yoksa veya threshold finish değilse düşük güç kontrolü
            if not self.has_finish_state and power < 2.0:
                if self.finished_timer_start is None:
                    self.finished_timer_start = datetime.now()
                if (datetime.now() - self.finished_timer_start).total_seconds() >= self.finished_delay:
                    self.finished_timer_start = None
                    return "idle"
                return current

            self.finished_timer_start = None
            return threshold_state if threshold_state != "unknown" else current

        return threshold_state if threshold_state != "unknown" else current

    def _check_idle_delay(self, proposed_state: str) -> str:
        if self.current_state == self.finish_state_name:
            if self.bitti_start_time is None:
                self.bitti_start_time = datetime.now()
                _LOGGER.warning("finish timer sıfırlandı - düzeltildi")

            duration = (datetime.now() - self.bitti_start_time).total_seconds()
            remaining = max(0, self.idle_delay - duration)

            _LOGGER.debug(
                "finish durumu | geçti: %.0fs | kalan: %.0fs / limit: %ds",
                duration, remaining, self.idle_delay
            )

            if duration >= self.idle_delay:
                _LOGGER.info("idle_delay doldu → idle'a geçiliyor")
                self.bitti_start_time = None
                self.finished_timer_start = None
                self.active_timer_start = None
                return "idle"

            return self.finish_state_name  # süre dolmadı → finish'te kal

        if proposed_state != self.finish_state_name:
            self.bitti_start_time = None

        return proposed_state

    def _on_state_change(self, new_state: str) -> None:
        old = self.current_state
        self.current_state = new_state
        self.state_start_time = datetime.now()

        _LOGGER.info("Durum değişti: %s → %s (güç: %.1fW)", old, new_state, self.current_power)

        if old == "idle" and new_state not in ["idle", self.finish_state_name or "unknown"]:
            self.cycle_start_time = datetime.now()
            _LOGGER.info("Döngü başladı")
        elif old not in ["idle", self.finish_state_name or "unknown"] and new_state in ["idle", self.finish_state_name]:
            if self.cycle_start_time:
                dur = (datetime.now() - self.cycle_start_time).total_seconds()
                _LOGGER.info("Döngü bitti. Süre: %.0f sn", dur)
                self.cycle_start_time = None

        if new_state == self.finish_state_name:
            _LOGGER.info("Bitiş durumu algılandı. %d sn sonra idle olacak", self.idle_delay)

    def _get_state_duration(self) -> int:
        return int((datetime.now() - self.state_start_time).total_seconds())

    def _get_cycle_duration(self) -> int:
        if self.cycle_start_time and self.current_state not in ["idle", self.finish_state_name or "unknown"]:
            return int((datetime.now() - self.cycle_start_time).total_seconds())
        return 0

    def _get_timer_duration(self, timer_start: datetime | None) -> int:
        if timer_start:
            return int((datetime.now() - timer_start).total_seconds())
        return 0
