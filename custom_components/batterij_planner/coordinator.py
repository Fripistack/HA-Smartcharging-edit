"""Coordinator: plan berekenen, verbruik leren en de omvormer aansturen."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import fields
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SUN_EVENT_SUNRISE, SUN_EVENT_SUNSET
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import optimizer
from .const import (
    CONF_LAAD_EIND,
    CONF_LAAD_START,
    CONF_LAAD_STROOM,
    CONF_NOTIFY,
    CONF_ONTLAAD_EIND,
    CONF_ONTLAAD_START,
    CONF_ONTLAAD_STROOM,
    CONF_PRIJS_MORGEN,
    CONF_PRIJS_VANDAAG,
    CONF_PV_MORGEN,
    CONF_PV_REST,
    CONF_SOC,
    CONF_SOLCAST_MORGEN,
    CONF_SOLCAST_VANDAAG,
    CONF_SPANNING,
    CONF_VASTHOUDEN_STROOM,
    CONF_VERBRUIK,
    CONF_WERKMODUS,
    CONF_WERKMODUS_TOU,
    DOMAIN,
    GEEN_MELDING,
    NIET_WIJZIGEN,
    STANDAARD_INSTELLINGEN,
)
from .profiel import VerbruiksProfiel

_LOGGER = logging.getLogger(__name__)
ONGELDIG = ("unknown", "unavailable", "none", "")


class PlanFout(Exception):
    """Plan kan niet berekend worden (ontbrekende gegevens)."""


def _float(state: State | None) -> float | None:
    if state is None or state.state in ONGELDIG:
        return None
    try:
        return float(state.state)
    except ValueError:
        return None


class BatterijPlannerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Rekent elke 5 minuten (en bij nieuwe prijzen) het plan opnieuw uit."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None)
        self.conf: dict[str, Any] = {**STANDAARD_INSTELLINGEN, **entry.data, **entry.options}
        self.actief = False
        self.profiel = VerbruiksProfiel(hass, entry.entry_id, float(self.conf["verbruik_fallback_w"]))
        self._lock = asyncio.Lock()
        self._unsubs: list = []
        self._melding_gepland = False
        self._laatste_melding: date | None = None
        self.laatste_schrijfacties: list[str] = []

    # ------------------------------------------------------------------ levensloop
    async def async_start(self) -> None:
        await self.profiel.async_load()
        verbruik = self.conf.get(CONF_VERBRUIK)
        self.profiel.meting(_float(self.hass.states.get(verbruik)), dt_util.now())
        self._unsubs.append(
            async_track_time_change(self.hass, self._tik_plan, minute=list(range(0, 60, 5)), second=20)
        )
        self._unsubs.append(
            async_track_time_change(self.hass, self._tik_kwartier, minute=[0, 15, 30, 45], second=0)
        )
        if verbruik:
            self._unsubs.append(async_track_state_change_event(self.hass, [verbruik], self._verbruik_event))
        if self.conf.get(CONF_PRIJS_MORGEN):
            self._unsubs.append(
                async_track_state_change_event(self.hass, [self.conf[CONF_PRIJS_MORGEN]], self._prijzen_event)
            )

    async def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        await self.profiel.async_save()

    # ------------------------------------------------------------------ events
    async def _tik_plan(self, _now: datetime) -> None:
        await self.async_refresh()

    @callback
    def _tik_kwartier(self, now: datetime) -> None:
        self.profiel.afsluiten(now)

    @callback
    def _verbruik_event(self, event: Event[EventStateChangedData]) -> None:
        self.profiel.meting(_float(event.data["new_state"]), dt_util.now())

    @callback
    def _prijzen_event(self, event: Event[EventStateChangedData]) -> None:
        nieuw = event.data["new_state"]
        oud = event.data["old_state"]
        had = bool(oud and oud.attributes.get("prices"))
        heeft = bool(nieuw and nieuw.attributes.get("prices"))
        if heeft and not had:
            self._melding_gepland = True
            self.hass.async_create_task(self.async_request_refresh())

    # ------------------------------------------------------------------ update
    async def _async_update_data(self) -> dict[str, Any]:
        async with self._lock:
            nu = dt_util.now()
            try:
                resultaat = await self._bereken(nu)
            except PlanFout as err:
                resultaat = {"modus": "zelfverbruik", "fout": str(err)}
                _LOGGER.warning("Batterij Planner: %s -> zelfverbruik", err)
            except Exception:  # noqa: BLE001 - nooit de omvormer in een rare stand laten
                _LOGGER.exception("Batterij Planner: onverwachte fout bij berekenen")
                resultaat = {"modus": "zelfverbruik", "fout": "onverwachte fout, zie logboek"}
            resultaat["bijgewerkt"] = nu
            resultaat["sturing_actief"] = self.actief
            if self.actief:
                await self._stuur(resultaat)
            if self._melding_gepland and "fout" not in resultaat:
                self._melding_gepland = False
                await self._meld(resultaat)
            return resultaat

    def _instellingen(self) -> optimizer.Instellingen:
        namen = {f.name for f in fields(optimizer.Instellingen)}
        waarden = {}
        for k, v in self.conf.items():
            if k in namen and v is not None:
                waarden[k] = v if k == "saldering" else float(v)
        return optimizer.Instellingen(**waarden)

    def _kwh(self, entity_id: str | None) -> float:
        st = self.hass.states.get(entity_id) if entity_id else None
        waarde = _float(st)
        if waarde is None:
            return 0.0
        eenheid = (st.attributes.get("unit_of_measurement") or "kWh").lower()
        return waarde / 1000.0 if eenheid == "wh" else waarde

    def _attr_lijst(self, entity_id: str | None, naam: str) -> list:
        st = self.hass.states.get(entity_id) if entity_id else None
        waarde = st.attributes.get(naam) if st else None
        return list(waarde) if isinstance(waarde, (list, tuple)) else []

    async def _bereken(self, nu: datetime) -> dict[str, Any]:
        inst = self._instellingen()
        soc = _float(self.hass.states.get(self.conf.get(CONF_SOC) or ""))
        if soc is None:
            raise PlanFout("SOC onbekend")
        tz = dt_util.get_default_time_zone()
        prijzen = [
            self._attr_lijst(self.conf.get(CONF_PRIJS_VANDAAG), "prices"),
            self._attr_lijst(self.conf.get(CONF_PRIJS_MORGEN), "prices"),
        ]
        slots = optimizer.bouw_slots(prijzen, nu, tz)
        if not slots:
            raise PlanFout("geen prijzen beschikbaar")

        optimizer.zet_terugleverprijs(slots, inst)
        optimizer.zet_verbruik(slots, self.profiel.werkdag, self.profiel.weekend, inst.verbruik_fallback_w)

        solcast = self._attr_lijst(self.conf.get(CONF_SOLCAST_VANDAAG), "detailedForecast") + self._attr_lijst(
            self.conf.get(CONF_SOLCAST_MORGEN), "detailedForecast"
        )
        if solcast and optimizer.zet_pv_solcast(slots, solcast, tz, inst.pv_factor):
            pv_bron = "solcast"
        else:
            pv_bron = "forecast_solar"
            vandaag = nu.date()
            totalen = {
                vandaag: self._kwh(self.conf.get(CONF_PV_REST)),
                vandaag + timedelta(days=1): self._kwh(self.conf.get(CONF_PV_MORGEN)),
            }
            zon: dict[date, tuple[datetime, datetime]] = {}
            for d in {s.start.date() for s in slots}:
                op = get_astral_event_date(self.hass, SUN_EVENT_SUNRISE, d)
                onder = get_astral_event_date(self.hass, SUN_EVENT_SUNSET, d)
                if op and onder:
                    zon[d] = (dt_util.as_local(op), dt_util.as_local(onder))
            optimizer.zet_pv_verdeeld(slots, totalen, zon, inst.pv_factor)

        resultaat = await self.hass.async_add_executor_job(optimizer.optimaliseer, slots, soc, inst)
        resultaat["pv_bron"] = pv_bron
        resultaat["laad_vermogen_w"] = inst.max_laad_w
        resultaat["ontlaad_vermogen_w"] = inst.max_ontlaad_w
        return resultaat

    # ------------------------------------------------------------------ sturing
    async def async_naar_zelfverbruik(self) -> None:
        """Beide TOU-slots leegmaken (bij uitzetten van de sturing)."""
        async with self._lock:
            await self._stuur({"modus": "zelfverbruik"})

    def _schrijflijst(self, res: dict[str, Any]) -> list[tuple[str, str, Any]]:
        c = self.conf
        nu = dt_util.now()
        modus = res.get("modus", "zelfverbruik")
        if "fout" in res:
            modus = "zelfverbruik"
        start = f"{nu.hour:02d}:{(nu.minute // 15) * 15:02d}:00"
        einde = res.get("blok_einde")
        if isinstance(einde, datetime) and dt_util.as_local(einde).date() == nu.date():
            e = dt_util.as_local(einde)
            eind = f"{e.hour:02d}:{e.minute:02d}:00"
        else:
            eind = "23:59:00"
        spanning = float(c.get(CONF_SPANNING) or 51.2)
        laad_a = int(float(res.get("laad_vermogen_w", c["max_laad_w"])) / spanning)
        ontlaad_a = int(float(res.get("ontlaad_vermogen_w", c["max_ontlaad_w"])) / spanning)
        nul = "00:00:00"
        wis_laden = [("time", c.get(CONF_LAAD_START), nul), ("time", c.get(CONF_LAAD_EIND), nul)]
        wis_ontladen = [("time", c.get(CONF_ONTLAAD_START), nul), ("time", c.get(CONF_ONTLAAD_EIND), nul)]
        if modus == "laden":
            lijst = wis_ontladen + [
                ("number", c.get(CONF_LAAD_STROOM), laad_a),
                ("time", c.get(CONF_LAAD_START), start),
                ("time", c.get(CONF_LAAD_EIND), eind),
            ]
        elif modus == "vasthouden":
            lijst = wis_ontladen + [
                ("number", c.get(CONF_LAAD_STROOM), float(c.get(CONF_VASTHOUDEN_STROOM) or 0)),
                ("time", c.get(CONF_LAAD_START), start),
                ("time", c.get(CONF_LAAD_EIND), eind),
            ]
        elif modus == "ontladen":
            lijst = wis_laden + [
                ("number", c.get(CONF_ONTLAAD_STROOM), ontlaad_a),
                ("time", c.get(CONF_ONTLAAD_START), start),
                ("time", c.get(CONF_ONTLAAD_EIND), eind),
            ]
        else:
            lijst = wis_laden + wis_ontladen
        werkmodus = c.get(CONF_WERKMODUS)
        tou = c.get(CONF_WERKMODUS_TOU)
        if modus != "zelfverbruik" and werkmodus and tou and tou != NIET_WIJZIGEN:
            lijst.insert(0, ("select", werkmodus, tou))
        return [item for item in lijst if item[1]]

    async def _stuur(self, res: dict[str, Any]) -> None:
        acties: list[str] = []
        for domein, entity_id, waarde in self._schrijflijst(res):
            st = self.hass.states.get(entity_id)
            if st is None or st.state == "unavailable":
                _LOGGER.warning("Batterij Planner: %s niet beschikbaar, overgeslagen", entity_id)
                continue
            try:
                if domein == "time":
                    if st.state == waarde:
                        continue
                    await self.hass.services.async_call(
                        "time", "set_value", {"entity_id": entity_id, "time": waarde}, blocking=True
                    )
                elif domein == "number":
                    huidig = _float(st)
                    if huidig is not None and abs(huidig - float(waarde)) < 0.5:
                        continue
                    await self.hass.services.async_call(
                        "number", "set_value", {"entity_id": entity_id, "value": waarde}, blocking=True
                    )
                else:
                    if st.state == waarde:
                        continue
                    await self.hass.services.async_call(
                        "select", "select_option", {"entity_id": entity_id, "option": waarde}, blocking=True
                    )
                acties.append(f"{entity_id} = {waarde}")
            except (HomeAssistantError, ValueError) as err:
                _LOGGER.error("Batterij Planner: schrijven naar %s mislukt: %s", entity_id, err)
        if acties:
            _LOGGER.info("Batterij Planner (%s): %s", res.get("modus"), ", ".join(acties))
            self.laatste_schrijfacties = acties

    # ------------------------------------------------------------------ melding
    async def _meld(self, res: dict[str, Any]) -> None:
        dienst = self.conf.get(CONF_NOTIFY)
        vandaag = dt_util.now().date()
        if not dienst or dienst == GEEN_MELDING or self._laatste_melding == vandaag:
            return
        morgen = vandaag + timedelta(days=1)
        regels = []
        for b in res.get("blokken", []):
            eind = dt_util.parse_datetime(b["eind"])
            if eind and dt_util.as_local(eind).date() >= morgen and b["modus"] != "zelfverbruik":
                regels.append(
                    f"{b['tijd']} {b['modus']} ({b['soc_start']:.0f}→{b['soc_eind']:.0f}%, € {b['afname_gem']:.3f})"
                )
        domein, _, naam = dienst.partition(".")
        try:
            await self.hass.services.async_call(
                domein or "notify",
                naam,
                {
                    "title": f"🔋 Plan morgen – verwacht € {res.get('besparing', 0):.2f} beter dan alleen zelfverbruik",
                    "message": "\n".join(regels) or "Morgen alleen zelfverbruik.",
                },
                blocking=False,
            )
            self._laatste_melding = vandaag
        except HomeAssistantError as err:
            _LOGGER.error("Batterij Planner: melding versturen mislukt: %s", err)
