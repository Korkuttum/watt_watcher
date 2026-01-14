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
        self.finish_start_time: datetime | None = None  # bitiş (finish) başlangıç zamanı
        
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
        
        # YENİ: Start ve finish her zaman listenin ilk ve son elemanı
        if self.states_config:
            self.start_state_name = self.states_config[0][CONF_STATE_NAME]
            self.finish_state_name = self.states_config[-1][CONF_STATE_NAME]
        else:
            self.start_state_name = "çalışıyor"
            self.finish_state_name = "bitti"
        
        _LOGGER.info("Coordinator başlatıldı | start_state=%s | finish_state=%s | idle_delay=%d sn",
                     self.start_state_name, self.finish_state_name, self.idle_delay)
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.scan_interval),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from power sensor and update states."""
        # İlk çalıştırma veya hata durumunda idle dön
        if not self.last_update_success or self.data is None:
            _LOGGER.debug("İlk veri veya hata → idle varsayılıyor")
            return self._create_idle_data()

        try:
            power_entity = self.config[CONF_POWER_SENSOR]
            state = self.hass.states.get(power_entity)
            
            if state is None or state.state in ["unknown", "unavailable"]:
                _LOGGER.warning("Power sensor unavailable: %s", power_entity)
                return self._create_idle_data()
            
            power = float(state.state)
            self.current_power = power
            
            # 1. Ham threshold state belirle
            threshold_state = self._determine_state_by_thresholds(power)
            
            # 2. Delay'leri uygula
            new_state = self._apply_delays(threshold_state, power)
            
            # 3. En son idle delay kontrolü (en kritik kısım)
            new_state = self._check_idle_delay(new_state)
            
            if new_state != self.current_state:
                self._on_state_change(new_state)
            
            is_active = self.current_state not in ["idle", self.finish_state_name]
            current_icon = self.state_icons.get(self.current_state, "mdi:circle")
            
            finish_duration = 0
            if self.current_state == self.finish_state_name and self.finish_start_time:
                finish_duration = int((datetime.now() - self.finish_start_time).total_seconds())
            
            data = {
                "current_power": self.current_power,
                "current_state": self.current_state,
                "current_icon": current_icon,
                "state_duration": self._get_state_duration(),
                "cycle_duration": self._get_cycle_duration(),
                "is_active": is_active,
                "bitti_duration": finish_duration,
                "idle_remaining": max(0, self.idle_delay - finish_duration) if self.current_state == self.finish_state_name else 0,
                "timing_settings": {
                    "active_delay": self.active_delay,
                    "finished_delay": self.finished_delay,
                    "idle_delay": self.idle_delay,
                },
                "states_config": self.states_config,
                "timers": {
                    "active_timer": self._get_timer_duration(self.active_timer_start),
                    "finished_timer": self._get_timer_duration(self.finished_timer_start),
                }
            }
            
            _LOGGER.debug(
                "UPDATE | güç=%.1f | threshold=%s | gecikme sonrası=%s | final=%s | finish_süre=%d sn",
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
        greater_states = [s for s in self.states_config if s[CONF_COMPARISON] == COMPARISON_GREATER]
        less_states = [s for s in self.states_config if s[CONF_COMPARISON] == COMPARISON_LESS]
        
        greater_states.sort(key=lambda x: x[CONF_THRESHOLD], reverse=True)
        less_states.sort(key=lambda x: x[CONF_THRESHOLD])
        
        for state in greater_states:
            if power > state[CONF_THRESHOLD]:
                return state[CONF_STATE_NAME]
        
        for state in less_states:
            if power < state[CONF_THRESHOLD]:
                return state[CONF_STATE_NAME]
        
        return "unknown"

    def _apply_delays(self, threshold_state: str, power: float) -> str:
        current = self.current_state
        
        # Idle → Start (aktif) geçiş
        if current == "idle":
            if threshold_state == self.start_state_name:
                if self.active_timer_start is None:
                    self.active_timer_start = datetime.now()
                    _LOGGER.debug("Active timer başlatıldı")
                if self._get_timer_duration(self.active_timer_start) >= self.active_delay:
                    self.active_timer_start = None
                    return threshold_state
                return "idle"
            self.active_timer_start = None
            return "idle"
        
        # Aktif durumdayken
        if current not in ["idle", self.finish_state_name]:
            # Finish'e geçiş?
            if threshold_state == self.finish_state_name:
                if self.finished_timer_start is None:
                    self.finished_timer_start = datetime.now()
                    _LOGGER.debug("Finished timer başlatıldı")
                if self._get_timer_duration(self.finished_timer_start) >= self.finished_delay:
                    self.finished_timer_start = None
                    self.finish_start_time = datetime.now()
                    _LOGGER.info("Finish durumuna geçildi: %s", self.finish_state_name)
                    return self.finish_state_name
                return current  # timer bitmedi → mevcut halde kal
            
            # Finish değilse timer sıfırla
            self.finished_timer_start = None
            return threshold_state if threshold_state != "unknown" else current
        
        return threshold_state if threshold_state != "unknown" else current

    def _check_idle_delay(self, proposed_state: str) -> str:
        """Finish → idle geçişini ZORLA kontrol et."""
        if self.current_state == self.finish_state_name:
            if self.finish_start_time is None:
                self.finish_start_time = datetime.now()
                _LOGGER.warning("finish_start_time None → otomatik başlatıldı")
            
            duration = self._get_timer_duration(self.finish_start_time)
            remaining = max(0, self.idle_delay - duration)
            
            _LOGGER.debug(
                "FINISH kontrol | current=%s | süre geçti=%d sn | kalan=%d sn / limit=%d sn | proposed=%s",
                self.current_state, duration, remaining, self.idle_delay, proposed_state
            )
            
            if duration >= self.idle_delay:
                _LOGGER.info("IDLE_DELAY DOLDU (%d sn) → idle'a ZORLA geçiş", self.idle_delay)
                self.finish_start_time = None
                self.finished_timer_start = None
                self.active_timer_start = None
                return "idle"
            
            # Süre dolmadı → finish'te kalmaya devam (proposed ne olursa olsun)
            return self.finish_state_name
        
        # Finish dışıysa timer temizle
        if self.finish_start_time is not None:
            _LOGGER.debug("Finish dışı → finish timer sıfırlandı")
            self.finish_start_time = None
        
        return proposed_state

    def _on_state_change(self, new_state: str) -> None:
        old_state = self.current_state
        self.current_state = new_state
        self.state_start_time = datetime.now()
        
        _LOGGER.info("Durum değişti: %s → %s (güç: %.1fW)", old_state, new_state, self.current_power)
        
        if old_state == "idle" and new_state != "idle":
            self.cycle_start_time = datetime.now()
            _LOGGER.info("Döngü başladı")
        
        elif old_state != "idle" and new_state == "idle":
            if self.cycle_start_time:
                dur = (datetime.now() - self.cycle_start_time).total_seconds()
                _LOGGER.info("Döngü bitti. Süre: %.0f sn", dur)
                self.cycle_start_time = None
        
        if new_state == self.finish_state_name:
            _LOGGER.info("Finish durumu algılandı (%s). %d sn sonra idle olacak", 
                         self.finish_state_name, self.idle_delay)

    def _get_state_duration(self) -> int:
        return int((datetime.now() - self.state_start_time).total_seconds())

    def _get_cycle_duration(self) -> int:
        if self.cycle_start_time and self.current_state != "idle":
            return int((datetime.now() - self.cycle_start_time).total_seconds())
        return 0

    def _get_timer_duration(self, timer_start: datetime | None) -> int:
        if timer_start:
            return int((datetime.now() - timer_start).total_seconds())
        return 0
