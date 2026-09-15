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

## ESPHome Device Builder in Home Assistant

**Variante 1 – Komponente direkt aus GitHub (empfohlen):** Nur `heizung-esp.yaml` nach
`/config/esphome/` kopieren (oder im Builder als neues Gerät einfügen) und den Block
`external_components` so ändern:

```yaml
external_components:
  - source:
      type: git
      url: https://github.com/MYF540/heat_conductor
      ref: main
      path: esphome/components
    components: [vaillant_x6]
    refresh: 1d
```

**Variante 2 – lokal:** Ordner `components/vaillant_x6` zusätzlich nach
`/config/esphome/components/vaillant_x6/` kopieren; die YAML bleibt unverändert.

Die Zugangsdaten gehören in die Secrets des Builders (oben rechts *Secrets*), Schlüssel
siehe `secrets.yaml.example`.

## Inbetriebnahme

1. `secrets.yaml.example` nach `secrets.yaml` kopieren und ausfüllen (bzw. Secrets im Builder).
2. Erstes Flashen per USB (z. B. ESPHome Builder in Home Assistant oder
   `esphome run heizung-esp.yaml`). Die Platzhalter-Adressen der DS18B20 sind noch leer.
3. Im Log listet der 1-Wire-Bus die gefundenen Adressen (`0x…`). Einen Fühler kurz in der
   Hand erwärmen, um Vorlauf und Rücklauf zuzuordnen.
4. Adressen unter `substitutions` (`address_flow`, `address_return`) eintragen, erneut flashen.
X6„X6 Verbindung“ muss `an` sein, „X6 Übertragungsfehler“ sollte
   nicht stetig steigen. Falls keine Antworten kommen: `x6_baud_rate` auf `2400` stellen
   (ältere Geräte) und RX/TX-Zuordnung prüfen. Mit `logger: level: VERBOSE` werden die
   gesendeten Pakete protokolliert.
6. Nicht jede Adresse wird von jedem Kesselmodell beantwortet. Werte, die dauerhaft keine
   Antwort liefern, in der YAML auskommentieren.
7. **Fühler kalibrieren** (siehe unten).

## Kalibrierung der Vor- und Rücklauffühler

Die Korrektur passiert **auf dem ESP**: Die Entitäten *Vorlauf* und *Rücklauf* liefern
bereits korrigierte Werte an Home Assistant, HeatConductor und alle anderen Nutzer.

```
korrigiert = roh × Faktor + Offset
```

| Entität | Bedeutung |
|---|---|
| *Vorlauf roh*, *Rücklauf roh* (Diagnose) | unkorrigierter Messwert des DS18B20 |
| *Vorlauf/Rücklauf Kalibrierung Offset* (Konfiguration) | Verschiebung in K, Standard 0 |
| *Vorlauf/Rücklauf Kalibrierung Faktor* (Konfiguration) | Steigung, Standard 1 |

Die Werte stellst du in Home Assistant am Gerät *Heizung* unter *Konfiguration* ein. Sie
werden auf dem ESP gespeichert, überstehen Neustarts und wirken ab der nächsten Messung
(höchstens 15 s), ohne neu zu flashen.

### Zwei-Punkt-Kalibrierung (am genauesten, vor der Montage)

1. Beide Fühler und ein **Referenzthermometer** zusammen in ein isoliertes Gefäß mit Wasser.
2. **Punkt 1** bei etwa 25 °C, **Punkt 2** bei etwa 60 °C: jeweils einige Minuten warten, dann
   Referenz `R` und Rohwert `M` („… roh“) je Fühler notieren.
3. Je Fühler berechnen und eintragen:

   ```
   Faktor = (R2 − R1) / (M2 − M1)
   Offset = R1 − M1 × Faktor
   ```

   Beispiel: M1 = 24,6, R1 = 25,0, M2 = 59,1, R2 = 60,0
   → Faktor = 35,0 / 34,5 = **1,0145** · Offset = 25,0 − 24,6 × 1,0145 = **0,04 K**

   Das Eingabefeld für den Faktor erlaubt drei Nachkommastellen: 1,014 ergibt dann einen
   Offset von 0,06 K (Offset immer mit dem tatsächlich eingetragenen Faktor berechnen).

