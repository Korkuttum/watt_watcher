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
        self.active_timer_start = None  # Aktif olma timer'ı
        self.finished_timer_start = None  # Bitti olma timer'ı
        self.bitti_start_time = None  # Bitti durumunun başlangıç zamanı
        
        # Configuration
        self.scan_interval = self.config.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        self.active_delay = self.config.get(CONF_ACTIVE_DELAY, DEFAULT_ACTIVE_DELAY)
        self.finished_delay = self.config.get(CONF_FINISHED_DELAY, DEFAULT_FINISHED_DELAY)
        self.idle_delay = self.config.get(CONF_IDLE_DELAY, DEFAULT_IDLE_DELAY)
        
        # States configuration
        self.states_config = self.config.get(CONF_STATES, [])
        self.state_icons = {}
        
        for state in self.states_config:
            state_name = state[CONF_STATE_NAME]
            self.state_icons[state_name] = state.get(CONF_ICON, "mdi:circle")
        
        # "bitti" durumunu kontrol et
        self.has_bitti_state = any(state[CONF_STATE_NAME] == "bitti" for state in self.states_config)
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.scan_interval),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from power sensor and update states."""
        try:
            # Get power sensor value
            power_entity = self.config[CONF_POWER_SENSOR]
            state = self.hass.states.get(power_entity)
            
            if state is None or state.state in ["unknown", "unavailable"]:
                _LOGGER.warning("Power sensor unavailable: %s", power_entity)
                return self._create_error_data()
            
            power = float(state.state)
            self.current_power = power
            
            # 1. Önce threshold'lara göre state belirle
            threshold_state = self._determine_state_by_thresholds(power)
            
            # 2. Delay'lere göre final state'i belirle
            new_state = self._apply_delays(threshold_state, power)
            
            # 3. IDLE_DELAY kontrolü - BİTTİ'den sonra IDLE'a geçiş
            new_state = self._check_idle_delay(new_state)
            
            if new_state != self.current_state:
                self._on_state_change(new_state)
            
            # 4. Aktiflik durumunu hesapla
            is_active = self.current_state not in ["idle", "bitti", "unknown"]
            
            # Get current state icon
            current_icon = self.state_icons.get(self.current_state, "mdi:circle")
            
            # Bitti durum süresini hesapla
            bitti_duration = 0
            if self.current_state == "bitti" and self.bitti_start_time:
                bitti_duration = int((datetime.now() - self.bitti_start_time).total_seconds())
            
            return {
                "current_power": self.current_power,
                "current_state": self.current_state,
                "current_icon": current_icon,
                "state_duration": self._get_state_duration(),
                "cycle_duration": self._get_cycle_duration(),
                "is_active": is_active,
                "bitti_duration": bitti_duration,
                "idle_remaining": max(0, self.idle_delay - bitti_duration) if self.current_state == "bitti" else 0,
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
            
        except (ValueError, AttributeError, TypeError) as err:
            _LOGGER.error("Error updating power data: %s", err)
            return self._create_error_data()

    def _determine_state_by_thresholds(self, power: float) -> str:
        """Determine state based on threshold comparisons."""
        # Durumları karşılaştırma tipine göre ayır
        greater_states = []
        less_states = []
        
        for state in self.states_config:
            if state[CONF_COMPARISON] == COMPARISON_GREATER:
                greater_states.append(state)
            elif state[CONF_COMPARISON] == COMPARISON_LESS:
                less_states.append(state)
        
        # Büyüktür durumlarını threshold'a göre AZALAN sırada sırala
        greater_states.sort(key=lambda x: x[CONF_THRESHOLD], reverse=True)
        
        # Küçüktür durumlarını threshold'a göre ARTI sırada sırala
        less_states.sort(key=lambda x: x[CONF_THRESHOLD])
        
        # Önce büyüktür durumlarını kontrol et
        for state in greater_states:
            if power > state[CONF_THRESHOLD]:
                return state[CONF_STATE_NAME]
        
        # Sonra küçüktür durumlarını kontrol et
        for state in less_states:
            if power < state[CONF_THRESHOLD]:
                return state[CONF_STATE_NAME]
        
        # Hiçbir durum eşleşmezse
        # Eğer "bitti" durumu tanımlı değilse ve power çok düşükse "idle" döndür
        if not self.has_bitti_state and power < 1.0:
            return "idle"
        
        return "unknown"

    def _apply_delays(self, threshold_state: str, power: float) -> str:
        """Apply delays to determine final state."""
        current_state = self.current_state
        
        # 1. IDLE → AKTİF geçişi (active_delay)
        if current_state == "idle":
            if threshold_state != "idle" and threshold_state != "unknown":
                # Aktif olma koşulu sağlandı, timer başlat
                if self.active_timer_start is None:
                    self.active_timer_start = datetime.now()
                    _LOGGER.debug("Active timer started")
                
                # Timer süresini kontrol et
                active_timer_duration = self._get_timer_duration(self.active_timer_start)
                if active_timer_duration >= self.active_delay:
                    # active_delay geçti, yeni duruma geç
                    self.active_timer_start = None
                    return threshold_state
                else:
                    # active_delay henüz dolmadı, idle kalmaya devam
                    return "idle"
            else:
                # Aktif koşul sağlanmadı, timer'ı sıfırla
                self.active_timer_start = None
                return "idle"
        
        # 2. AKTİF → BİTTİ geçişi (finished_delay)
        elif current_state not in ["idle", "bitti", "unknown"]:
            # Eğer "bitti" durumu tanımlıysa ve koşulu sağlanıyorsa
            if self.has_bitti_state and threshold_state == "bitti":
                # Bitti olma timer'ını başlat
                if self.finished_timer_start is None:
                    self.finished_timer_start = datetime.now()
                    _LOGGER.debug("Finished timer started")
                
                # Timer süresini kontrol et
                finished_timer_duration = self._get_timer_duration(self.finished_timer_start)
                if finished_timer_duration >= self.finished_delay:
                    # finished_delay geçti, bitti'ye geç
                    self.finished_timer_start = None
                    self.bitti_start_time = datetime.now()  # bitti başlangıç zamanını kaydet
                    return "bitti"
                else:
                    # finished_delay henüz dolmadı, mevcut durumda kal
                    return current_state
            else:
                # Bitti koşulu sağlanmadı, timer'ı sıfırla
                self.finished_timer_start = None
                return threshold_state if threshold_state != "unknown" else current_state
        
        # 3. Diğer durumlar
        return threshold_state if threshold_state != "unknown" else current_state

    def _check_idle_delay(self, proposed_state: str) -> str:
        """Check idle delay for transition from bitti to idle."""
        current_state = self.current_state
        
        # Eğer şu anki durum "bitti" ise
        if current_state == "bitti":
            # Bitti başlangıç zamanını kontrol et (güvenlik için)
            if self.bitti_start_time is None:
                self.bitti_start_time = datetime.now()
            
            # Bitti durumunda ne kadar süredir olduğunu hesapla
            bitti_duration = int((datetime.now() - self.bitti_start_time).total_seconds())
            
            # Eğer idle_delay süresi geçtiyse idle'a geç
            if bitti_duration >= self.idle_delay:
                _LOGGER.info("Idle delay passed (%d seconds), transitioning to idle", self.idle_delay)
                self.bitti_start_time = None  # Timer'ı sıfırla
                return "idle"
            else:
                # idle_delay henüz dolmadı, bitti kalmaya devam
                return "bitti"
        
        # Eğer yeni durum "bitti" değilse, bitti_start_time'ı sıfırla
        if proposed_state != "bitti":
            self.bitti_start_time = None
        
        return proposed_state

    def _on_state_change(self, new_state: str) -> None:
        """Handle state change."""
        old_state = self.current_state
        self.current_state = new_state
        self.state_start_time = datetime.now()
        
        # State change logging
        _LOGGER.info(
            "State changed: %s -> %s (power: %.1fW)",
            old_state, new_state, self.current_power
        )
        
        # Cycle tracking
        if old_state == "idle" and new_state not in ["idle", "bitti", "unknown"]:
            self.cycle_start_time = datetime.now()
            _LOGGER.info("Cycle started")
        
        elif old_state not in ["idle", "bitti", "unknown"] and new_state in ["idle", "bitti"]:
            if self.cycle_start_time:
                cycle_duration = (datetime.now() - self.cycle_start_time).total_seconds()
                _LOGGER.info("Cycle ended. Duration: %.0f seconds", cycle_duration)
                self.cycle_start_time = None
        
        # Bitti durumuna geçişte log
        if new_state == "bitti":
            _LOGGER.info("Program finished. Will go idle in %d seconds", self.idle_delay)

    def _get_state_duration(self) -> int:
        """Get duration in current state in seconds."""
        return int((datetime.now() - self.state_start_time).total_seconds())

    def _get_cycle_duration(self) -> int:
        """Get current cycle duration in seconds."""
        if self.cycle_start_time and self.current_state not in ["idle", "bitti", "unknown"]:
            return int((datetime.now() - self.cycle_start_time).total_seconds())
        return 0

    def _get_timer_duration(self, timer_start: datetime | None) -> int:
        """Get timer duration in seconds."""
        if timer_start:
            return int((datetime.now() - timer_start).total_seconds())
        return 0

    def _create_error_data(self) -> Dict[str, Any]:
        """Create error data structure."""
        return {
            "current_power": 0.0,
            "current_state": "error",
            "current_icon": "mdi:alert-circle",
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
            "timers": {
                "active_timer": 0,
                "finished_timer": 0,
            }
        }
