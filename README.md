# Batterij Planner voor Home Assistant

Batterij Planner is een custom integration die je thuisbatterij stuurt op de dynamische kwartierprijzen van Frank Energie. Je stelt alles in via het scherm, zonder YAML.

Bij elke berekening worden **alle bekende kwartieren tegelijk** doorgerekend: vandaag en morgen, tot ongeveer 35 uur vooruit. Per kwartier kiest de planner wat het meest oplevert:

| modus | wat de omvormer doet |
|---|---|
| zelfverbruik | normaal: PV-overschot naar de accu, tekort uit de accu |
| vasthouden | accu staat stil, het huis draait op net en PV (accu sparen voor een duurder moment) |
| laden | accu laden op max vermogen, uit PV en/of net |
| ontladen | accu ontladen op max vermogen, naar huis en net |

Daardoor benut de planner een dure **ochtendpiek** net zo goed als de avondpiek.

Bij elke beslissing telt mee:

- afname- en terugleverprijs per kwartier, met saldering t/m 2026 en daarna marktprijs + opslag;
- de PV-verwachting;
- een zelf geleerd verbruiksprofiel per uur, apart voor werkdag en weekend;
- laad- en ontlaadverlies;
- slijtage;
- min/max SOC en max vermogen;
- de waarde van de lading die aan het einde van de planning nog in de accu zit.

Elke 5 minuten wordt opnieuw gerekend met de actuele SOC, en direct zodra de prijzen van morgen binnen zijn.

Gemaakt voor en getest met: Solis RHI-3.6K-48ES-5G (Solis Modbus), Dyness 16 kWh, Frank Quarter Prices en Forecast.Solar. Solcast werkt ook.

---

## Installatie

### 1. Oude sturing opruimen

Heb je eerder de YAML-versie (v5 package) of v4.x gebruikt?

- Haal `packages/batterij_planner.yaml` of je oude batterijpackage weg.
- Haal `python_scripts/batterij_planner.py` weg.
- De regel `python_script:` in `configuration.yaml` mag blijven staan als je andere scripts hebt. Anders mag die ook weg.
- Zet in de Frank-app **Slim Terugleveren** en **Slim Handelen** uit.

### 2. Integratie neerzetten

Kies een van de twee manieren.

**Handmatig (Samba, File editor of Studio Code Server):**

1. Maak in je configmap, waar `configuration.yaml` staat, een map `custom_components` als die er nog niet is.
2. Kopieer de map `batterij_planner` daarin, zodat je dit krijgt:

```
config/
├── configuration.yaml
└── custom_components/
    └── batterij_planner/
        ├── __init__.py
        ├── manifest.json
        ├── optimizer.py
        └── ... (overige bestanden + map translations)
```

**Via HACS (als deze map in een eigen GitHub-repository staat):**
HACS → ⋮ → Aangepaste repositories → URL van de repository, categorie *Integratie* → **Batterij Planner** downloaden.

### 3. Herstarten

Instellingen → ⋮ rechtsboven → **Home Assistant herstarten** → *Herstarten*.

### 4. Integratie toevoegen

Instellingen → **Apparaten & diensten** → **+ Integratie toevoegen** → zoek **Batterij Planner**.

**Scherm 1: Bronnen.** Bestaande standaardnamen zijn al ingevuld; controleer ze.

| veld | jouw entiteit (waarschijnlijk) |
|---|---|
| Laadtoestand accu | `sensor.pv_omvormer_battery_soc` |
| Huisverbruik | `sensor.pv_omvormer_household_load_power` (of `..._house_load_power`) |
| Frank prijzen vandaag / morgen | `sensor.frank_prices_today` / `sensor.frank_prices_tomorrow` |
| PV rest van vandaag / morgen | `sensor.energy_production_today_remaining` / `sensor.energy_production_tomorrow` |
| Solcast | leeg laten, tenzij je Solcast gebruikt |

**Scherm 2: Omvormer.** Kies de TOU-entiteiten van Solis Modbus voor laadslot 1 en ontlaadslot 1, plus de laad- en ontlaadstroom. De werkmodus is optioneel.

### 5. Instellingen controleren

Bij de integratie: **Configureren → Instellingen**. Alles heeft een verstandige standaardwaarde. Controleer vooral:

- **Capaciteit** (16 kWh), **min/max SOC** en **max laad-/ontlaadvermogen** (3000 W).
- **Werkmodus waarin TOU actief is.** Kies hier de TOU-variant uit de lijst als de planner de werkmodus zelf mag zetten. Staat je omvormer al vast in de TOU-modus, laat dan *Werkmodus niet aanpassen* staan.
- **Melding met plan voor morgen.** Kies je telefoon (`notify.mobile_app_...`) om rond 13–14 uur het plan voor morgen te krijgen.

Wijzigingen gelden direct; de integratie herlaadt zichzelf.

### 6. Een dag meekijken, daarna aanzetten

