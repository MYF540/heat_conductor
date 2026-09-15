<p align="center">
  <img src="custom_components/heat_conductor/brand/logo@2x.png" alt="HeatConductor" width="325">
</p>

# HeatConductor

Intelligente Heizungssteuerung für Home Assistant: HeatConductor wertet Thermostate,
Raum- und Außensensoren aus, steuert Solltemperaturen und Zeitpläne der Räume und
entscheidet, wann der Kessel laufen soll – mit Schutz gegen Takten, Sicherheitsabschaltung,
Lernfunktionen und nachvollziehbaren Entscheidungen im eigenen Panel.

> **Sicher starten:** Nach der Installation ist der **Beobachtungsmodus** aktiv (der Kessel
> wird nicht geschaltet) und die **Raumsteuerung** ist aus (es werden keine Solltemperaturen
> an Thermostate geschrieben). Beides schaltest du bewusst ein, wenn die Entscheidungen passen.
> Den Projektplan enthält [PLAN.md](PLAN.md).

## Funktionen

**Kessel**
- Wärmebedarf je Raum aus Ventilöffnung und Temperaturdefizit, gewichteter Gesamtbedarf
- Zustandsautomat mit Bestätigungszeit, Mindestlaufzeit, Mindestpause, max. Starts pro Stunde
- Restwärme nutzen: Brenner stoppt, wenn alle Räume über Soll liegen
- Heizgrenze auf geglätteter Außentemperatur, aufgehoben bei kalter Wettervorhersage
- Sicherheit: veraltete Werte, Sicherheitsabschaltung ohne Daten, Übertemperatur, Frostschutz,
  Erkennung manuellen Schaltens, **Relais-Watchdog** auf dem Shelly, **Reparaturhinweise** in HA

**Räume**
- Virtueller **Raumthermostat** je Raum (Soll, Ist, Boost, Komfort/Eco, Aus)
- Solltemperatur nach Priorität: Fenster offen → Raum aus → Boost → manuelle Übersteuerung →
  Modus (Aus, Frostschutz, Urlaub, Abwesend, Eco, Komfort) → Anwesenheit → Zeitplan
- **Optimaler Start:** Aufheizen beginnt so früh, dass zum Zeitplanbeginn Komfort erreicht ist
- Schreiben an Thermostate gedrosselt (Mindestabstand, Funk-Duty-Cycle), Korrektur über
  externe Raumsensoren, Übernahme von Handänderungen am Thermostat als Übersteuerung
- Sonnen-Proxy über PV-Leistung für Räume mit großen Glasflächen

**Energie und Analyse**
- Gasverbrauch in m³ und kWh (Energie-Dashboard), Brennerleistung, Modulation
- Brennwertnutzung, Spreizung, Starts und Laufzeiten
- Gradtagzahl (VDI 3807) und Energie je Gradtag

**Lernen**
- Aufheizrate je Raum (nach Außentemperatur), Auskühl-Zeitkonstante, Totzeit
- Brennerzyklen, Heizkurve des Kesselreglers
- Jeder Wert mit Anzahl Messungen und Streuung

**Panel „HeatConductor“ in der Seitenleiste**
- *Übersicht:* Zustandsautomat, Grund, Zeitschutz, Räume, Verläufe (24 h / 7 Tage)
- *Parameter:* jeder Parameter erklärt, mit Wirkung, Standard, Bereich; Änderungen wirken sofort
- *Lernen:* gelernte Werte, Diagramme, Lernverlauf
- *Was-wäre-wenn:* aufgezeichnete Daten mit geänderten Parametern durchspielen
- *Protokoll:* wer hat wann welchen Parameter geändert
- Alle Nutzer sehen das Panel, nur Administratoren ändern Parameter oder Lerndaten.

## Installation

### Über HACS (empfohlen)

