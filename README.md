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
- **Freigabe über den Raumthermostat-Eingang** des Kessels: Bestätigungszeit,
  Mindest-Freigabedauer, Pause zwischen Freigaben, max. Freigaben pro Stunde
- Brennerbewusst: ein laufender Brenner wird nicht abgeschaltet, und nach einem Brennerlauf
  endet die Freigabe, wenn der Bedarf für einen Neustart nicht reicht
- Freigabe endet, wenn alle Räume über Soll liegen
- **Wärmeverbund:** jede Freigabe wird für möglichst viele Räume genutzt – Räume, die bald
  selbst Wärme bräuchten, heizen mit, weitere Räume öffnen, bis der Kessel genug Wärme loswird,
  und die Restwärme aus Kessel und Rohren geht nach der Freigabe in die Räume. Ergebnis: weniger,
  längere Brennerläufe
- Heizgrenze auf geglätteter Außentemperatur, aufgehoben bei kalter Wettervorhersage
- Sicherheit: veraltete Werte, Sicherheitsabschaltung ohne Daten, Übertemperatur, Frostschutz,
  Erkennung manuellen Schaltens, **Relais-Watchdog** auf dem Shelly, **Reparaturhinweise** in HA

**Räume**
- Virtueller **Raumthermostat** je Raum (Soll, Ist, Boost, Komfort/Eco, Aus)
- Solltemperatur nach Priorität: Fenster offen → Raum aus → Boost → manuelle Übersteuerung →
  Modus (Aus, Frostschutz, Urlaub, Abwesend, Eco, Komfort) → Anwesenheit → Zeitplan
- **Nutzungsbasiertes Heizen:** Räume werden nur auf Komfort geheizt, solange sie genutzt
  werden (Fernseher, PC, Präsenzmelder …); ungenutzte Räume fallen auf Eco. Je Raum abschaltbar
- **Nachtabsenkung:** Nachtfenster, optionaler Schlafsensor und gelerntes Nachtfenster senken
  alle Räume auf Eco, auch wenn jemand zu Hause ist
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
- **Wärmeverbund:** benötigte offene Heizfläche für eine Ziel-Brennerlaufzeit (aus jedem
  Brennerlauf) und das Nachheizen der Heizkörper je Raum
- **Heizkurven-Empfehlung:** aus Ventilöffnungen, Raumtemperaturen und Vorlauf entsteht je
  Außentemperatur-Bereich ein Vorschlag für eine passendere Heizkurve des Kesselreglers
- **Vorausschauend heizen:** aus der Anwesenheit gelernte Ankunftszeiten; vorgeheizt wird
  rechtzeitig vor der erwarteten Ankunft, wer früher kommt, bekommt sofort Wärme, kommt niemand,
  geht die Heizung nach einer Wartezeit auf Eco
- **Gelerntes Nachtfenster:** der Schlafsensor trainiert, wann üblicherweise geschlafen wird
- **Automatischer Urlaub:** ist zwei Tage niemand zu Hause, schaltet HeatConductor in den
  Urlaubsmodus und beendet ihn drei Stunden nach der Rückkehr; währenddessen wird nicht gelernt
- Jeder Wert mit Anzahl Messungen und Streuung

**Panel „HeatConductor“ in der Seitenleiste**
- *Übersicht:* Zustandsautomat, Grund, Zeitschutz, Räume, Verläufe (24 h / 7 Tage)
- *Parameter:* jeder Parameter erklärt, mit Wirkung, Standard, Bereich; Änderungen wirken sofort
- *Lernen:* gelernte Werte, Diagramme, Lernverlauf, Heizkurven-Empfehlung, Heizfläche und
  Brennerlaufzeit, Tageswerte mit und ohne Wärmeverbund
- *Zeitplan:* Anwesenheit je Wochentag, der vorgeschlagene Wochenplan und die Nachtabsenkung
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
   Geräte für die Nutzungserkennung, Gewichtung, Sensorkorrektur, Sonnengewinne.
   Räume ohne Thermostat als „Nur überwachen“.
