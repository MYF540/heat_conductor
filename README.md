# HeatConductor

Intelligente Heizungssteuerung für Home Assistant: HeatConductor wertet Thermostate,
Raum- und Außensensoren aus und entscheidet, wann der Kessel laufen soll – mit Schutz
gegen Takten, Sicherheitsabschaltung und nachvollziehbaren Entscheidungen.

> **Status: Phase 1 (Beobachtung).** HeatConductor rechnet und zeigt an, was es tun
> würde. Solange der **Beobachtungsmodus** aktiv ist (Standard), wird nichts geschaltet.
> Den vollständigen Projektplan enthält [PLAN.md](PLAN.md).

## Funktionen in Phase 1

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

Die Modi *Komfort* (ignoriert die Heizgrenze), *Frostschutz* und *Aus* wirken bereits;
*Eco*, *Abwesend* und *Urlaub* bekommen ihre Wirkung mit der Raumsteuerung (Phase 4).

## Installation (Entwicklungsphase)

1. Ordner `custom_components/heat_conductor` nach `/config/custom_components/` kopieren
   (z. B. mit der Samba- oder SSH-App).
2. Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → HeatConductor*.

Später: Installation über HACS als benutzerdefiniertes Repository.

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
