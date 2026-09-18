# HeatConductor – Projektplan

> Home-Assistant-Integration (HACS) zur ganzheitlichen Steuerung der Heizungsanlage.
> Stand: 2026-09-14 · Status: **Software vollständig umgesetzt (Phasen 1–5, Panel A–D); Hardware-Phase 3 und Abnahmen am realen System offen** · Domain: `heat_conductor`

---

## 1. Ziel und Rahmen

HeatConductor ist eine **All-in-one-Heizungssteuerung** als Custom Integration für Home Assistant:

- steuert **Zeitpläne, Solltemperaturen, Modi, Fenster- und Anwesenheitslogik** aller Räume,
- entscheidet, **wann der Kessel läuft**, so effizient und taktarm wie möglich,
- **wertet aus** (Gas → kWh, Laufzeiten, Starts, Brennwertnutzung),
- **lernt** das thermische Verhalten der Räume (spätere Phase),
- ist **sicher**: Bei Ausfällen geht der Kessel in einen definierten Zustand (**aus**).

Rahmenbedingungen:

| Punkt | Festlegung |
|---|---|
| Plattform | Home Assistant OS, HA 2026.8+, Python 3.14 |
| Form | Custom Integration (`custom_components/heat_conductor`), später über HACS installierbar |
| Einrichtung | Komplett über die UI (Config Flow, Räume als Config-Subentries, Options Flow) |
| Sprachen | Deutsch + Englisch |
| Repo | GitHub, zunächst privat, später öffentlich |
| Unabhängigkeit | Nutzt ausschließlich HA-Entities, kein direkter Geräte-Zugriff. Funktioniert mit HmIP Cloud **und** lokal (RaspberryMatic/OpenCCU) |

---

## 2. Referenzanlage (anonymisiert)

Die Integration wird an einer realen Anlage entwickelt. Die installationsspezifischen Details (Entity-IDs, Gerätedaten, Messwerte) liegen in einer lokalen, nicht versionierten Datei `PLAN.local.md`.

### 2.1 Wärmeerzeuger

| Merkmal | Wert |
|---|---|
| Gerät | Vaillant-Gas-Brennwertkessel (bodenstehend, ältere Generation) |
| Art | **nur Heizung** (kein Warmwasser) |
| Leistung | modulierend; die **Mindestleistung liegt in der Übergangszeit über dem Wärmebedarf** |
| Wasserinhalt | groß (hohe thermische Trägheit, gut für Restwärmenutzung) |
| Regler heute | witterungsgeführter Vaillant-Einbauregler |
| Pumpe | wird vom **Kessel** gesteuert |

Typische Vaillant-Anschlussleiste:

| Klemme | Zustand | Nutzung im Projekt |
|---|---|---|
| **3-4-5 „RT 230V~“** | 3-4 gebrückt | **Relaiskontakt ersetzt die Brücke** (230 V!) |
| 7-8-9 „RT 24V“ | frei | Reserve (spätere Vorlauftemperatur-Vorgabe möglich) |
| Anl.-Therm. | gebrückt | unverändert |
| Pumpe | belegt | unverändert |
| X6 (Diagnose) | frei | **ESPHome-Diagnose (nur lesen)** |

**Wichtig:** Weil die kleinste Brennerleistung über dem Wärmebedarf der Übergangszeit liegt, **muss** der Kessel dann takten. Deshalb hat die Takt-Logik höchste Priorität.

### 2.2 Räume

| Raumtyp | Ausstattung | Rolle |
|---|---|---|
| Geregelte Räume (mehrere) | je 1–2 HomematicIP-Heizkörperthermostate, meist ein zusätzlicher Raumsensor (Zigbee, Bluetooth oder ESPHome) | erzeugen Wärmebedarf |
| Raum mit großer Glasfläche | 2 Thermostate, starke Sonnengewinne/Verluste | eigene Parameter, später Sonnen-Proxy |
| Raum mit Handventil | kein Thermostat, Raumsensor | nur überwachen |
| Flur o. ä. | ohne Heizkörper | – |

Die HmIP-Integration liefert je Thermostat eine Climate-Entity (Soll-/Ist-Temperatur) und einen Sensor mit der Ventilöffnung in % (`sensor.…_heating`).

### 2.3 Weitere Datenquellen

