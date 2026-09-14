<p align="center">
  <img src="custom_components/heat_conductor/brand/logo@2x.png" alt="HeatConductor" width="325">
</p>

# HeatConductor

Intelligente Heizungssteuerung für Home Assistant: HeatConductor wertet Thermostate,
Raum- und Außensensoren aus und entscheidet, wann der Kessel laufen soll – mit Schutz
gegen Takten, Sicherheitsabschaltung und nachvollziehbaren Entscheidungen.

> **Status: Phase 2 (Beobachtung + Analyse).** HeatConductor rechnet und zeigt an, was es tun
> würde. Solange der **Beobachtungsmodus** aktiv ist (Standard), wird nichts geschaltet.
> Den vollständigen Projektplan enthält [PLAN.md](PLAN.md).

## Funktionen

- **Räume** mit beliebig vielen Thermostaten, Ventil-Sensoren, optionalem Raumsensor,
  Fensterkontakten und Gewichtung; Räume ohne Thermostat können „nur überwacht“ werden.
- **Wärmebedarf je Raum** aus Ventilöffnung und Temperaturdefizit, gewichteter
  **Gesamtbedarf**.
- **Kessel-Zustandsautomat** mit Bestätigungszeit, Mindestlaufzeit, Mindestpause und
  maximalen Starts pro Stunde.
- **Sicherheit:** veraltete Werte werden erkannt, ohne gültige Daten geht der Kessel aus;
  Übertemperatur-Abschaltung; Frostschutz; Erkennung manuellen Schaltens.
- **Außentemperatur** aus mehreren Sensoren (Sonnen-Ausreißer werden ignoriert), Fallback
  auf eine Wetter-Entität, geglätteter Wert für die Heizgrenze.
- **Vergleich mit der Realität:** Kesselstarts/-laufzeit (virtuell) und Brennerstarts/
  -laufzeit (aus Gasdurchfluss oder Brenner-Sensor).

- **Energie und Analyse (Phase 2):**
  - Gasverbrauch in m³ und kWh (Zählerstand × Zustandszahl × Brennwert), geeignet für das
    Energie-Dashboard
  - Brennerleistung (kW) und Modulation (% der Nennbelastung)
  - Brennwertnutzung: Rücklauf unter einstellbarer Grenze bei laufendem Brenner, Anteil pro Tag
  - Gradtagzahl nach VDI 3807 (20/15) und Verbrauch je Gradtag, um Tage mit
    unterschiedlichem Wetter zu vergleichen

Die Modi *Komfort* (ignoriert die Heizgrenze), *Frostschutz* und *Aus* wirken bereits;
*Eco*, *Abwesend* und *Urlaub* bekommen ihre Wirkung mit der Raumsteuerung (Phase 4).

## Installation

### Über HACS (empfohlen)

1. *HACS → ⋮ (oben rechts) → Benutzerdefinierte Repositories*
2. Repository `https://github.com/MYF540/heat_conductor`, Typ **Integration**, hinzufügen.
3. *HeatConductor* in HACS öffnen → **Herunterladen**.
4. Home Assistant neu starten.
5. *Einstellungen → Geräte & Dienste → Integration hinzufügen → HeatConductor*.

Updates erscheinen danach in HACS.

### Manuell

Ordner `custom_components/heat_conductor` nach `/config/custom_components/` kopieren
(z. B. mit der Samba- oder SSH-App), Home Assistant neu starten und die Integration
wie oben hinzufügen.

## Einrichtung

1. **Zentrale Entitäten:** Außensensoren (mindestens einer oder eine Wetter-Entität),
   optional Kessel-Relais, Vor-/Rücklauf, Gasdurchfluss, Brenner-Sensor.
2. **Räume hinzufügen:** Auf der Integrationskarte „Raum hinzufügen“.
   Für HomematicIP-Thermostate:
   - *Thermostate:* die Climate-Entität des Raums
   - *Sensoren Ventilöffnung:* `sensor.…_heating` (Einheit %)
   - *Raumtemperatur-Sensor:* z. B. Zigbee-Sensor im Raum (optional, empfohlen)
3. **Parameter** (optional): *Konfigurieren → Regelparameter*. Die Standardwerte sind
   Startwerte, die im Beobachtungsbetrieb kalibriert werden.
4. **Energie** (für Phase 2): *Konfigurieren → Energie und Gas*
   - *Brennwert* und *Zustandszahl* von der Gasabrechnung
   - *Nennbelastung* (Q, Hi, in kW) vom Typenschild des Kessels, für die Modulation
   - unter *Zentrale Entitäten* den **Gaszählerstand** (m³, genauer) und/oder den
     **Gasdurchfluss** (m³/h) sowie die Rücklauftemperatur wählen

### Gaszähler mit ESPHome

Ein Reed-Kontakt am Gaszähler liefert Impulse (häufig 0,01 m³ je Impuls, siehe Zähler).
Mit pulse_meter entstehen Durchfluss und Zählerstand:

`yaml
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
`

Den Zählerstand einmalig an den echten Zähler angleichen ist nicht nötig: HeatConductor
wertet nur die Differenzen aus.

### Energie-Dashboard

*Einstellungen → Dashboards → Energie → Gasverbrauch hinzufügen* → **Gasenergie**
(HeatConductor, kWh) oder **Gasverbrauch** (m³) wählen.

## Entitäten

| Entität | Bedeutung |
|---|---|
| Betriebsmodus | Automatik / Komfort / Eco / Abwesend / Urlaub / Frostschutz / Aus |
| Automatik | Steuerung aktiv; aus = HeatConductor greift nie ein |
| Beobachtungsmodus | an = nur rechnen, nicht schalten |
| Wärmeanforderung | Entscheidung „Kessel an“ (im Beobachtungsmodus virtuell) |
| Brenner aktiv | Brenner brennt tatsächlich (Gas/Sensor) |
| Störung | Sicherheitsabschaltung oder Raum ohne gültige Daten |
| Kesselstatus, Entscheidungsgrund | Zustand und Grund, Attribute mit Restzeit und Räumen |
| Gesamtbedarf | gewichteter Bedarf aller geregelten Räume |
| Außentemperatur (geglättet) | kombinierter Wert und Glättung für die Heizgrenze |
| Kessel-/Brennerstarts und -laufzeit heute | Takt-Kontrolle |
| Spreizung Vor-/Rücklauf | falls beide Sensoren konfiguriert |
| Gasverbrauch, Gasenergie (gesamt/heute/gestern) | m³ bzw. kWh, fürs Energie-Dashboard |
| Brennerleistung, Brennermodulation | kW (Brennwertbasis) und % der Nennbelastung |
| Brennwertnutzung, Brennwertanteil heute | Rücklauf unter der Grenze bei laufendem Brenner |
| Außentemperatur Tagesmittel, Gradtagzahl gestern | Grundlage für den Wettervergleich |
| Energie je Gradtag gestern | kWh/Kd, witterungsbereinigter Verbrauch |
| je Raum: Bedarf, Temperatur, Status | Attribute: Soll, Defizit, Ventil, Gewichtung |

## Entwicklung

Die Steuerlogik in `custom_components/heat_conductor/core/` ist reines Python ohne
Home-Assistant-Abhängigkeit.

Home Assistant läuft nicht nativ unter Windows, daher laufen die Tests in Docker:

```powershell
docker build -f docker/test.Dockerfile -t heat-conductor-test .
docker run --rm -v "${PWD}:/work" heat-conductor-test
```

Nur die Kern-Tests gehen auch direkt (Python 3.14):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core -p no:homeassistant
```