3. **Parameter**: im Panel unter *Parameter* oder unter *Konfigurieren* (Regelparameter,
   Energie und Gas, Raumsteuerung, Nutzungserkennung, Nacht und Schlaf, Urlaub,
   Lernen und Vorausschau).
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

### Nutzungsbasiertes Heizen

Trage je Raum unter *Geräte für Nutzungserkennung* die Entitäten ein, an denen man die Nutzung
erkennt: Fernseher (Media Player), Steckdose des PCs, Präsenzmelder, Lichter. Ist eine davon an,
gilt der Raum als genutzt und wird auf **Komforttemperatur** geheizt, sonst auf **Eco**
(Beispiel: 20 °C genutzt, 18 °C ungenutzt). Nach der letzten Aktivität bleibt der Raum noch die
eingestellte **Nachlaufzeit** (Standard 30 min) auf Komfort.

- Je Raum gibt es den Schalter *Nutzungserkennung* und den Sensor *Raum genutzt*.
- Fenster offen, Raum aus, Boost, manuelle Übersteuerung, Urlaub und Abwesenheit haben weiter Vorrang.
- *Nutzung hebt Absenkung auf* (Standard an): ein genutzter Raum wird auch in einer Absenkphase
  auf Komfort geheizt. Ausschalten, wenn nachts keinesfalls geheizt werden soll.

### Vorausschauend heizen

HeatConductor lernt aus den Anwesenheits-Entitäten, wann üblicherweise jemand zu Hause ist
(Panel-Reiter *Zeitplan*, belastbar nach etwa zwei Wochen). Mit dem Schalter
*Vorausschauend heizen* wird daraus eine Vorhersage, die die echte Anwesenheit bestätigt:

| Lage | Verhalten | Grund im Panel |
|---|---|---|
| jemand zu Hause | Komfort | *Jemand zu Hause* |
| niemand da, Ankunft laut Plan bald | rechtzeitig vorheizen | *Ankunft erwartet* |
| früher heimgekommen | sofort Komfort | *Jemand zu Hause* |
| erwartete Ankunft verstrichen, niemand da | noch die **Wartezeit** (Standard 45 min) warm, dann Eco | *Ankunft erwartet*, danach *Niemand zu Hause* |
| niemand da, keine Ankunft erwartet | Eco | *Niemand zu Hause* |
| Nachtfenster endet (fest oder gelernt) | vor dem Aufstehen aufheizen | *Aufwärmen vor dem Aufstehen* |

Wie früh vorgeheizt wird, folgt je Raum aus der gelernten Aufheizrate (optimaler Start);
solange sie fehlt, gilt die *Vorheizzeit ohne Lernwerte* (Standard 60 min).

- Gilt für Räume **ohne eigenen Zeitplan-Helfer**; ein Zeitplan-Helfer bleibt die feste Vorgabe
  seines Raums.
- Nachtabsenkung und Nutzungserkennung liegen darüber: nachts wird abgesenkt, und ein Raum mit
  Nutzungserkennung wird erst warm, wenn er genutzt wird.
- Ohne genug Lerndaten entscheidet allein die Anwesenheit (jemand da → Komfort).
- Später geplant: Ankunft über die Entfernung zum Zuhause (Integration *Proximity*) erkennen.

### Nachtabsenkung

Nachts ist man zu Hause, trotzdem soll die Heizung meist absenken. Das entscheidest du unter
*Konfigurieren → Nacht und Schlaf*. Drei Auslöser, einer genügt:

| Auslöser | Wirkung |
|---|---|
| **Nachtfenster** (z. B. 23:00 bis 06:30) | gilt fest, auch über Mitternacht und auch wenn jemand wach ist |
| **Schlafsensor** (optional) | Bettsensor o. Ä.; senkt nach der **Bestätigungszeit** ab (Standard 20 min) |
| **Gelerntes Nachtfenster** | aus dem Schlafsensor gelernt, je Wochentag und halber Stunde |