| Zweck | Quelle |
|---|---|
| Außentemperatur | mehrere Zigbee-Sensoren, Wetter-Integration als Fallback |
| Vor-/Rücklauf | ESPHome |
| Gas | ESPHome-Impulszähler |
| Kesseldiagnose | ESPHome über X6, eigenes Projekt [esphome-vaillant-x6](https://github.com/MYF540/esphome-vaillant-x6) (Testkessel antwortet seit 17.09.2026, Adressraum kartiert) |
| HmIP-Funklast | Duty-Cycle-Sensor des Access Points |
| Sonneneinstrahlung (Proxy) | Leistung einer PV-Anlage (optional) |
| Anwesenheit | HA `person`-Entities |
| Gaswerte | Brennwert und Zustandszahl laut Gasabrechnung (konfigurierbar) |

### 2.4 Erkenntnisse aus der Bestandsaufnahme

- Batteriebetriebene Thermostate/Sensoren können **wochenlang unerreichbar** sein, während der letzte Wert (z. B. eine Ventilöffnung) stehen bleibt → Veraltet-Erkennung ist Pflicht.
- Die HmIP-Cloud-Verbindung fällt gelegentlich aus → Ausfälle müssen sauber behandelt werden.
- HmIP-eigene Zeitprofile und „Optimum Start/Stop“ werden später deaktiviert, damit keine zwei Logiken gegeneinander arbeiten.

---

## 3. Hardware-Umbau (Variante B + X6)

### 3.1 Zielbild

```
                    ┌──────────────── Vaillant-Gaskessel ─────────────┐
 HA ──WLAN── Relais │ Klemme 3-4 (230 V, RT) ◄── potentialfreier Kontakt│
          (Dose     │                          ◄── Handschalter parallel│
          außerhalb)│ Einbauregler (Heizkurve, Dauerbetrieb „Heizen“)   │
                    │ Buchse X6 ──► ESPHome-Diagnose (nur lesen) ──WLAN─┼─► HA
                    │ Pumpe (kesselgesteuert, aus bei Sperre)           │
                    └──────────────────────────────────────────────────┘
 ESPHome: Vorlauf, Rücklauf, Gasimpulse ─────────────────────────────────► HA
```

### 3.2 Komponenten

| Komponente | Anforderung / Empfehlung |
|---|---|
| Relais | **Shelly 1 Gen3/Gen4** oder **Shelly Pro 1**: potentialfreier Kontakt, 230 V geeignet, Gen2+ für Skripte (**keine PM-Variante**) |
| Einbau | Eigene Abzweigdose **außerhalb** des Kesselgehäuses, Einschaltzustand „aus“ |
| Notbetrieb | **Handschalter parallel** zum Relaiskontakt (manuelles Heizen bei Defekt) |
| Diagnose | ESPHome-Modul an X6, **nur lesend**; ausgegliedert in das Projekt [esphome-vaillant-x6](https://github.com/MYF540/esphome-vaillant-x6) |
| Montage | **Elektrofachkraft** (230 V an der Kesselplatine) |

### 3.3 Inbetriebnahme-Checkliste

1. Brücke 3-4 durch Relaiskontakt + Handschalter ersetzen.
2. Test: Kontakt offen → **Brenner stoppt** und **Pumpe stoppt nach Nachlaufzeit**.
3. Test: Kontakt geschlossen → Kessel heizt nach der Heizkurve des Einbaureglers.
4. Einbauregler auf Dauerbetrieb „Heizen“ stellen (keine eigene Zeitabsenkung mehr).
5. Kessel-Drehknopf Vorlauf als Obergrenze einstellen (z. B. 65–70 °C).
6. Relais-Watchdog-Skript aktivieren, Ausfalltest (HA stoppen → Kessel aus).

---

## 4. Funktionsumfang

### 4.1 Raumebene

**Raummodell:** Jeder Raum hat 0–n Thermostate (HmIP-Climate-Entities), optional einen Raumsensor, optional Fensterkontakte, eine Gewichtung und einen Typ:

- `geregelt`: Thermostate vorhanden, volle Steuerung.
- `nur überwachen`: z. B. Raum mit Handventil. Temperatur wird angezeigt und analysiert, erzeugt aber **keinen** Kesselbedarf.

**Effektiver Sollwert je Raum** (höchste Priorität zuerst):

1. Frostschutz (Raum < Frostgrenze)
2. Fenster offen → Fenstertemperatur
3. Boost (zeitlich begrenzt)
4. Globaler Modus: Aus / Urlaub (auch automatisch erkannt) / Abwesend / Eco / Komfort
5. Anwesenheit (niemand zu Hause → Eco)
6. Zeitplan: **HA-Zeitplan-Helfer** je Raum (`an` = Komfort, `aus` = Absenkung); ohne eigenen Helfer optional der **gelernte Anwesenheits-Zeitplan**
7. **Nutzungserkennung** (optional je Raum): genutzter Raum → Komfort, ungenutzter Raum → Absenkung. Nutzung erkennen Geräte des Raums (Fernseher, PC, Präsenzmelder), mit Nachlaufzeit

**Solltemperaturen an die Thermostate schreiben**, mit diesen Regeln (wegen Batterie und HmIP-Duty-Cycle):

- nur bei echter Änderung des effektiven Sollwerts, gerundet auf 0,5 K,
- höchstens eine automatische Änderung je Raum pro 15 min (Benutzeraktionen sofort),
- Pause aller automatischen Schreibvorgänge, wenn der Duty Cycle des Access Points über einem Grenzwert liegt,
- Rücklesen und begrenzte Wiederholung bei Fehlschlag,
- HmIP-Räume werden einmalig auf Modus „Manuell“ gestellt (HmIP-Zeitprofile ungenutzt).

**Kompensation über externe Raumsensoren:** Offset = geglättete Differenz (Thermostat-Temp. − Raumtemp.). An den Thermostat geht `Sollwert + Offset`, begrenzt auf ±3 K, und nur, wenn sich der Wert um ≥ 0,5 K ändert.

**Raumbedarf (0–100 %):** Maximum aus
- Ventilöffnung (Mittelwert über die Thermostate des Raums) und
- Temperaturdefizit (effektiver Soll − Raumtemp.), 1 K Defizit = 100 %.

Ausgeschlossen werden: veraltete Werte, offenes Fenster, Typ „nur überwachen“.

### 4.2 Erzeugerebene (Kessel)

**Gesamtbedarf** = gewichteter Mittelwert der Raumbedarfe.

**Kessel-Zustandsautomat:**

```
          Bedarf ≥ Start-Schwelle (bestätigt)
          UND Mindestpause erfüllt
  ┌─────┐ ─────────────────────────────► ┌────────┐
  │ AUS │                                │ HEIZEN │
  └─────┘ ◄───────────────────────────── └────────┘
     ▲     Bedarf ≤ Stopp-Schwelle UND Mindestlaufzeit erfüllt
     │     (oder Sicherheitsabschaltung)
     │
  Übersteuernde Zustände: FROSTSCHUTZ · FAILSAFE · MANUELL · SOMMER (Heizgrenze)
  Beobachtungsmodus: Automat rechnet, schaltet aber nicht
```

**Startwerte der Parameter** (alle einstellbar, werden im Beobachtungsmodus kalibriert):

| Parameter | Startwert |
|---|---|
| Start-Schwelle Gesamtbedarf | 25 %, 5 min bestätigt |
| Sofortstart, wenn ein Raum Defizit ≥ | 1,0 K |
| Stopp-Schwelle | 10 % |
| Mindestlaufzeit | 20 min |
| Mindestpause | 15 min |
| Max. Starts pro Stunde | 3 |
| Heizgrenze (Außentemp. geglättet 24 h) | 16 °C |
| Frostgrenze Raum | 6 °C |

**Außentemperatur:** Kombination der gültigen Sensoren (Plausibilitätsgrenzen, Ausreißer bei Sonneneinstrahlung erkennen), Fallback auf die Wetter-Integration.

**Pumpe aus bei Sperre:** Vor- und Rücklaufwerte gelten in Pausen als **nicht repräsentativ** und werden dann nicht für Regelentscheidungen genutzt.

**X6-Diagnose** (sobald verfügbar): Brenner an/aus, Kessel-Vorlauf, Status- und Fehlercodes. Damit wird geprüft: Relais an, aber Brenner aus (Kessel-Temperaturgrenze erreicht)? Fehlercode → Benachrichtigung.

### 4.3 Sicherheit

| Regel | Verhalten |
|---|---|
| Pflichtdaten fehlen (alle Räume veraltet, Relais nicht erreichbar) | **Kessel aus**, Benachrichtigung, Reparatur-Hinweis in HA |
| Einzelner Raum veraltet | Raum wird aus dem Bedarf ausgeschlossen, Hinweis |
| Veraltet-Erkennung | `unavailable`/`unknown`, `last_reported` älter als Grenzwert (je Sensortyp einstellbar) |
| Takt-Schutz | Mindestlaufzeit, Mindestpause, Max. Starts/h, nie verletzbar außer durch Failsafe |
| Übertemperatur | Vorlauf > Grenzwert → Kessel aus |
| Frostschutz | Raum < Frostgrenze → Heizen (sofern Daten vorhanden) |
| Manuelles Schalten erkannt | Automatik pausiert für einstellbare Zeit, Hinweis |
| HA-Neustart | Start im sicheren Zustand (aus), bis gültige Daten vorliegen |
| HA/WLAN-Ausfall | Shelly-Watchdog-Skript → Kontakt aus |

### 4.4 Analyse

- Gas: Impulse → m³ → **kWh** (Brennwert × Zustandszahl), Einbindung ins Energie-Dashboard.
- Brennerleistung (kW) und **Modulation (%)** aus dem Gasdurchfluss (Leistungsbereich des Kessels).
- Starts und Laufzeit (heute / gesamt), mittlere Laufzeit je Start.
- Spreizung Vor-/Rücklauf, **Brennwert-Anzeige** (Rücklauf unter Taupunkt-Richtwert).
- Verbrauch je Gradtag (Vergleichbarkeit zwischen Tagen/Wintern).
- Sensor **„Entscheidungsgrund“** (z. B. „Bad −1,2 K, Ventil 80 % → Start“).

### 4.5 Lernen und Vorausschau (spätere Phase)

- Thermisches Modell je Raum: Aufheizrate (abhängig von Außentemp.), Auskühlrate.
- **Optimum Start:** Komfortzeitpunkt wird erreicht, nicht erst begonnen.
- **Restwärme:** Frühzeitiger Stopp, wenn alle Räume nah am Soll sind.
- Wettervorhersage (Kälteeinbruch → früher starten, Sonne → später).
- PV-Leistung als Sonnen-Proxy für die Wärmegewinne in Räumen mit großen Glasflächen.
- Lerndaten persistent (HA-Storage), zurücksetzbar.

---

## 5. Entities der Integration

**Global (Gerät „HeatConductor“):**

| Entity | Zweck |
|---|---|
| `select.heat_conductor_betriebsmodus` | Auto / Komfort / Eco / Abwesend / Urlaub / Frostschutz / Aus |
| `switch.heat_conductor_automatik` | Steuerung aktiv |
| `switch.heat_conductor_beobachtungsmodus` | Rechnen ohne Schalten |
| `binary_sensor.heat_conductor_waermeanforderung` | Kessel angefordert |
| `binary_sensor.heat_conductor_brenner_aktiv` | Brenner brennt (Gas/X6) |
| `binary_sensor.heat_conductor_stoerung` | Failsafe / Sensorfehler |
| `sensor.heat_conductor_kesselstatus` | Zustand des Automaten |
| `sensor.heat_conductor_gesamtbedarf` | % |
| `sensor.heat_conductor_entscheidungsgrund` | Klartext |
| `sensor.heat_conductor_aussentemperatur` | kombinierter Wert |
| `sensor.heat_conductor_gas_energie` | kWh (Energie-Dashboard) |
| `sensor.heat_conductor_brennerleistung` / `_modulation` | kW / % |
| `sensor.heat_conductor_starts_heute` / `_laufzeit_heute` | Takt-Kontrolle |
| `sensor.heat_conductor_spreizung` | K |

**Je Raum (eigenes Gerät):**

| Entity | Zweck |
|---|---|
| `climate.heat_conductor_<raum>` | Virtueller Raumthermostat (Ist = Raumsensor, Soll = Übersteuerung, Aktion heizt/idle) |
| `sensor.…_bedarf` | % |
| `sensor.…_effektiver_sollwert` | inkl. Grund (Attribut) |
| `number.…_komfort` / `_absenkung` | Temperaturen |
| `binary_sensor.…_fenster_offen` | kombiniert |

**Dienste:** `heat_conductor.boost`, `heat_conductor.set_vacation`, `heat_conductor.reset_learning`, `heat_conductor.force_boiler` (Test/Wartung, zeitlich begrenzt).

---

## 6. Architektur

### 6.1 Schichten

```
┌─ HA-Adapter ─────────────────────────────────────────────────────┐
│ Config Flow · Subentries (Räume) · Entities · Dienste · Storage   │
│ Coordinator: reagiert auf State-Changes + Takt alle 30 s          │
└──────────────┬───────────────────────────────────────▲────────────┘
     Snapshot (reine Daten)                    Aktionen (Soll, Relais)
┌──────────────▼───────────────────────────────────────┴────────────┐
│ core/ (reines Python, ohne HA-Abhängigkeit → vollständig testbar)  │
│ rooms · setpoint · demand · boiler_fsm · safety · outdoor ·        │
│ energy · throttle · (später) thermal_model                         │
└────────────────────────────────────────────────────────────────────┘
```

Wärmeerzeuger-Stellglied als austauschbarer Adapter: `SwitchActuator` (jetzt) und `FlowSetpointActuator` (später, z. B. 7-8-9 oder eBUS).

### 6.2 Projektstruktur

```
custom_components/heat_conductor/
  __init__.py  manifest.json  const.py
  config_flow.py            # Kessel, Sensoren, Parameter; Räume als Subentries
  coordinator.py
  core/
    models.py  rooms.py  setpoint.py  demand.py  boiler_fsm.py
    safety.py  outdoor.py  energy.py  throttle.py
  actuators/  switch.py  (flow_setpoint.py später)
  climate.py  sensor.py  binary_sensor.py  switch.py  select.py  number.py
  services.yaml  diagnostics.py  repairs.py
  strings.json  translations/de.json  translations/en.json
tests/
  core/        # Unit-Tests der Logik
  ha/          # pytest-homeassistant-custom-component
sim/           # Haus-/Kessel-Simulator, Wiedergabe echter HA-Historie
.github/workflows/  # ruff, mypy, pytest, hassfest, HACS-Validierung
hacs.json  README.md  PLAN.md  LICENSE
```

### 6.3 Entwicklung und Test

- Lokal (Windows, VS Code): Python-3.14-Umgebung, Unit-Tests und Simulator.
- Deployment während der Entwicklung: per Samba- oder SSH-App nach `/config/custom_components/`, HACS ab Veröffentlichung.
- **Neue Logik läuft immer zuerst im Beobachtungsmodus**, bevor sie schalten darf.

---

## 7. Umsetzungsphasen

| Phase | Inhalt | Abnahmekriterium |
|---|---|---|
| **0 Vorbereitung** | Erreichbarkeit/Batterien aller Geräte prüfen, Gasimpulszähler aktiv (mit Zählerstand), offene Entity-IDs klären, X6-Kompatibilität recherchieren, Git-Repo privat anlegen | Alle Pflicht-Entities liefern Werte |
| **1 Fundament + Beobachtung** | Config Flow + Räume, Außentemp.-Kombination, Veraltet-Erkennung, Raumbedarf, Kessel-Automat **im Beobachtungsmodus**, Entscheidungsgrund, Diagnose, Tests | 2 Wochen stabil, Entscheidungen nachvollziehbar, Vergleich mit realem Brennerbetrieb |
| **2 Analyse** | Gas → kWh, Leistung/Modulation, Starts/Laufzeit, Spreizung, Brennwert-Anzeige, Energie-Dashboard | kWh ±5 % zum Gaszähler |
| **3 Kessel aktiv** | Hardware-Umbau (Abschnitt 3), Switch-Adapter, Sicherheitsregeln scharf, Shelly-Watchdog; parallel X6-Diagnose | Checkliste 3.3 bestanden, keine Takt-Verletzungen, Failsafe-Tests bestanden |
| **4 Raumsteuerung** | Zeitpläne, Modi, Anwesenheit, Fenster, Boost, gedrosseltes Schreiben der Sollwerte, Sensor-Kompensation, virtuelle Climate-Entities; HmIP auf Manuell, Optimum Start/Stop aus | Sollwerte korrekt, Duty Cycle unkritisch, Räume erreichen Komfort |
| **5 Lernen + Vorausschau** | Thermisches Modell, Optimum Start, Restwärme, Wetter, PV-Proxy | Messbar weniger Starts / Gas bei gleichem Komfort |
| **6 Veröffentlichung** | Doku, Beispiele, HACS-Validierung, Repo öffentlich | HACS-Installation auf frischer Instanz funktioniert |
| *Option* | Vorlauftemperatur-Vorgabe über 7-8-9 (Einbauregler entfällt) | – |
| *Geplant* | **HeatConductor-Panel** in der HA-Seitenleiste, Teile A–D (Abschnitt 12) – noch nicht terminiert | siehe Abschnitt 12.8 |

---

## 8. Risiken

| Risiko | Gegenmaßnahme |
|---|---|
| HmIP-Cloud-Ausfälle / Verzögerung | Veraltet-Erkennung, Failsafe, Option RaspberryMatic |
| Takten wegen hoher Mindestleistung | Takt-Logik, Bedarf bündeln, Restwärme |
| Batterie / Duty Cycle der Thermostate | Gedrosseltes Schreiben, Duty-Cycle-Überwachung |
| X6 nicht kompatibel | Rein optional, Brennerstatus alternativ über Gasdurchfluss |
| Einbauregler und HeatConductor arbeiten gegeneinander | Einbauregler nur für Heizkurve, Zeitprogramm auf Dauerbetrieb |
| Fehlfunktion im Winter | Beobachtungsmodus zuerst, Handschalter, Benachrichtigungen |
| 230-V-Arbeiten | Ausschließlich durch Elektrofachkraft |
| Panel bricht nach HA-Frontend-Updates | Nur öffentliche Schnittstellen nutzen (WebSocket-API, `hass`-Objekt), eigene Diagramm-Bibliothek, keine internen HA-Komponenten |
| Gelernte Werte verfälscht, solange HmIP/Einbauregler steuern | Lernen erst mit aktiver Steuerung scharf nutzen; Stichprobenzahl und Streuung immer anzeigen |
| Parameter per Panel auf unsichere Werte gestellt | Serverseitige Bereichsprüfung, Sicherheitsregeln nicht abschaltbar, Änderungsprotokoll, „Auf Standard zurücksetzen“ |

---

## 9. Bewusst nicht im Umfang (vorerst)

- Warmwasser (nicht vorhanden)
- Eigene Lovelace-Karte für Zeitpläne (spätere Erweiterung)
- Modellprädiktive Regelung (MPC)
- Kühlung

---

## 10. Entscheidungsprotokoll

| Datum | Entscheidung |
|---|---|
| 2026-09-14 | Custom Integration, via HACS; Name **HeatConductor** (`heat_conductor`) |
| 2026-09-14 | All-in-one: Räume + Kessel |
| 2026-09-14 | Failsafe: Kessel **aus** |
| 2026-09-14 | Hardware **Variante B** (Relais an 3-4, Einbauregler liefert Heizkurve) + X6-Diagnose |
| 2026-09-14 | Pumpe darf bei Sperre stoppen |
| 2026-09-14 | Zeitpläne v1 über HA-Zeitplan-Helfer (Komfort/Absenkung) |
| 2026-09-14 | Anwesenheit über HA-Personen |
| 2026-09-14 | Gaswerte (Brennwert, Zustandszahl) konfigurierbar |
| 2026-09-14 | Plan freigegeben, Umsetzung Phase 1 gestartet |
| 2026-09-14 | Tests der HA-Schicht laufen in Docker (HA läuft nicht nativ unter Windows) |
| 2026-09-14 | Panel in der Seitenleiste geplant (Teile A–D), vorerst nur Planung, keine Umsetzung |
| 2026-09-14 | Panel: alle Nutzer sehen, nur Admins ändern Parameter |
| 2026-09-14 | Panel: Was-wäre-wenn-Simulation (Teil D) wird mit eingeplant |
| 2026-09-14 | Lernen (Teil C) wird noch nicht gestartet, nur festgehalten |
| 2026-09-14 | Panel zweisprachig Deutsch/Englisch |
| 2026-09-14 | Phase 2 gestartet und umgesetzt: Gas m³/kWh (Zählerstand bevorzugt), Leistung/Modulation, Brennwertnutzung, Gradtage VDI 3807 (20/15) |
| 2026-09-14 | Gesamte Softwareseite umgesetzt: Watchdog, Reparaturhinweise, Raumsteuerung, Lernen, Vorausschau, Panel A–D |
| 2026-09-14 | Raumsteuerung nach Installation standardmäßig aus (eigener Schalter) |
| 2026-09-14 | Panel als abhängigkeitsfreie Web-Component ohne Build (statt Lit/TypeScript): kein Node-Build, offline lauffähig |
| 2026-09-14 | Was-wäre-wenn für alle Nutzer lesend erlaubt, bis 168 h; Änderungsprotokoll hält die letzten 500 Einträge |
| 2026-09-18 | Rückmeldungen vom Kessel als optionale Eingänge (Relais-Rückmeldung, Brennersperrzeit, Winterbetrieb, Pumpe, Kesselfühler Vor-/Rücklauf); Rohrfühler werden gegen den Kesselfühler mit gelerntem Versatz geprüft |
| 2026-09-17 | Automatischer Urlaub: 2 Tage ohne Anwesenheit startet ihn, 3 h Anwesenheit beendet ihn; währenddessen kein Lernen des Anwesenheitsplans |
| 2026-09-17 | Nutzungsbasiertes Heizen je Raum (Geräte als Nutzungsmelder, Komfort/Eco, je Raum abschaltbar) und gelernter Anwesenheits-Zeitplan als globaler Vorschlag |
| 2026-09-15 | X6-Anbindung in eigenes Projekt `esphome-vaillant-x6` ausgegliedert (Kessel antwortet bisher nicht, Tests dort dokumentiert); HeatConductor-ESP nur noch mit Vor-/Rücklauf |

---

## 11. Offene Detailfragen

Installationsspezifische offene Punkte (Zuordnung von Sensoren zu Räumen, Entity-IDs,
Impulswertigkeit des Gaszählers) werden in `PLAN.local.md` gepflegt.

---

## 12. Erweiterung: HeatConductor-Panel (geplant, noch nicht umgesetzt)

> Status: **nur Planung**. Umsetzung erst nach gesonderter Freigabe.

### 12.1 Ziel

Ein eigener Menüpunkt **„HeatConductor“** in der linken HA-Seitenleiste (neben Dashboards und Apps), der

- die **Regelparameter verständlich erklärt und einstellbar** macht,
- **live zeigt, warum** der Kessel an oder aus ist,
- **visualisiert, was der Algorithmus lernt**,
- per **Was-wäre-wenn** die Wirkung geänderter Parameter vorab zeigt.

### 12.2 Rahmen und Entscheidungen

| Punkt | Festlegung |
|---|---|
| Einbindung | Registrierung durch die Integration selbst als Custom Panel (Seitenleiste), keine separate Installation; funktioniert über HACS |
| Rechte | **Alle Nutzer sehen** das Panel, **nur Admins ändern** Parameter und setzen Lerndaten zurück (serverseitig geprüft) |
| Sprache | Deutsch + Englisch (folgt der HA-Spracheinstellung) |
| Frontend | Web-Component mit Lit + TypeScript, eigene gebündelte Diagramm-Bibliothek; gebaute JS-Datei liegt im Repo, Build in Docker |
| Datenzugriff | WebSocket-API der Integration; Verläufe direkt aus dem HA-Recorder |
| Parameter | Änderungen wirken **sofort ohne Neuladen** der Integration; bisheriger Options-Dialog bleibt als Rückfallweg |

### 12.3 Teil A – Parameter transparent und einstellbar

**Aufbau:** Gruppen mit Karten je Parameter. Jede Karte zeigt Erklärung, Einheit, erlaubten Bereich, Standard- und aktuellen Wert, Wirkungshinweis und – wo sinnvoll – eine kleine Skizze.

| Gruppe | Parameter | Erklärung | Wirkung „höher“ |
|---|---|---|---|
| Start/Stopp | Start-Schwelle (%) | Gewichteter Bedarf aller Räume, ab dem der Kessel starten darf | Weniger, dafür längere Brennerläufe; Räume kühlen etwas stärker aus |
| Start/Stopp | Bestätigungszeit (min) | So lange muss der Bedarf über der Start-Schwelle liegen | Kurze Bedarfsspitzen (z. B. Lüften) lösen keinen Start aus; Reaktion träger |
| Start/Stopp | Stopp-Schwelle (%) | Unter diesem Bedarf darf der Kessel ausgehen | Kessel geht früher aus, Restwärme wird stärker genutzt |
| Start/Stopp | Sofortstart ab Raumdefizit (K) | Liegt ein Raum so weit unter Soll, startet der Kessel ohne Bestätigung | Seltener Sofortstarts, einzelne kalte Räume warten länger |
| Start/Stopp | Defizit für 100 % Raumbedarf (K) | Umrechnung Temperaturdefizit → Raumbedarf | Defizite wirken schwächer, Ventilöffnung dominiert |
| Takt-Schutz | Mindestlaufzeit (min) | Kürzeste Brennerlaufzeit nach einem Start | Weniger Takten, mögliche Überschwinger der Raumtemperatur |
| Takt-Schutz | Mindestpause (min) | Kürzeste Pause zwischen zwei Starts | Weniger Starts, längere Wartezeit bei neuem Bedarf |
| Takt-Schutz | Max. Starts pro Stunde | Harte Obergrenze für Starts | Mehr Flexibilität, mehr Verschleiß |
| Heizgrenze & Frost | Heizgrenze (°C) | Über dieser geglätteten Außentemperatur bleibt der Kessel aus (außer Komfort/Frost) | Heizt auch an milderen Tagen |
| Heizgrenze & Frost | Glättung Außentemperatur (h) | Zeitkonstante der Glättung für die Heizgrenze | Kurze Warm-/Kaltphasen ändern den Modus weniger |
| Heizgrenze & Frost | Frostschutz-Raumtemperatur (°C) | Unterschreitet ein Raum diesen Wert, heizt der Kessel immer | Frostschutz greift früher |
| Sicherheit | Max. Vorlauftemperatur (°C) | Darüber sofortige Abschaltung | Abschaltung erst bei höherer Temperatur |
| Sicherheit | Werte veraltet nach (min) | Ältere Messwerte werden ignoriert | Toleranter bei selten sendenden Sensoren, erkennt Ausfälle später |
| Sicherheit | Pause nach manuellem Schalten (min) | So lange respektiert die Automatik ein manuelles Schalten | Längere Übersteuerung durch den Nutzer |
| Sensorik | Brenner-an-Schwelle Gasdurchfluss (m³/h) | Ab diesem Durchfluss gilt der Brenner als an | Kurzes Zünden/Nachlaufen wird nicht als Start gezählt |

**Skizzen:** Bedarfsverlauf mit Start-/Stopp-Schwelle und Bestätigungszeit; Zeitstrahl mit Mindestlaufzeit/-pause; Heizgrenze auf Außentemperaturkurve.

**Funktionen:** Bereichsprüfung (Client und Server), Speichern nur für Admins, „Auf Standard zurücksetzen“ (je Parameter/alle), **Änderungsprotokoll** (Zeit, Nutzer, Parameter, alt → neu, persistent).

### 12.4 Teil B – Live-Ansicht und Verlauf

- **Zustandsautomat als Grafik**: Zustände Aus/Heizt/Frostschutz/Sommer/Manuell/Sicherheitsabschaltung, aktueller Zustand hervorgehoben, Entscheidungsgrund im Klartext.
- **Restzeiten als Fortschrittsbalken**: Bestätigung, Mindestlaufzeit, Mindestpause, Starts in der letzten Stunde.
- **Gesamtbedarf** als Anzeige mit Start-/Stopp-Schwelle.
- **Raumtabelle**: Bedarf, Anteil Ventil vs. Defizit, Soll/Ist, Gewichtung, Datenstatus.
- **Zeitverlauf (24 h / 7 Tage)**: Gesamtbedarf mit Schwellen, virtuelle Anforderung vs. realer Brennerbetrieb, Außentemperatur (roh/geglättet), Vor-/Rücklauf, Markierung von Parameteränderungen.

### 12.5 Teil C – Lernen und Visualisierung

**Status: nur festgehalten, Lernen wird noch nicht gestartet.**

| Gelernt | Datengrundlage | Verfahren (Entwurf) | Visualisierung | Späterer Nutzen |
|---|---|---|---|---|
| Aufheizrate je Raum (K/h) | Raumtemperatur bei Brenner an + Ventil offen | Steigung je Heizphase, gruppiert nach Außentemperatur | Wert + Streudiagramm gegen Außentemperatur | Rechtzeitiger Start (Optimum Start) |
| Auskühl-Zeitkonstante je Raum (h) | Temperaturabfall ohne Heizen | Exponentieller Fit auf (T_innen − T_außen) | Abkühlkurve mit Fit | Absenkung/Restwärme, Vorausschau |
| Totzeit je Raum (min) | Ventil auf → erster messbarer Anstieg | Median über Ereignisse | Wert + Verteilung | Vermeidung von Überschwingern |
| Brennerzyklen | Brenner an/aus (X6/Gas), Außentemperatur | Laufzeit-/Pausen-Statistik je Temperaturband | Histogramm, Takt-Kennzahlen | Kalibrierung Takt-Schutz |
| Heizkurve des Einbaureglers | Vorlauf-Soll (X6) vs. Außentemperatur | Lineare Regression | Kurve + Messpunkte | Kontrolle / spätere eigene Vorlaufvorgabe |

- Jeder gelernte Wert mit **Stichprobenzahl, Streuung und Stand** (Datum der letzten Aktualisierung).
- **Lernverlauf**: Stabilisierung der Werte über die Zeit.
- **Zurücksetzen** je Raum oder komplett (nur Admins).
- Speicherung persistent im HA-Storage; Plausibilitätsgrenzen gegen Ausreißer (offene Fenster, Sensorsprünge).

### 12.6 Teil D – Was-wäre-wenn

- Admin/Nutzer ändert Parameter im Panel **als Entwurf** → Server spielt die **aufgezeichneten Eingangsdaten der letzten 24 h** (optional 7 Tage) mit den Entwurfswerten durch den unveränderten Regelkern.
- Ergebnis im Vergleich **aktuell vs. Entwurf**: Starts, Brennerlaufzeit, Anteil Zeit mit Raum-Defizit > 0,5 K, Verlaufsdiagramm beider Varianten.
- Eingangsdaten aus dem Recorder; der Regelkern ist bereits HA-unabhängig und damit direkt wiederverwendbar.
- Grenzen klar anzeigen: Simulation ohne Rückwirkung auf die Raumtemperaturen (echte Temperaturen bleiben die aufgezeichneten); belastbar vor allem für Starts/Laufzeiten.

### 12.7 Technischer Entwurf

**Backend (Integration):**

| Baustein | Aufgabe |
|---|---|
| `panel.py` | Registriert statischen Pfad für die JS-Datei und das Custom Panel (Titel, Icon `mdi:radiator`, URL `heat-conductor`) |
| `websocket_api.py` | Befehle `heat_conductor/state`, `…/params/get` (inkl. Metadaten), `…/params/set` (Admin), `…/params/reset` (Admin), `…/changelog`, `…/learning/get`, `…/learning/reset` (Admin), `…/simulate` |
| `core/params_meta.py` | Eine Quelle für Bereich, Einheit, Standardwert, Gruppe und Übersetzungsschlüssel aller Parameter (auch für Options-Dialog) |
| Coordinator | Parameter live übernehmen (ohne Reload), Änderungsprotokoll speichern |
| `core/learning/…` | Lernverfahren aus 12.5 (später) |
| `core/simulation.py` | Wiedergabe von Eingangsdaten durch die Engine (Teil D) |

**Frontend (`frontend/`):** Lit + TypeScript, Build per Docker (Node-Image), Ausgabe `custom_components/heat_conductor/frontend/heat-conductor-panel.js`. Ansichten als Reiter: *Übersicht* · *Parameter* · *Lernen* · *Was-wäre-wenn* · *Protokoll*. Theme-Farben aus HA übernehmen (hell/dunkel).

**Tests:** WebSocket-Befehle inkl. Rechteprüfung (pytest), Parameter-Validierung, Simulation gegen bekannte Szenarien, Frontend-Build in CI.

### 12.8 Reihenfolge und Abnahme

| Schritt | Inhalt | Abnahmekriterium |
|---|---|---|
| A | Panel-Grundgerüst, Parameter-Editor, Rechte, Änderungsprotokoll, Live-Übernahme | Nutzer sehen, nur Admins ändern; Änderungen wirken ohne Neuladen; Protokoll vollständig |
| B | Live-Ansicht, Zustandsgrafik, Raumtabelle, Verlaufsdiagramme | Jede Kesselentscheidung im Panel nachvollziehbar |
| D | Was-wäre-wenn auf Recorder-Daten | Simulation mit aktuellen Parametern reproduziert die realen Entscheidungen der letzten 24 h |
| C | Lernverfahren + Visualisierung (sinnvoll zusammen mit Phase 5) | Werte stabilisieren sich, Streuung plausibel, Zurücksetzen funktioniert |

### 12.9 Offene Punkte zum Panel

1. Umfang Was-wäre-wenn: nur 24 h oder wählbar bis 7 Tage (Rechenzeit auf dem Thin Client prüfen).
2. Sollen Nicht-Admins Entwürfe simulieren dürfen (ohne Speichern)?
3. Aufbewahrungsdauer des Änderungsprotokolls.
