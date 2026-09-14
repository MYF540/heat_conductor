# Heizung-ESP (ESPHome)

ESP32-S3-DevKitC-1 am Heizkessel. Er liefert HeatConductor:

- **Vorlauf- und Rücklauftemperatur** über zwei DS18B20-Anlegefühler
- **Kesseldaten über die Vaillant-X6-Diagnoseschnittstelle** (nur lesend): Brenner an/aus,
  Pumpe, Kessel-Vorlauf/-Rücklauf, Vorlauf-Soll von Kessel und Regler, Brennsperrzeit

![Verdrahtung](docs/verdrahtung.svg)

## Teile

| Bauteil | Anzahl | Hinweis |
|---|---|---|
| ESP32-S3-DevKitC-1 | 1 | Versorgung über USB-C mit eigenem 5-V-Netzteil |
| DS18B20, wasserdichte Ausführung mit Kabel | 2 | Anlegefühler |
| Widerstand 4,7 kΩ (R1) | 1 | 1-Wire-Pull-up; bei Kabel > 10 m: 2,2 kΩ |
| ADuM1201 (U1), SOIC-8 oder fertiges Modul | 1 | Digitalisolator, 1 Kanal je Richtung |
| Kondensator 100 nF (C1, C2) | 2 | direkt an VDD1/GND1 und VDD2/GND2 |
| Widerstand 220 Ω (R2, R3) | 2 | Schutzwiderstände in den X6-Signalleitungen |
| RJ12-Stecker + Flachkabel (6P6C oder 6P4C) | 1 | für die X6-Buchse |
| Wärmeleitpaste, Kabelbinder/Rohrschellen, Isolierung | – | Fühlermontage |

## Anschlüsse

### ESP32-S3 ↔ DS18B20

| ESP32-S3 | DS18B20 (beide parallel) |
|---|---|
| 3V3 | VDD (meist rot) |
| GND | GND (meist schwarz) |
| GPIO4 | DQ (meist gelb/weiß) + R1 4,7 kΩ nach 3V3 |

### ESP32-S3 ↔ ADuM1201 ↔ X6

| ESP32-S3 | ADuM1201 ESP-Seite | ADuM1201 Kessel-Seite | X6 (RJ12) |
|---|---|---|---|
| 3V3 | Pin 1 VDD1 | Pin 8 VDD2 | Pin 2 +5 V |
| GPIO18 (RX) | Pin 2 VOA ← | Pin 6 VIA ← R2 220 Ω ← | Pin 4 TX |
| GPIO17 (TX) | Pin 3 VIB → | Pin 7 VOB → R3 220 Ω → | Pin 3 RX |
| GND | Pin 4 GND1 | Pin 5 GND2 | Pin 5 GND |
| – | – | – | Pin 1 n. c., **Pin 6 +24 V nicht anschließen** |

Die Pinbelegung des ADuM1201 bitte mit dem Datenblatt bzw. der Modulbeschriftung abgleichen.

## Sicherheit

- **Kessel stromlos schalten**, bevor das Schaltfeld geöffnet wird (230 V an der Platine).
- **Den ESP nie aus der X6 versorgen.** In der Community ist dokumentiert, dass ein über
  X6-Pin 2/5 gespeister ESP die Therme sofort abgeschaltet hat. Aus Pin 2 wird hier nur
  die Kessel-Seite des Isolators versorgt (wenige mA).
- **Pin 6 (+24 V) nicht anschließen.**
- **Vor dem ersten Anstecken messen** (Multimeter gegen Pin 5 GND): Pin 2 ≈ 5 V,
  Pin 6 ≈ 24 V, Pin 4 ≈ 5 V im Ruhezustand. Weicht das ab: nicht anschließen.
- Geht das Kesseldisplay aus oder flackert es: sofort abziehen.
- Die Komponente **sendet nur Lese-Anfragen**. Es werden keine Parameter geschrieben.

## Fühlermontage

