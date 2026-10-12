"""Config flow en options flow voor Batterij Planner."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    BRON_KEYS,
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
    OMVORMER_KEYS,
    STANDAARD_INSTELLINGEN,
    SUGGESTIES,
)

VERPLICHT = {CONF_SOC, CONF_VERBRUIK, CONF_PRIJS_VANDAAG, CONF_PRIJS_MORGEN,
             CONF_LAAD_START, CONF_LAAD_EIND, CONF_ONTLAAD_START, CONF_ONTLAAD_EIND,
             CONF_LAAD_STROOM, CONF_ONTLAAD_STROOM}

DOMEIN_PER_KEY = {
    CONF_SOC: "sensor", CONF_VERBRUIK: "sensor", CONF_PRIJS_VANDAAG: "sensor",
    CONF_PRIJS_MORGEN: "sensor", CONF_PV_REST: "sensor", CONF_PV_MORGEN: "sensor",
    CONF_SOLCAST_VANDAAG: "sensor", CONF_SOLCAST_MORGEN: "sensor",
    CONF_LAAD_START: "time", CONF_LAAD_EIND: "time", CONF_ONTLAAD_START: "time",
    CONF_ONTLAAD_EIND: "time", CONF_LAAD_STROOM: "number", CONF_ONTLAAD_STROOM: "number",
    CONF_WERKMODUS: "select",
}


def _voorstel(hass: HomeAssistant, key: str, huidig: dict[str, Any]) -> str | None:
    if key in huidig:
        return huidig.get(key)
    sug = SUGGESTIES.get(key)
    if sug and hass.states.get(sug) is not None:
        return sug
    return None


def _entity_schema(hass: HomeAssistant, keys: list[str], huidig: dict[str, Any]) -> vol.Schema:
    velden: dict[Any, Any] = {}
    for key in keys:
        sel = selector.EntitySelector(selector.EntitySelectorConfig(domain=DOMEIN_PER_KEY[key]))
        voorstel = _voorstel(hass, key, huidig)
        if key in VERPLICHT:
            if voorstel:
                velden[vol.Required(key, default=voorstel)] = sel
            else:
                velden[vol.Required(key)] = sel
        else:
            velden[vol.Optional(key, description={"suggested_value": voorstel})] = sel
    return vol.Schema(velden)


def _met_lege_optionele(keys: list[str], user_input: dict[str, Any]) -> dict[str, Any]:
    """Leeggemaakte optionele velden expliciet op None zetten."""
    return {k: user_input.get(k) for k in keys}


def _controleer_bronnen(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    fouten: dict[str, str] = {}
    soc = hass.states.get(data.get(CONF_SOC) or "")
    if soc is None:
        fouten[CONF_SOC] = "niet_gevonden"
    else:
        try:
            float(soc.state)
        except ValueError:
            fouten[CONF_SOC] = "geen_getal"
    prijs = hass.states.get(data.get(CONF_PRIJS_VANDAAG) or "")
    if prijs is None or not isinstance(prijs.attributes.get("prices"), list):
        fouten[CONF_PRIJS_VANDAAG] = "geen_prijzen"
    return fouten


def _num(minimum: float, maximum: float, stap: float, eenheid: str | None = None) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=stap, unit_of_measurement=eenheid,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _instellingen_schema(hass: HomeAssistant, huidig: dict[str, Any]) -> vol.Schema:
    w = {**STANDAARD_INSTELLINGEN, **{k: v for k, v in huidig.items() if v is not None}}

    werkmodus_opties = [selector.SelectOptionDict(value=NIET_WIJZIGEN, label="Werkmodus niet aanpassen")]
    sel_entity = huidig.get(CONF_WERKMODUS)
    st = hass.states.get(sel_entity) if sel_entity else None
    if st is not None:
        for opt in st.attributes.get("options", []):
            werkmodus_opties.append(selector.SelectOptionDict(value=str(opt), label=str(opt)))

    notify_opties = [selector.SelectOptionDict(value=GEEN_MELDING, label="Geen melding")]
    for naam in sorted(hass.services.async_services().get("notify", {})):
        notify_opties.append(selector.SelectOptionDict(value=f"notify.{naam}", label=f"notify.{naam}"))

    return vol.Schema(
        {
            vol.Required("capaciteit_kwh", default=w["capaciteit_kwh"]): _num(1, 100, 0.1, "kWh"),
            vol.Required("min_soc", default=w["min_soc"]): _num(0, 60, 1, "%"),
            vol.Required("max_soc", default=w["max_soc"]): _num(40, 100, 1, "%"),
            vol.Required("max_laad_w", default=w["max_laad_w"]): _num(100, 20000, 100, "W"),
            vol.Required("max_ontlaad_w", default=w["max_ontlaad_w"]): _num(100, 20000, 100, "W"),
            vol.Required("rendement_laden", default=w["rendement_laden"]): _num(70, 100, 0.5, "%"),
            vol.Required("rendement_ontladen", default=w["rendement_ontladen"]): _num(70, 100, 0.5, "%"),
            vol.Required("slijtage_eur_kwh", default=w["slijtage_eur_kwh"]): _num(0, 0.3, 0.001, "€/kWh"),
            vol.Required("saldering", default=w["saldering"]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value="auto", label="Automatisch: saldering t/m 2026"),
                        selector.SelectOptionDict(value="aan", label="Altijd saldering"),
                        selector.SelectOptionDict(value="uit", label="Geen saldering"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required("saldering_correctie", default=w["saldering_correctie"]): _num(0, 0.2, 0.0001, "€/kWh"),
            vol.Required("teruglever_opslag", default=w["teruglever_opslag"]): _num(-0.1, 0.2, 0.0001, "€/kWh"),
            vol.Required("pv_factor", default=w["pv_factor"]): _num(0.3, 1.5, 0.05),
            vol.Required("eindwaarde_factor", default=w["eindwaarde_factor"]): _num(0.3, 1.5, 0.05),
            vol.Required("verbruik_fallback_w", default=w["verbruik_fallback_w"]): _num(0, 5000, 10, "W"),
            vol.Required(CONF_SPANNING, default=w[CONF_SPANNING]): _num(10, 1000, 0.1, "V"),
            vol.Required(CONF_VASTHOUDEN_STROOM, default=w[CONF_VASTHOUDEN_STROOM]): _num(0, 100, 1, "A"),
            vol.Required(CONF_WERKMODUS_TOU, default=w[CONF_WERKMODUS_TOU]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=werkmodus_opties, custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_NOTIFY, default=w[CONF_NOTIFY]): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=notify_opties, custom_value=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


class BatterijPlannerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Eerste installatie: bronnen en omvormer kiezen."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        fouten: dict[str, str] = {}
        if user_input is not None:
            fouten = _controleer_bronnen(self.hass, user_input)
            if not fouten:
                self._data.update(_met_lege_optionele(BRON_KEYS, user_input))
                return await self.async_step_omvormer()
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _entity_schema(self.hass, BRON_KEYS, {}), user_input or {}
            ),
            errors=fouten,
        )

    async def async_step_omvormer(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(_met_lege_optionele(OMVORMER_KEYS, user_input))
            return self.async_create_entry(
                title="Batterij Planner",
                data=self._data,
                options=dict(STANDAARD_INSTELLINGEN),
            )
        return self.async_show_form(
            step_id="omvormer",
            data_schema=_entity_schema(self.hass, OMVORMER_KEYS, {}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BatterijPlannerOptionsFlow()


class BatterijPlannerOptionsFlow(OptionsFlow):
    """Later aanpassen via Configureren."""

    def _huidig(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["instellingen", "bronnen", "omvormer"])

    async def async_step_instellingen(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            if user_input["min_soc"] >= user_input["max_soc"]:
                return self.async_show_form(
                    step_id="instellingen",
                    data_schema=_instellingen_schema(self.hass, {**self._huidig(), **user_input}),
                    errors={"base": "soc_bereik"},
                )
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        return self.async_show_form(
            step_id="instellingen", data_schema=_instellingen_schema(self.hass, self._huidig())
        )

    async def async_step_bronnen(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fouten: dict[str, str] = {}
        if user_input is not None:
            fouten = _controleer_bronnen(self.hass, user_input)
            if not fouten:
                return self.async_create_entry(
                    data={**self.config_entry.options, **_met_lege_optionele(BRON_KEYS, user_input)}
                )
        return self.async_show_form(
            step_id="bronnen",
            data_schema=_entity_schema(self.hass, BRON_KEYS, self._huidig()),
            errors=fouten,
        )

    async def async_step_omvormer(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={**self.config_entry.options, **_met_lege_optionele(OMVORMER_KEYS, user_input)}
            )
        return self.async_show_form(
            step_id="omvormer", data_schema=_entity_schema(self.hass, OMVORMER_KEYS, self._huidig())
        )