Während der Nacht gehen alle Räume auf ihre **Eco-Temperatur**, der Grund heißt *Nachtabsenkung*.

- **Aufstehen:** Meldet der Schlafsensor für die **Aufwachzeit** (Standard 15 min) wach, endet die
  Nacht sofort, auch mitten im Nachtfenster. Ein kurzer nächtlicher Gang beendet sie nicht.
- **Vorrang:** Fenster offen, Raum aus, Boost, manuelle Übersteuerung und der Modus *Komfort*
  stechen die Nachtabsenkung. Die Nutzungserkennung dagegen nicht: Der laufende Fernseher hebt
  die Absenkung nicht auf.
- **Lernen:** Nur der Schlafsensor trainiert das Nachtraster, nicht die Fenster. Im Urlaub wird
  nicht gelernt. Der Reiter *Zeitplan* zeigt das Raster und die gelernten Nachtfenster.
- Die Entität *Schlafen* zeigt, ob gerade abgesenkt wird und welcher Auslöser greift.

### Automatischer Urlaub

Ist **zwei Tage** niemand zu Hause (Anwesenheits-Entitäten unter *Zentrale Entitäten*), schaltet
HeatConductor selbst in den **Urlaubsmodus**: alle Räume auf Urlaubstemperatur (Standard 15 °C).
Ist wieder **drei Stunden** jemand zu Hause, endet er. Beide Zeiten sind einstellbar, die
Erkennung lässt sich abschalten (*Konfigurieren → Urlaub*).

- Die Entität *Urlaub* zeigt, ob gerade Urlaub läuft und ob er automatisch oder geplant ist.
- Von Hand beenden: Dienst `heat_conductor.clear_vacation` oder Betriebsmodus umstellen.
  Danach braucht es wieder die volle Abwesenheit, bevor der Urlaubsmodus erneut startet.
- Ein kurzer Besuch beendet den Urlaub nicht, weil erst die Rückkehrzeit ablaufen muss.
- **Während eines Urlaubs lernt HeatConductor keinen Zeitplan.** Sonst würden zwei Wochen
  Abwesenheit den Anwesenheitsplan verwässern.

### Heizkurven-Empfehlung

Ist die Heizkurve des Kesselreglers zu hoch, drosseln die Thermostate die überschüssige Wärme
weg: Die Ventile stehen nur halb offen, der Rücklauf ist warm, der Brenner taktet. Ist sie zu
niedrig, werden Räume trotz offener Ventile nicht warm. HeatConductor wertet deshalb während
**durchgehenden Brennerbetriebs** je Außentemperatur-Bereich (3 K) aus:

- welcher Raum am weitesten geöffnet ist (**Engpass-Raum**) und wie weit,
- ob er trotz offenem Ventil zu kalt bleibt,
- welcher Vorlauf und welche Spreizung dabei anlagen.

Daraus folgt über die Heizkörper-Kennlinie, welcher Vorlauf reichen würde, damit der Engpass-Raum
seine Solltemperatur bei etwa **85 % Ventilöffnung** hält. Das Panel zeigt unter *Lernen* die
gelernte und die empfohlene Kurve, die Änderung je Bereich und – mit der eingestellten Kurvennummer
(*Parameter → Lernen → Eingestellte Heizkurve*, z. B. 1,4) – eine ungefähre neue Kurvennummer.

- Voraussetzungen: *Vorlauf-Soll des Kesselreglers* (z. B. X6 0x39), ein Brenner-Sensor oder
  Gaszähler, Ventilöffnungen der Räume. Vor- und Rücklauf verbessern das Ergebnis.
