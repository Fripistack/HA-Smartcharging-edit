"""Constanten voor Batterij Planner."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "batterij_planner"
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]

# ---- bronnen (stap 1)
CONF_SOC = "soc_entity"
CONF_VERBRUIK = "verbruik_entity"
CONF_PRIJS_VANDAAG = "prijs_vandaag_entity"
CONF_PRIJS_MORGEN = "prijs_morgen_entity"
CONF_PV_REST = "pv_rest_vandaag_entity"
CONF_PV_MORGEN = "pv_morgen_entity"
CONF_SOLCAST_VANDAAG = "solcast_vandaag_entity"
CONF_SOLCAST_MORGEN = "solcast_morgen_entity"

# ---- omvormer (stap 2)
CONF_LAAD_START = "laad_start_entity"
CONF_LAAD_EIND = "laad_eind_entity"
CONF_ONTLAAD_START = "ontlaad_start_entity"
CONF_ONTLAAD_EIND = "ontlaad_eind_entity"
CONF_LAAD_STROOM = "laad_stroom_entity"
CONF_ONTLAAD_STROOM = "ontlaad_stroom_entity"
CONF_WERKMODUS = "werkmodus_entity"

# ---- instellingen (options)
CONF_WERKMODUS_TOU = "werkmodus_tou"
CONF_VASTHOUDEN_STROOM = "vasthouden_stroom"
CONF_SPANNING = "accu_spanning"
CONF_NOTIFY = "notify_service"
NIET_WIJZIGEN = "__niet_wijzigen__"
GEEN_MELDING = "__geen__"

BRON_KEYS = [
    CONF_SOC, CONF_VERBRUIK, CONF_PRIJS_VANDAAG, CONF_PRIJS_MORGEN,
    CONF_PV_REST, CONF_PV_MORGEN, CONF_SOLCAST_VANDAAG, CONF_SOLCAST_MORGEN,
]
OMVORMER_KEYS = [
    CONF_LAAD_START, CONF_LAAD_EIND, CONF_ONTLAAD_START, CONF_ONTLAAD_EIND,
    CONF_LAAD_STROOM, CONF_ONTLAAD_STROOM, CONF_WERKMODUS,
]

# Voorgestelde entiteiten (Frank Quarter Prices, Forecast.Solar, Solis Modbus met
# apparaatnaam "PV omvormer"). Worden alleen voorgesteld als ze bestaan.
SUGGESTIES = {
    CONF_SOC: "sensor.pv_omvormer_battery_soc",
    CONF_VERBRUIK: "sensor.pv_omvormer_household_load_power",
    CONF_PRIJS_VANDAAG: "sensor.frank_prices_today",
    CONF_PRIJS_MORGEN: "sensor.frank_prices_tomorrow",
    CONF_PV_REST: "sensor.energy_production_today_remaining",
    CONF_PV_MORGEN: "sensor.energy_production_tomorrow",
    CONF_LAAD_START: "time.pv_omvormer_time_charging_charge_start_slot_1",
    CONF_LAAD_EIND: "time.pv_omvormer_time_charging_charge_end_slot_1",
    CONF_ONTLAAD_START: "time.pv_omvormer_time_charging_discharge_start_slot_1",
    CONF_ONTLAAD_EIND: "time.pv_omvormer_time_charging_discharge_end_slot_1",
    CONF_LAAD_STROOM: "number.pv_omvormer_time_charging_charge_current",
    CONF_ONTLAAD_STROOM: "number.pv_omvormer_time_charging_discharge_current",
    CONF_WERKMODUS: "select.pv_omvormer_work_mode",
}

# Standaardwaarden voor de rekeninstellingen (namen = velden van optimizer.Instellingen)
STANDAARD_INSTELLINGEN: dict[str, float | str] = {
    "capaciteit_kwh": 16.0,
    "min_soc": 10.0,
    "max_soc": 100.0,
    "max_laad_w": 3000.0,
    "max_ontlaad_w": 3000.0,
    "rendement_laden": 95.0,
    "rendement_ontladen": 95.0,
    "slijtage_eur_kwh": 0.03,
    "pv_factor": 0.9,
    "saldering": "auto",
    "saldering_correctie": 0.0,
    "teruglever_opslag": 0.0182,
    "eindwaarde_factor": 1.0,
    "verbruik_fallback_w": 400.0,
    CONF_SPANNING: 51.2,
    CONF_VASTHOUDEN_STROOM: 0.0,
    CONF_WERKMODUS_TOU: NIET_WIJZIGEN,
    CONF_NOTIFY: GEEN_MELDING,
}