Het apparaat **Batterij Planner** heeft een schakelaar **Sturing actief**, die standaard uit staat. Zolang die uit staat, rekent de planner wel, maar raakt hij de omvormer niet aan.

1. Kijk een dag mee met `sensor.batterij_planner_modus`. Het attribuut `blokken` toont het hele plan; de dashboardkaart hieronder maakt het overzichtelijk.
2. Klopt het, zet dan **Sturing actief** aan.
3. Kijk bij de eerstvolgende wissel in de Solis-entiteiten of de tijden veranderen. Het attribuut `laatste_schrijfacties` van de modus-sensor laat zien wat er is geschreven.

Zet je de schakelaar uit, dan worden beide TOU-slots leeggemaakt en draait de omvormer gewoon op zelfverbruik.

---

## Entiteiten

| entiteit | betekenis |
|---|---|
| `sensor.batterij_planner_modus` | huidige modus; attributen: volledig plan (`blokken`, `slots`), kosten, PV-bron, fout |
| `sensor.batterij_planner_verwachte_besparing` | € beter dan alleen zelfverbruik, over de hele bekende horizon |
| `sensor.batterij_planner_volgende_actie` | bijv. `ontladen di 06:45-09:00` |
| `sensor.batterij_planner_doel_soc_einde_blok` | verwachte SOC aan het eind van het huidige blok |
| `sensor.batterij_planner_geleerd_verbruik_laatste_kwartier` | geleerd verbruik; attributen: profiel per uur |
| `switch.batterij_planner_sturing_actief` | omvormer wel/niet aansturen |
| `button.batterij_planner_plan_herberekenen` | direct opnieuw rekenen |

## Hoe de omvormer wordt aangestuurd

De planner gebruikt alleen TOU-slot 1 en schrijft alleen als een waarde echt verandert:

| modus | laadslot 1 | ontlaadslot 1 |
|---|---|---|
| zelfverbruik | 00:00–00:00 (uit) | 00:00–00:00 (uit) |
| laden | nu → einde blok, max stroom | uit |
| vasthouden | nu → einde blok, 0 A | uit |
| ontladen | uit | nu → einde blok, max stroom |

Stroom = vermogen ÷ accuspanning (3000 W ÷ 51,2 V = 58 A). Een blok dat over middernacht loopt, wordt tot 23:59 gezet en na middernacht opnieuw. Ontbreken gegevens (SOC onbekend, geen prijzen), dan valt de planner terug op zelfverbruik.

Twee dingen moet je één keer zelf testen:

- **Vasthouden:** controleer op een zonnig uur dat de accu met een laadslot op 0 A echt stilstaat.
- **Laden uit het net:** dat werkt alleen als *Allow grid charging* aan staat op de omvormer.

## Saldering

- **Automatisch** (standaard): t/m 31-12-2026 is terugleveren evenveel waard als de afnameprijs van dat kwartier, vanaf 1-1-2027 marktprijs + opslag (€ 0,0182). Dit wordt per kwartier bepaald, dus ook de jaarwissel gaat goed.
- Saldering geldt alleen tot je jaarafname. Lever je over het jaar netto méér terug dan je afneemt, kies dan *Geen saldering*.

## Dashboardkaart (apexcharts-card)

```yaml
type: custom:apexcharts-card
header: {show: true, title: Batterijplan, show_states: true}
graph_span: 36h
span: {start: hour, offset: -1h}
now: {show: true, label: nu}
yaxis:
  - id: prijs
    decimals: 2
  - id: soc
    opposite: true
    min: 0
    max: 100
series:
  - entity: sensor.batterij_planner_modus
    name: Afnameprijs
    type: column
    yaxis_id: prijs
    data_generator: "return (entity.attributes.slots||[]).map(s => [s[0], s[3]]);"
  - entity: sensor.batterij_planner_modus
    name: Geplande SOC
    type: line
    yaxis_id: soc
    stroke_width: 3
    data_generator: "return (entity.attributes.slots||[]).map(s => [s[0] + 900000, s[2]]);"
```

Elk item in `slots` is `[tijd_ms, modus (Z/V/L/O), soc%, afnameprijs, terugleverprijs, pv_kW, verbruik_kW]`.

## Problemen oplossen

| symptoom | oplossing |
|---|---|
| *Batterij Planner* niet te vinden bij Integratie toevoegen | map staat niet in `config/custom_components/batterij_planner`, of je hebt niet herstart; browsercache legen |
| "Deze sensor heeft geen 'prices'-attribuut" | kies de Frank Quarter Prices-sensor `..._prices_today`, niet de huidige prijs |
| Modus-sensor heeft attribuut `fout` | daarin staat wat ontbreekt (SOC onbekend / geen prijzen) |
| Omvormer reageert niet | Configureren → Omvormer: entiteiten controleren; logboek bekijken |

Extra logging aanzetten:

```yaml
logger:
  logs:
    custom_components.batterij_planner: debug
```