- Je Bereich braucht es etwa 2 h durchgehenden Brennerbetrieb; eine Kurve (Steilheit) entsteht
  erst, wenn mindestens zwei Bereiche vorliegen. Im Herbst gibt es also zunächst nur Werte für
  milde Tage.
- Räume, die die Kurve nicht bestimmen sollen (z. B. ein Wintergarten), schaltest du in den
  Raumeinstellungen bei *Für Heizkurven-Empfehlung berücksichtigen* aus.
- **Richtwert:** Die Ventilöffnung ist nur ein grobes Maß für die abgegebene Wärme. Kurve am
  Regler anpassen und danach an der gelernten Kurve prüfen. HeatConductor verstellt den Regler
  nicht selbst.

### Rückmeldungen vom Kessel (z. B. Vaillant X6)

Alle Felder sind optional unter *Zentrale Entitäten*. Mit
[esphome-vaillant-x6](https://github.com/MYF540/esphome-vaillant-x6) liefern sie:

| Feld in HeatConductor | X6-Wert | Wirkung |
|---|---|---|
| Sensor „Brenner aktiv“ | *Flamme* (0x05) oder *Brenner* (0x0D) | Brennerstarts, Laufzeiten, Lernen – auch ohne Gaszähler |
| Vorlauf-Soll des Kesselreglers | *Kessel Vorlauf soll* (0x39) | Heizkurve des Einbaureglers lernen |
| Außentemperatur-Sensoren (zusätzlich) | *Außentemperatur* (0x6A) | der Fühler, nach dem der Kessel regelt |
| Rückmeldung Wärmeanforderung am Kessel | *Wärmeanforderung Raumthermostat* (0x0E) | Störung, wenn Relais und Kessel länger nicht übereinstimmen |
| Brennersperrzeit des Kessels | *Brennersperrzeit* (0x38) | erklärt, warum der Brenner trotz Anforderung aus bleibt |
| Kessel im Winterbetrieb | *Winterbetrieb* (0x08) | Störung, wenn der Kessel auf Sommer steht, aber geheizt werden soll |
| Heizungspumpe des Kessels | *Heizungspumpe* (0x44) | Spreizung nur bei laufender Pumpe |
| Vorlauf am Kesselfühler | *Kessel Vorlauf ist* (0x18) | Kontrolle der Rohrfühler, Spreizung am Kessel |
| Rücklauf am Kesselfühler | – (am Testkessel nicht vorhanden) | sonst dient der Rücklauf-Rohrfühler |

**Rohrfühler und Kesselfühler:** Die Anlegefühler sitzen hinter der Umwälzpumpe am Rohr, ein
gleichbleibender Unterschied zum Kesselfühler ist daher normal. HeatConductor lernt ihn bei
laufender Pumpe (Sensor *Vorlauf-Abweichung zum Kessel*, Attribut „üblich“) und meldet nur, wenn
der Rohrfühler länger als 30 min mehr als 5 K davon abweicht – etwa bei einem abgerutschten Fühler.
*Spreizung am Kessel* rechnet mit dem Kesselvorlauf und dem Rücklauf-Rohrfühler, falls der Kessel
keinen eigenen Rücklauffühler hat; die bisherige *Spreizung* bleibt die der beiden Rohrfühler.

Relais-Rückmeldung, Sommerbetrieb und „Kessel heizt trotz Freigabe nicht“ erscheinen als
Störung und nach 5 min als Reparaturhinweis.

### Wie HeatConductor den Kessel steuert

Das Relais ersetzt den Raumthermostat-Kontakt (Klemmen 3-4). Es **schaltet nicht den Brenner**,
sondern gibt den Kessel frei. Innerhalb der Freigabe regelt der Kessel selbst: Der Einbauregler
bestimmt das Vorlauf-Soll aus der Heizkurve, der Kessel moduliert und zündet, bis das Soll
erreicht ist, und sperrt danach den Brenner für seine eigene Sperrzeit. Die Pumpe läuft nur,
solange freigegeben ist.

HeatConductor entscheidet deshalb über **Beginn und Ende der Freigaben**:

| Regel | Wirkung |
|---|---|
| Start-/Stopp-Schwelle, Bestätigungszeit | Freigabe nur bei echtem Bedarf aller Räume |
| Mindest-Freigabedauer, Pause, max. Freigaben pro Stunde | wenige, dafür sinnvolle Freigaben |
| **Laufenden Brenner nicht abschalten** | Soll die Freigabe enden, während der Brenner brennt, wird das Ende des Brennerlaufs abgewartet (höchstens 30 min). Ein abgebrochener Brennerlauf kostet einen Start ohne Nutzen. |
| **Nach dem Brennerlauf bei geringem Bedarf beenden** | Endet ein Brennerlauf und liegt der Bedarf unter der Start-Schwelle, endet auch die Freigabe. Sonst zündet der Kessel nach seiner Sperrzeit für einen Rest-Bedarf erneut. |
| **Kessel heizt trotz Freigabe nicht** | 30 min freigegeben, Brenner nie gezündet, Wasser deutlich unter dem Vorlauf-Soll → Hinweis, z. B. wenn der Einbauregler noch ein eigenes Zeitprogramm mit Absenkung fährt |

Die brennerbewussten Regeln brauchen einen Brenner-Sensor (z. B. X6 *Flamme*) oder den Gaszähler
und wirken nur, wenn HeatConductor das Relais wirklich schaltet (nicht im Beobachtungsmodus).
Im Panel zeigt die Übersicht die Brennerstarts der laufenden Freigabe.

### Wärmeverbund

Der Kessel kann nicht unter seine Mindestleistung. Sind nur wenige Heizkörper offen, ist das
Wasser nach wenigen Minuten zu warm und der Brenner geht wieder aus: viele kurze Brennerläufe.
Der Wärmeverbund betrachtet deshalb alle Räume zusammen:

| Baustein | Verhalten |
|---|---|
| Mitheizen, Bedarf bald | Während einer Freigabe heizen Räume mit, die innerhalb des **Horizonts** (Standard 3 h) selbst Wärme bräuchten. Wer am schnellsten auskühlt, kommt zuerst dran. Ziel ist die Temperatur, mit der der Raum den Horizont übersteht, höchstens Soll + **Vorrat** (Standard +1 K). |
| Mitheizen, Kessel-Abnahme | Ist weniger Heizfläche offen, als der Kessel für einen Brennerlauf von 10 min braucht, öffnen weitere Räume bis Soll + Vorrat. |
| Räume in Eco | Nur kurz vor ihrer Komfortzeit (Zeitplan, erwartete Ankunft, Ende der Nacht) und nur bis Komfort. |
| Restwärme | Nach der Freigabe bleiben Räume offen, solange die Pumpe nachläuft und der Vorlauf noch warm ist (höchstens 15 min). |
| Bündeln | Reicht die offene Heizfläche nicht und braucht ein anderer Raum bald Wärme, wartet der Start bis zu 30 min auf ihn. Ein großes Defizit startet sofort. |

Geöffnet wird ein Raum über seine Thermostate: HeatConductor schreibt die **Öffnungstemperatur**
(Standard 25 °C) und setzt das normale Soll zurück, sobald der Raum sein Ziel minus dem gelernten
Nachheizen der Heizkörper erreicht hat. Mitgeheizte Räume zählen nicht zum Wärmebedarf, ihr
offenes Ventil verlängert also keine Freigabe.

Gelernt wird:
- **Benötigte Heizfläche:** Jeder Brennerlauf innerhalb einer Freigabe zeigt, wie lange der
  Brenner bei wie viel offener Heizfläche läuft. Daraus folgt, wie viele voll offene Heizkörper
  eine Ziel-Brennerlaufzeit ergeben. Bis dahin gilt der Startwert von 4 Heizkörpern.
- **Nachheizen je Raum:** wie weit der Raum nach dem Schließen noch wärmer wird. Bis dahin gilt 0,3 K.
- **Auskühlen je Raum:** die schon bekannte Auskühl-Zeitkonstante bestimmt, wann ein Raum Wärme
  braucht. Bis dahin gilt ein gut gedämmter Raum (40 h).

Schutz und Bedienung:
- Nie bei offenem Fenster, Sonnengewinn, Boost, manueller Übersteuerung, Urlaub oder Abwesenheit
  ohne erwartete Ankunft, nachts nur kurz vor dem Aufstehen. Heizt der Kessel trotz Freigabe
  nicht, wird nichts mitgeheizt.
- Neue Vorgänge nur mit 20 % Reserve unter der Duty-Cycle-Grenze, höchstens 6 je Raum und Tag,
  höchstens 2 h je Vorgang. Eine Handänderung am Thermostat wird übernommen und beendet das Mitheizen.
- Ausgeführt wird nur mit Schalter **Wärmeverbund**, eingeschalteter Raumsteuerung und außerhalb
  des Beobachtungsmodus. Sonst zeigt das Panel, was passieren würde (*Vorschau*).
- Je Raum lässt sich das Mitheizen mit dem Schalter **Mitheizen** ausschließen, z. B. für einen
  kaum gedämmten, abgetrennten Raum.
- Wird die Raumsteuerung ausgeschaltet oder HeatConductor neu gestartet, bekommen geöffnete
  Thermostate ihr Soll zurück.

Ob es wirkt, zeigt der Reiter *Lernen*: Freigaben, Brennerstarts, mittlere Laufzeit, Läufe
unter 3 min, Mitheiz-Vorgänge und Gas je Gradtag, getrennt nach Tagen mit und ohne Wärmeverbund.

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
| Störung, Relais-Watchdog | Sicherheitsabschaltung/fehlende Daten, Relais-Rückmeldung, Kessel im Sommerbetrieb, Erreichbarkeit des Watchdogs |
| Vorlauf-Abweichung zum Kessel, Spreizung am Kessel | Rohrfühler gegen Kesselfühler (nur mit Kessel-Vorlauf) |
| Gesamtbedarf | gewichteter Bedarf aller geregelten Räume |
| Außentemperatur (geglättet, Tagesmittel, Vorhersage 12 h) | Grundlage für Heizgrenze und Vorausschau |
| Kessel-/Brennerstarts und -laufzeit heute, Spreizung | Takt-Kontrolle |
| Gasverbrauch, Gasenergie (gesamt/heute/gestern) | m³ bzw. kWh |
| Brennerleistung, Brennermodulation, Brennwertnutzung, Brennwertanteil | Kesselanalyse |
| Gradtagzahl gestern, Energie je Gradtag gestern | witterungsbereinigter Verbrauch |
| je Raum: Thermostat, Solltemperatur, Komfort-/Eco-Temperatur | Raumsteuerung |
| je Raum: Bedarf, Temperatur, Status | Attribute: Soll, Defizit, Ventil, Gewichtung |
| je Raum: Nutzungserkennung, Raum genutzt | nur bei konfigurierten Geräten zur Nutzungserkennung |
| Vorausschauend heizen | an = Räume ohne Zeitplan-Helfer heizen nach erwarteter und tatsächlicher Anwesenheit |
| Wärmeverbund | an = Freigaben heizen weitere Räume mit und nutzen die Restwärme |
| je Raum: Mitheizen, Wird mitgeheizt | Raum darf mitgeheizt werden; mitgeheizt gerade (Attribute: Ziel, Grund, nächster Bedarf, Vorschau) |
| Urlaub | Urlaub aktiv (Attribute: geplant oder automatisch, seit wann, niemand zu Hause seit) |
| Schlafen | Nachtabsenkung aktiv (Attribute: Auslöser, seit wann, Zustand des Schlafsensors) |
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