### Ein-Punkt-Kalibrierung (Offset, auch nach der Montage)

Faktor auf 1 lassen. Bei gleicher Temperatur Referenz und Rohwert vergleichen:
`Offset = Referenz − roh`.

Nach der Montage eignet sich dafür eine längere Brennerpause mit laufender Pumpe: Vor- und
Rücklauf sind dann annähernd gleich warm. Den Rücklauf-Offset so wählen, dass beide Fühler
denselben Wert zeigen. Die X6-Werte *Kessel Vorlauf/Rücklauf* taugen zur Plausibilisierung,
sind aber selbst nur auf etwa ±1 K genau.

Hinweis: Anlegefühler messen am Rohr etwas weniger als die Wassertemperatur. Die
Zwei-Punkt-Kalibrierung im Wasserbad korrigiert den Fühler selbst; eine zusätzliche
Montage-Abweichung lässt sich danach über den Offset ausgleichen.

## Einbindung in HeatConductor

*HeatConductor → Konfigurieren → Zentrale Entitäten:*

| Feld | Entität |
|---|---|
| Vorlauftemperatur | `sensor.heizung_vorlauf` (DS18B20, kalibriert) |
| Rücklauftemperatur | `sensor.heizung_rucklauf` (DS18B20, kalibriert) |
| Sensor „Brenner aktiv“ | `binary_sensor.heizung_brenner` (X6) |

Die X6-Temperaturen des Kessels dienen zur Kontrolle und später zur Plausibilisierung.

## X6-Protokoll

Reverse-engineert von der Community. Die Komponente ist eine eigenständige, nicht
blockierende Neuimplementierung; Adressen und Prüfsumme stammen aus
[esphome_vaillant](https://github.com/jayme-github/esphome_vaillant).

- UART 9600 Baud, 8N1, TTL 5 V
- Anfrage: `07 00 00 00 <Adresse> <Anfragebyte> <Prüfsumme>`, Anfragebyte **0x05** bei älteren
  Kesseln (z. B. VKO/VKK mit Einbauregler), **0x00** bei neueren. `request_byte: auto` probiert beide.
- Antwort: `<Länge> <Status> <Daten…> <Prüfsumme>`, Temperaturen als int16 big-endian / 16
- Prüfsumme: für jedes Byte `sum = (sum & 0x80) ? ((sum << 1) | 1) ^ 0x18 : sum << 1; sum ^= byte`

| Adresse | Wert | Konfiguration |
|---|---|---|
| 0x18 | Vorlauf ist | `flow_temperature` |
| 0x39 | Vorlauf soll (Kessel) | `flow_temperature_target` |
| 0x25 | Vorlauf soll vom Regler (7-8-9) | `flow_temperature_controller` |
| 0x98 | Rücklauf ist (neuere Geräte) | `return_temperature` |
| 0x6A | Außentemperatur (Fühler am Kessel, ältere Geräte) | `outdoor_temperature` |
| 0x05 | Flammsignal (ältere Geräte) | `flame` |
| 0x38 | verbleibende Brennsperrzeit (min) | `remaining_burner_lock` |
| 0x0D | Brenner an | `burner` |
| 0x44 | Pumpe an | `pump` |
| 0x08 | Winterbetrieb | `winter_mode` |

Das Anfragebyte 0x05 und die Parameter älterer Kessel stammen aus [haniham/HeizungESP8266](https://github.com/haniham/HeizungESP8266) (VKO 246 mit VRC 420).

Weitere Quellen: [martin3000/ESPhome](https://github.com/martin3000/ESPhome),
[FHEM-Forum: Vaillant X6 über ESP8266](https://forum.fhem.de/index.php?topic=43573.0),
[Symcon-Community: Vaillant X6](https://community.symcon.de/t/vaillant-x6-schnittstelle/52188).