- **Vorlauf:** am Vorlaufrohr kurz nach dem Kessel, vor dem ersten Abzweig.
- **Rücklauf:** am Rücklaufrohr kurz vor dem Kessel.
- Fühler mit Wärmeleitpaste längs an das blanke Rohr (Kupfer/Stahl), mit Kabelbinder oder
  Schelle fixieren, darüber isolieren. Anlegefühler messen einige Kelvin träger und
  niedriger als die Wassertemperatur; für Spreizung und Brennerzyklen ist das ausreichend.

## Inbetriebnahme

1. `secrets.yaml.example` nach `secrets.yaml` kopieren und ausfüllen.
2. Erstes Flashen per USB (z. B. ESPHome Builder in Home Assistant oder
   `esphome run heizung-esp.yaml`). Die Platzhalter-Adressen der DS18B20 sind noch leer.
3. Im Log listet der 1-Wire-Bus die gefundenen Adressen (`0x…`). Einen Fühler kurz in der
   Hand erwärmen, um Vorlauf und Rücklauf zuzuordnen.
4. Adressen unter `substitutions` (`address_flow`, `address_return`) eintragen, erneut flashen.
5. **X6 prüfen:** Der Sensor „X6 Verbindung“ muss `an` sein, „X6 Übertragungsfehler“ sollte
   nicht stetig steigen. Falls keine Antworten kommen: `x6_baud_rate` auf `2400` stellen
   (ältere Geräte) und RX/TX-Zuordnung prüfen. Mit `logger: level: VERBOSE` werden die
   gesendeten Pakete protokolliert.
6. Nicht jede Adresse wird von jedem Kesselmodell beantwortet. Werte, die dauerhaft keine
   Antwort liefern, in der YAML auskommentieren.

## Einbindung in HeatConductor

*HeatConductor → Konfigurieren → Zentrale Entitäten:*

| Feld | Entität |
|---|---|
| Vorlauftemperatur | `sensor.heizung_vorlauf` (DS18B20) |
| Rücklauftemperatur | `sensor.heizung_rucklauf` (DS18B20) |
| Sensor „Brenner aktiv“ | `binary_sensor.heizung_brenner` (X6) |

Die X6-Temperaturen des Kessels dienen zur Kontrolle und später zur Plausibilisierung.

## X6-Protokoll

Reverse-engineert von der Community. Die Komponente ist eine eigenständige, nicht
blockierende Neuimplementierung; Adressen und Prüfsumme stammen aus
[esphome_vaillant](https://github.com/jayme-github/esphome_vaillant).

- UART 9600 Baud (teils 2400), 8N1, TTL 5 V
- Anfrage: `07 00 00 00 <Adresse> 00 <Prüfsumme>`
- Antwort: `<Länge> <Status> <Daten…> <Prüfsumme>`, Temperaturen als int16 big-endian / 16
- Prüfsumme: für jedes Byte `sum = (sum & 0x80) ? ((sum << 1) | 1) ^ 0x18 : sum << 1; sum ^= byte`

| Adresse | Wert | Konfiguration |
|---|---|---|
| 0x18 | Vorlauf ist | `flow_temperature` |
| 0x39 | Vorlauf soll (Kessel) | `flow_temperature_target` |
| 0x25 | Vorlauf soll vom Regler (7-8-9) | `flow_temperature_controller` |
| 0x98 | Rücklauf ist | `return_temperature` |
| 0x38 | verbleibende Brennsperrzeit (min) | `remaining_burner_lock` |
| 0x0D | Brenner an | `burner` |
| 0x44 | Pumpe an | `pump` |
| 0x08 | Winterbetrieb | `winter_mode` |

Weitere Quellen: [martin3000/ESPhome](https://github.com/martin3000/ESPhome),
[FHEM-Forum: Vaillant X6 über ESP8266](https://forum.fhem.de/index.php?topic=43573.0),
[Symcon-Community: Vaillant X6](https://community.symcon.de/t/vaillant-x6-schnittstelle/52188).