1. *HACS → ⋮ (oben rechts) → Benutzerdefinierte Repositories*
2. Repository `https://github.com/MYF540/heat_conductor`, Typ **Integration**, hinzufügen.
3. *HeatConductor* in HACS öffnen → **Herunterladen**.
4. Home Assistant neu starten.
5. *Einstellungen → Geräte & Dienste → Integration hinzufügen → HeatConductor*.

### Manuell

Ordner `custom_components/heat_conductor` nach `/config/custom_components/` kopieren,
Home Assistant neu starten und die Integration wie oben hinzufügen.

## Einrichtung

1. **Zentrale Entitäten** (*Konfigurieren → Zentrale Entitäten*): Außensensoren oder
   Wetter-Entität (Pflicht), optional Kessel-Relais, Vor-/Rücklauf, Gaszählerstand und/oder
   Gasdurchfluss, Brenner-Sensor, Watchdog-URL, Anwesenheit, Duty-Cycle-Sensor,
   Vorlauf-Soll des Kesselreglers (Heizkurve), PV-Leistung.
2. **Räume** (*Raum hinzufügen*): Thermostate (Climate), Sensoren Ventilöffnung
   (HomematicIP: `sensor.…_heating`), Raumtemperatur-Sensor, Fensterkontakte, Zeitplan-Helfer,
   Gewichtung, Sensorkorrektur, Sonnengewinne. Räume ohne Thermostat als „Nur überwachen“.
3. **Parameter**: im Panel unter *Parameter* oder unter *Konfigurieren* (Regelparameter,
   Energie und Gas, Raumsteuerung, Lernen und Vorausschau).
4. **Beobachten:** einige Tage die Entscheidungen im Panel mit dem echten Brennerbetrieb
   vergleichen, Parameter anpassen (die Was-wäre-wenn-Simulation hilft dabei).
5. **Raumsteuerung einschalten** (Schalter *Raumsteuerung*): HeatConductor schreibt ab jetzt
   Solltemperaturen und stellt HomematicIP-Thermostate auf manuellen Modus.
   Eigene Zeitprofile und „Optimum Start/Stop“ in der HmIP-App dann deaktivieren.
6. **Kessel übernehmen** (Beobachtungsmodus aus): erst nach Einbau des Relais und des
   Watchdogs (siehe unten).

### Zeitpläne

Pro Raum einen **Zeitplan-Helfer** anlegen (*Einstellungen → Geräte & Dienste → Helfer →
Zeitplan*): *an* = Komforttemperatur, *aus* = Eco-Temperatur. Komfort- und Eco-Temperatur
stellst du je Raum an den Zahlen-Entitäten ein.

### Relais-Watchdog (Shelly)

Das Skript [shelly/heatconductor_watchdog.js](shelly/heatconductor_watchdog.js) läuft auf dem
Shelly (Gen2+). HeatConductor sendet jede Minute einen Heartbeat. Steuert HeatConductor den
Kessel und bleiben die Heartbeats 10 Minuten aus, schaltet der Shelly das Relais ab.

1. Shelly-Weboberfläche → *Scripts* → *Create script* → Skript einfügen → speichern,
   starten und *Run on startup* aktivieren.
2. In HeatConductor unter *Zentrale Entitäten* die URL eintragen:
   `http://<IP-des-Shelly>/script/<Skript-Nr.>/heartbeat`
3. Die Entität *Relais-Watchdog* zeigt, ob der Shelly erreichbar ist.

### Gaszähler mit ESPHome

Ein Reed-Kontakt am Gaszähler liefert Impulse (häufig 0,01 m³ je Impuls, siehe Zähler).
Mit `pulse_meter` entstehen Durchfluss und Zählerstand:

```yaml
sensor:
  - platform: pulse_meter
    pin:
      number: GPIO5
      mode: INPUT_PULLUP
    name: "Gasdurchfluss"
    unit_of_measurement: "m³/h"
    accuracy_decimals: 3
    internal_filter: 100ms
    filters:
      - multiply: 0.6 # Impulse/min × 0,01 m³ × 60
    total:
      name: "Gaszählerstand"
      unit_of_measurement: "m³"
      device_class: gas
      state_class: total_increasing
      accuracy_decimals: 2
      filters:
        - multiply: 0.01
```

Den Zählerstand an den echten Zähler anzugleichen ist nicht nötig: HeatConductor wertet nur
die Differenzen aus. Brennwert und Zustandszahl stehen auf der Gasabrechnung.

Kessel-ESP mit Vor-/Rücklauf: siehe [esphome/README.md](esphome/README.md). Vaillant-X6-Diagnose: eigenes Projekt [esphome-vaillant-x6](https://github.com/MYF540/esphome-vaillant-x6).

### Energie-Dashboard

*Einstellungen → Dashboards → Energie → Gasverbrauch hinzufügen* → **Gasenergie**
(HeatConductor, kWh) oder **Gasverbrauch** (m³) wählen.

## Dienste

| Dienst | Wirkung |
|---|---|
| `heat_conductor.boost` | Raum für eine Dauer auf Boost-Temperatur (Ziel: Raumthermostat) |
| `heat_conductor.clear_override` | Boost und manuelle Übersteuerung beenden |
| `heat_conductor.set_vacation` | Urlaub von/bis mit optionaler Temperatur |
| `heat_conductor.clear_vacation` | Urlaub beenden |
| `heat_conductor.reset_learning` | Lerndaten eines Raums oder aller Räume löschen |

## Entitäten

| Entität | Bedeutung |
|---|---|
| Betriebsmodus | Automatik / Komfort / Eco / Abwesend / Urlaub / Frostschutz / Aus |
| Automatik | aus = HeatConductor greift nie ein |
| Beobachtungsmodus | an = Kessel wird nicht geschaltet |
| Raumsteuerung | an = Solltemperaturen werden an Thermostate geschrieben |
| Wärmeanforderung, Brenner aktiv | Entscheidung „Kessel an“ und tatsächlicher Brennerbetrieb |
| Kesselstatus, Entscheidungsgrund | Zustand und Grund (Attribute: Restzeit, Räume) |
| Störung, Relais-Watchdog | Sicherheitsabschaltung/fehlende Daten, Erreichbarkeit des Watchdogs |
| Gesamtbedarf | gewichteter Bedarf aller geregelten Räume |
| Außentemperatur (geglättet, Tagesmittel, Vorhersage 12 h) | Grundlage für Heizgrenze und Vorausschau |
| Kessel-/Brennerstarts und -laufzeit heute, Spreizung | Takt-Kontrolle |
| Gasverbrauch, Gasenergie (gesamt/heute/gestern) | m³ bzw. kWh |
| Brennerleistung, Brennermodulation, Brennwertnutzung, Brennwertanteil | Kesselanalyse |
| Gradtagzahl gestern, Energie je Gradtag gestern | witterungsbereinigter Verbrauch |
| je Raum: Thermostat, Solltemperatur, Komfort-/Eco-Temperatur | Raumsteuerung |
| je Raum: Bedarf, Temperatur, Status | Attribute: Soll, Defizit, Ventil, Gewichtung |
| je Raum: gelernte Aufheizrate, gelernte Auskühl-Zeitkonstante | Diagnose |

## Entwicklung

Die Steuerlogik in `custom_components/heat_conductor/core/` ist reines Python ohne
Home-Assistant-Abhängigkeit. Das Panel (`frontend/heat-conductor-panel.js`) ist eine
abhängigkeitsfreie Web-Component ohne Build-Schritt.

Home Assistant läuft nicht nativ unter Windows, daher laufen die Tests in Docker:

```powershell
docker build -f docker/test.Dockerfile -t heat-conductor-test .
docker run --rm -v "${PWD}:/work" heat-conductor-test
```

Nur die Kern-Tests gehen auch direkt (Python 3.14):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core -p no:homeassistant
```
