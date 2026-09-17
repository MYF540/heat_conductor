/*
 * HeatConductor sidebar panel.
 *
 * Dependency-free web component (no build step). Talks to the integration via
 * the WebSocket commands heat_conductor/* and to the recorder for history.
 * Everyone can view; only admins can change parameters or reset learning.
 */

const I18N = {
  de: {
    title: "HeatConductor",
    tabs: { overview: "Übersicht", params: "Parameter", learning: "Lernen", schedule: "Zeitplan", simulate: "Was-wäre-wenn", log: "Protokoll" },
    loading: "Lade …",
    notLoaded: "HeatConductor ist nicht eingerichtet.",
    refresh: "Aktualisieren",
    boiler: "Kessel",
    state: "Zustand",
    reason: "Grund",
    requestHeat: "Wärmeanforderung",
    burner: "Brenner",
    yes: "ja", no: "nein", unknown: "unbekannt",
    observation: "Beobachtungsmodus", automation: "Automatik", roomControl: "Raumsteuerung",
    on: "an", off: "aus",
    totalDemand: "Gesamtbedarf",
    startThreshold: "Start-Schwelle", stopThreshold: "Stopp-Schwelle",
    timers: "Zeitschutz",
    confirm: "Bestätigung", minRun: "Mindestlaufzeit", minPause: "Mindestpause",
    startsHour: "Starts in der letzten Stunde",
    remaining: "Rest",
    outdoor: "Außen", smoothed: "geglättet", forecast: "Vorhersage 12 h",
    flow: "Vorlauf", return: "Rücklauf", spread: "Spreizung",
    energyToday: "Gas heute", power: "Leistung", modulation: "Modulation",
    rooms: "Räume",
    room: "Raum", temp: "Ist", target: "Soll", source: "Grund", valve: "Ventil", deficit: "Defizit",
    demand: "Bedarf", weight: "Gewicht", status: "Status",
    history: "Verlauf", h24: "24 h", d7: "7 Tage",
    noHistory: "Keine Verlaufsdaten.",
    readOnly: "Nur Administratoren können Parameter ändern.",
    save: "Speichern", discard: "Verwerfen", resetDefault: "Standard", resetAll: "Alle auf Standard",
    changed: "geändert", saved: "Gespeichert", default: "Standard",
    higher: "Höher",
    simulateDraft: "Entwurf simulieren",
    groups: {
      start_stop: "Start und Stopp", cycle_protection: "Takt-Schutz", heating_limit: "Heizgrenze und Frost",
      safety: "Sicherheit", sensors: "Sensorik", energy: "Energie und Gas",
      room_control: "Raumsteuerung", usage: "Nutzungserkennung", learning: "Lernen und Vorausschau",
    },
    learningIntro: "Gelernte Werte mit Anzahl der Messungen und Streuung. Werte werden erst ab 3 Messungen verwendet.",
    heatRate: "Aufheizrate", coolingTau: "Auskühl-Zeitkonstante", deadTime: "Totzeit",
    samples: "Messungen", mean: "Mittel", std: "Streuung", band: "Außentemperatur",
    bands: { all: "gesamt", below_0: "unter 0 °C", "0_5": "0–5 °C", "5_10": "5–10 °C", above_10: "über 10 °C", unknown: "unbekannt" },
    usedFor: "Wofür",
    usedHeat: "Optimaler Start: Wann muss geheizt werden, damit es rechtzeitig warm ist?",
    usedCool: "Vorausschau: Wie schnell kühlt der Raum ohne Heizung aus?",
    usedDead: "Verzögerung zwischen Ventil auf und spürbarer Erwärmung.",
    heatPoints: "Aufheizrate gegen Außentemperatur", coolPoints: "Zeitkonstante gegen Temperaturdifferenz innen–außen",
    learnHistory: "Lernverlauf (Tageswerte)",
    boilerCycles: "Brennerzyklen", runs: "Laufzeiten", pauses: "Pausen",
    heatingCurve: "Heizkurve des Kesselreglers", slope: "Steilheit", flowAt0: "Vorlauf bei 0 °C",
    notEnough: "Noch nicht genug Daten.",
    resetLearning: "Lerndaten zurücksetzen", resetRoom: "Raum zurücksetzen",
    confirmReset: "Gelernte Werte wirklich löschen?",
    simIntro: "Spielt die aufgezeichneten Eingangsdaten mit den aktuellen und den Entwurfs-Parametern durch. Die Raumtemperaturen bleiben die aufgezeichneten, belastbar sind vor allem Starts und Laufzeiten.",
    draft: "Entwurf", current: "Aktuell", hours: "Zeitraum",
    run: "Simulation starten", running: "Simulation läuft …",
    noDraft: "Kein Entwurf – im Reiter Parameter Werte ändern und „Entwurf simulieren“ wählen, oder hier mit aktuellen Werten vergleichen.",
    starts: "Starts", runtime: "Laufzeit (min)", deficitShare: "Zeit mit Defizit > 0,5 K",
    realBurner: "Echter Brenner", minutes: "min",
    simChart: "Bedarf und Anforderung",
    inUse: "Nutzung", used: "genutzt", unused: "frei",
    scheduleTitle: "Gelernter Zeitplan aus der Anwesenheit",
    scheduleIntro: "HeatConductor merkt sich, wann jemand zu Hause ist, und schlägt daraus einen Wochenplan vor. Der Vorschlag gilt für die ganze Anlage. Räume ohne eigenen Zeitplan-Helfer folgen ihm, sobald der Schalter „Gelernter Zeitplan“ eingeschaltet ist.",
    daysObserved: "Beobachtete Tage",
    scheduleReady: "Vorschlag verfügbar", scheduleNotReady: "Sammelt noch Daten",
    presenceHeat: "Anwesenheit je Wochentag (dunkler = häufiger zu Hause)",
    suggestion: "Vorschlag für Komfortzeiten",
    noWindows: "keine Komfortzeit",
    learnedScheduleState: "Schalter „Gelernter Zeitplan“",
    learnedScheduleNow: "Vorschlag gerade",
    comfortNow: "Komfort", ecoNow: "Absenkung",
    weekdays: ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    log: "Änderungsprotokoll", time: "Zeit", user: "Benutzer", parameter: "Parameter", oldValue: "alt", newValue: "neu",
    emptyLog: "Noch keine Änderungen.",
    error: "Fehler",
  },
  en: {
    title: "HeatConductor",
    tabs: { overview: "Overview", params: "Parameters", learning: "Learning", schedule: "Schedule", simulate: "What-if", log: "Change log" },
    loading: "Loading …",
    notLoaded: "HeatConductor is not set up.",
    refresh: "Refresh",
    boiler: "Boiler", state: "State", reason: "Reason", requestHeat: "Heat request", burner: "Burner",
    yes: "yes", no: "no", unknown: "unknown",
    observation: "Observation mode", automation: "Automation", roomControl: "Room control",
    on: "on", off: "off",
    totalDemand: "Total demand", startThreshold: "Start threshold", stopThreshold: "Stop threshold",
    timers: "Timers", confirm: "Confirmation", minRun: "Minimum run", minPause: "Minimum pause",
    startsHour: "Starts in the last hour", remaining: "left",
    outdoor: "Outdoor", smoothed: "smoothed", forecast: "Forecast 12 h",
    flow: "Flow", return: "Return", spread: "Spread",
    energyToday: "Gas today", power: "Power", modulation: "Modulation",
    rooms: "Rooms", room: "Room", temp: "Actual", target: "Target", source: "Source", valve: "Valve", deficit: "Deficit",
    demand: "Demand", weight: "Weight", status: "Status",
    history: "History", h24: "24 h", d7: "7 days", noHistory: "No history.",
    readOnly: "Only administrators can change parameters.",
    save: "Save", discard: "Discard", resetDefault: "Default", resetAll: "Reset all",
    changed: "changed", saved: "Saved", default: "Default", higher: "Higher",
    simulateDraft: "Simulate draft",
    groups: {
      start_stop: "Start and stop", cycle_protection: "Cycle protection", heating_limit: "Heating limit and frost",
      safety: "Safety", sensors: "Sensors", energy: "Energy and gas",
      room_control: "Room control", usage: "Usage detection", learning: "Learning and anticipation",
    },
    learningIntro: "Learned values with sample count and spread. Values are used from 3 samples on.",
    heatRate: "Heat-up rate", coolingTau: "Cooling time constant", deadTime: "Dead time",
    samples: "Samples", mean: "Mean", std: "Spread", band: "Outdoor temperature",
    bands: { all: "all", below_0: "below 0 °C", "0_5": "0–5 °C", "5_10": "5–10 °C", above_10: "above 10 °C", unknown: "unknown" },
    usedFor: "Used for",
    usedHeat: "Optimum start: when heating must begin to be warm in time.",
    usedCool: "Anticipation: how fast the room cools without heating.",
    usedDead: "Delay between valve opening and noticeable warming.",
    heatPoints: "Heat-up rate vs. outdoor temperature", coolPoints: "Time constant vs. indoor–outdoor difference",
    learnHistory: "Learning history (daily values)",
    boilerCycles: "Burner cycles", runs: "Run times", pauses: "Pauses",
    heatingCurve: "Heating curve of the boiler controller", slope: "Slope", flowAt0: "Flow at 0 °C",
    notEnough: "Not enough data yet.",
    resetLearning: "Reset learning", resetRoom: "Reset room", confirmReset: "Really delete learned values?",
    simIntro: "Replays recorded inputs with the current and the draft parameters. Room temperatures stay as recorded, so starts and run times are the reliable results.",
    draft: "Draft", current: "Current", hours: "Period",
    run: "Run simulation", running: "Simulation running …",
    noDraft: "No draft – change values in the Parameters tab and choose “Simulate draft”, or compare current values here.",
    starts: "Starts", runtime: "Run time (min)", deficitShare: "Time with deficit > 0.5 K",
    realBurner: "Real burner", minutes: "min", simChart: "Demand and request",
    inUse: "Usage", used: "in use", unused: "free",
    scheduleTitle: "Learned schedule from presence",
    scheduleIntro: "HeatConductor learns when somebody is at home and suggests a weekly schedule from it. The suggestion applies to the whole installation. Rooms without their own schedule helper follow it once the switch \u201cLearned schedule\u201d is on.",
    daysObserved: "Days observed",
    scheduleReady: "Suggestion available", scheduleNotReady: "Still collecting data",
    presenceHeat: "Presence per weekday (darker = at home more often)",
    suggestion: "Suggested comfort periods",
    noWindows: "no comfort period",
    learnedScheduleState: "Switch \u201cLearned schedule\u201d",
    learnedScheduleNow: "Suggestion right now",
    comfortNow: "Comfort", ecoNow: "Setback",
    weekdays: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    log: "Change log", time: "Time", user: "User", parameter: "Parameter", oldValue: "old", newValue: "new",
    emptyLog: "No changes yet.", error: "Error",
  },
};

const PARAM_TEXT = {
  de: {
    start_threshold: ["Start-Schwelle (Gesamtbedarf)", "Gewichteter Bedarf aller Räume, ab dem der Kessel starten darf.", "Weniger, dafür längere Brennerläufe; Räume kühlen etwas stärker aus."],
    start_confirm: ["Bestätigungszeit", "So lange muss der Bedarf über der Start-Schwelle liegen.", "Kurze Bedarfsspitzen (z. B. Lüften) lösen keinen Start aus; Reaktion träger."],
    stop_threshold: ["Stopp-Schwelle (Gesamtbedarf)", "Unter diesem Bedarf darf der Kessel ausgehen.", "Kessel geht früher aus, Restwärme wird stärker genutzt."],
    immediate_start_deficit: ["Sofortstart ab Raumdefizit", "Liegt ein Raum so weit unter Soll, startet der Kessel ohne Bestätigung.", "Seltener Sofortstarts, einzelne kalte Räume warten länger."],
    deficit_full_scale: ["Defizit für 100 % Raumbedarf", "Umrechnung Temperaturdefizit in Raumbedarf.", "Defizite wirken schwächer, die Ventilöffnung dominiert."],
    min_run: ["Mindestlaufzeit", "Kürzeste Brennerlaufzeit nach einem Start.", "Weniger Takten, mögliche Überschwinger der Raumtemperatur."],
    min_pause: ["Mindestpause", "Kürzeste Pause zwischen zwei Starts.", "Weniger Starts, längere Wartezeit bei neuem Bedarf."],
    max_starts_per_hour: ["Max. Starts pro Stunde", "Harte Obergrenze für Brennerstarts.", "Mehr Flexibilität, mehr Verschleiß."],
    heating_limit: ["Heizgrenze", "Über dieser geglätteten Außentemperatur bleibt der Kessel aus (außer Komfort, Frostschutz oder kalte Vorhersage).", "Heizt auch an milderen Tagen."],
    outdoor_smoothing: ["Glättung Außentemperatur", "Zeitkonstante der Glättung für die Heizgrenze.", "Kurze Warm- oder Kaltphasen ändern den Modus weniger."],
    frost_limit: ["Frostschutz-Raumtemperatur", "Unterschreitet ein Raum diesen Wert, heizt der Kessel immer.", "Frostschutz greift früher."],
    max_flow_temperature: ["Max. Vorlauftemperatur", "Darüber sofortige Abschaltung.", "Abschaltung erst bei höherer Temperatur."],
    stale_after: ["Werte veraltet nach", "Ältere Messwerte werden ignoriert.", "Toleranter bei selten sendenden Sensoren, erkennt Ausfälle später."],
    manual_override: ["Pause nach manuellem Schalten", "So lange respektiert die Automatik ein manuelles Schalten des Relais.", "Längere Übersteuerung durch den Nutzer."],
    burner_flow_threshold: ["Brenner-an-Schwelle Gasdurchfluss", "Ab diesem Durchfluss gilt der Brenner als an.", "Kurzes Zünden oder Nachlaufen wird nicht als Start gezählt."],
    calorific_value: ["Brennwert Hs", "Brennwert laut Gasabrechnung.", "Mehr kWh je m³ (gilt für ab jetzt erfassten Verbrauch)."],
    z_factor: ["Zustandszahl", "Umrechnung des gemessenen Volumens auf Normbedingungen, siehe Gasabrechnung.", "Mehr kWh je m³."],
    burner_max_power: ["Nennbelastung (Typenschild)", "Maximale Belastung Q (Hi) in kW. Grundlage der Modulationsanzeige, 0 = unbekannt.", "Angezeigte Modulation sinkt."],
    condensing_return_limit: ["Rücklaufgrenze Brennwertnutzung", "Unter dieser Rücklauftemperatur gilt der Betrieb als kondensierend.", "Brennwertnutzung wird großzügiger bewertet."],
    default_comfort: ["Standard-Komforttemperatur", "Anfangswert für neue Räume, je Raum änderbar.", "Neue Räume starten wärmer."],
    default_eco: ["Standard-Eco-Temperatur", "Anfangswert der Absenkung für neue Räume.", "Neue Räume senken weniger ab."],
    vacation_temperature: ["Urlaubstemperatur", "Solltemperatur aller Räume im Urlaub.", "Wärmer im Urlaub, mehr Verbrauch."],
    frost_temperature: ["Frostschutz-Sollwert", "Solltemperatur ausgeschalteter Räume oder bei Modus Aus/Frostschutz.", "Mehr Schutz, mehr Verbrauch."],
    window_temperature: ["Temperatur bei offenem Fenster", "Solltemperatur, solange ein Fenster offen ist.", "Weniger Absenkung beim Lüften."],
    boost_temperature: ["Boost-Temperatur", "Solltemperatur während eines Boosts.", "Schnelleres Aufheizen, mehr Verbrauch."],
    boost_duration: ["Boost-Dauer", "Standarddauer eines Boosts.", "Längerer Boost."],
    override_duration: ["Dauer manueller Übersteuerung", "Manuelle Solltemperatur gilt so lange oder bis zum nächsten Zeitplanwechsel.", "Handänderungen bleiben länger bestehen."],
    write_interval: ["Mindestabstand Schreibvorgänge", "Nachführung der Thermostate höchstens so oft; Sollwertwechsel sofort.", "Schont Batterien und Funk, Korrekturen folgen langsamer."],
    compensation_max: ["Max. Sensorkorrektur", "Begrenzt die Korrektur zwischen Thermostat- und Raumsensor-Temperatur.", "Größere Abweichungen werden ausgeglichen."],
    duty_cycle_limit: ["Duty-Cycle-Grenze", "Oberhalb keine automatischen Schreibvorgänge.", "Mehr Schreibvorgänge bei hoher Funklast."],
    force_manual_mode: ["Thermostate auf manuell stellen", "Verhindert, dass eigene Zeitprofile der Thermostate gegensteuern.", null],
    adopt_trv_changes: ["Änderungen am Thermostat übernehmen", "Von Hand verstellte Thermostate werden zur vorübergehenden Raumübersteuerung.", null],
    usage_hold: ["Nachlaufzeit Nutzung", "So lange gilt ein Raum nach der letzten Aktivität noch als genutzt.", "Der Raum bleibt länger auf Komfort, weniger Takten bei kurzen Pausen."],
    usage_in_eco: ["Nutzung hebt Absenkung auf", "Ein genutzter Raum wird auch in Absenkphasen auf Komforttemperatur geheizt.", null],
    optimum_start: ["Optimaler Start", "Heizt früh genug, damit zum Zeitplanbeginn die Komforttemperatur erreicht ist.", null],
    optimum_start_max_lead: ["Max. Vorlaufzeit optimaler Start", "Längste Zeit, die vor Zeitplanbeginn geheizt wird.", "Früherer Start bei großem Temperaturabstand."],
    residual_heat: ["Restwärme nutzen", "Stoppt den Brenner, wenn alle Räume über Soll liegen.", null],
    use_forecast: ["Wettervorhersage nutzen", "Kalte Vorhersagen heben die Heizgrenze auf und verlängern den optimalen Start.", null],
    solar_reference: ["PV-Spitzenleistung (Sonnen-Proxy)", "Räume mit Sonnengewinnen ignorieren ihr Defizit ab 40 % dieser Leistung. 0 = aus.", "Sonnen-Proxy greift erst bei stärkerer Sonne."],
  },
  en: {
    start_threshold: ["Start threshold (total demand)", "Weighted demand of all rooms from which the boiler may start.", "Fewer but longer burner runs; rooms cool down a little more."],
    start_confirm: ["Confirmation time", "Demand must stay above the start threshold this long.", "Short spikes (e.g. airing) do not start the boiler; slower reaction."],
    stop_threshold: ["Stop threshold (total demand)", "Below this demand the boiler may stop.", "Stops earlier, uses more residual heat."],
    immediate_start_deficit: ["Immediate start at room deficit", "A room this far below target starts the boiler without confirmation.", "Fewer immediate starts, single cold rooms wait longer."],
    deficit_full_scale: ["Deficit for 100 % room demand", "Conversion from temperature deficit to room demand.", "Deficits count less, valve opening dominates."],
    min_run: ["Minimum run time", "Shortest burner run after a start.", "Less cycling, possible temperature overshoot."],
    min_pause: ["Minimum pause", "Shortest pause between two starts.", "Fewer starts, longer wait for new demand."],
    max_starts_per_hour: ["Max starts per hour", "Hard limit for burner starts.", "More flexibility, more wear."],
    heating_limit: ["Heating limit", "Above this smoothed outdoor temperature the boiler stays off (except comfort, frost protection or cold forecast).", "Heats on milder days too."],
    outdoor_smoothing: ["Outdoor smoothing", "Time constant of the smoothing used for the heating limit.", "Short warm or cold spells change the mode less."],
    frost_limit: ["Frost protection room temperature", "If a room falls below, the boiler always heats.", "Frost protection acts earlier."],
    max_flow_temperature: ["Max flow temperature", "Immediate shutdown above.", "Shutdown only at a higher temperature."],
    stale_after: ["Values outdated after", "Older readings are ignored.", "More tolerant with rarely reporting sensors, detects failures later."],
    manual_override: ["Pause after manual switching", "How long automation respects manual relay switching.", "Longer manual override."],
    burner_flow_threshold: ["Burner-on gas flow", "Gas flow from which the burner counts as on.", "Short ignitions are not counted as starts."],
    calorific_value: ["Calorific value Hs", "From the gas bill.", "More kWh per m³ (for consumption recorded from now on)."],
    z_factor: ["Conversion factor", "Converts metered volume to standard conditions, see gas bill.", "More kWh per m³."],
    burner_max_power: ["Rated load (type plate)", "Maximum load Q (Hi) in kW, basis of modulation. 0 = unknown.", "Displayed modulation decreases."],
    condensing_return_limit: ["Return limit for condensing", "Below this return temperature operation counts as condensing.", "Condensing is rated more generously."],
    default_comfort: ["Default comfort temperature", "Initial value for new rooms, adjustable per room.", "New rooms start warmer."],
    default_eco: ["Default eco temperature", "Initial setback for new rooms.", "New rooms set back less."],
    vacation_temperature: ["Vacation temperature", "Target of all rooms during a vacation.", "Warmer during vacation, more consumption."],
    frost_temperature: ["Frost protection setpoint", "Target of switched-off rooms or in mode off/frost protection.", "More protection, more consumption."],
    window_temperature: ["Window open temperature", "Target while a window is open.", "Less setback while airing."],
    boost_temperature: ["Boost temperature", "Target during a boost.", "Faster heat-up, more consumption."],
    boost_duration: ["Boost duration", "Default duration of a boost.", "Longer boost."],
    override_duration: ["Manual override duration", "A manual target lasts this long or until the next schedule change.", "Manual changes last longer."],
    write_interval: ["Minimum write interval", "Thermostat corrections at most this often; target changes immediately.", "Saves batteries and radio, corrections follow slower."],
    compensation_max: ["Max sensor compensation", "Limits the correction between thermostat and room sensor.", "Larger differences are compensated."],
    duty_cycle_limit: ["Duty cycle limit", "No automatic writes above.", "More writes despite high radio load."],
    force_manual_mode: ["Switch thermostats to manual", "Prevents thermostat schedules from working against HeatConductor.", null],
    adopt_trv_changes: ["Adopt changes at the thermostat", "Manually turned thermostats become a temporary room override.", null],
    usage_hold: ["Usage hold time", "How long a room still counts as in use after the last activity.", "The room stays at comfort longer, less cycling during short breaks."],
    usage_in_eco: ["Usage overrides setback", "A room in use is heated to comfort during setback periods as well.", null],
    optimum_start: ["Optimum start", "Heats early enough to reach comfort temperature when the schedule begins.", null],
    optimum_start_max_lead: ["Max optimum start lead", "Longest heating time before the schedule begins.", "Earlier start for large temperature gaps."],
    residual_heat: ["Use residual heat", "Stops the burner when all rooms are above target.", null],
    use_forecast: ["Use weather forecast", "Cold forecasts release the heating limit and extend optimum start.", null],
    solar_reference: ["PV peak power (sun proxy)", "Rooms with solar gains ignore their deficit above 40 % of this power. 0 = off.", "Sun proxy only reacts to stronger sun."],
  },
};

const STATE_TEXT = {
  de: {
    starting: "Startet", off: "Aus", heating: "Heizt", frost_protection: "Frostschutz", summer: "Sommer",
    manual: "Manuell", disabled: "Deaktiviert", failsafe: "Sicherheitsabschaltung",
  },
  en: {
    starting: "Starting", off: "Off", heating: "Heating", frost_protection: "Frost protection", summer: "Summer",
    manual: "Manual", disabled: "Disabled", failsafe: "Failsafe",
  },
};

const REASON_TEXT = {
  de: {
    startup: "Start, warte auf Daten", automation_disabled: "Automatik deaktiviert", manual_override: "Manuell geschaltet",
    relay_unavailable: "Relais nicht erreichbar", no_data: "Keine gültigen Raumdaten", overtemperature: "Vorlauf zu heiß",
    frost_protection: "Frostschutz", mode_off: "Modus Aus", frost_only: "Nur Frostschutz", summer_mode: "Heizgrenze überschritten",
    no_demand: "Kein Wärmebedarf", waiting_confirmation: "Bedarf wird bestätigt", waiting_min_pause: "Wartet auf Mindestpause",
    waiting_max_starts: "Max. Starts pro Stunde erreicht", demand_start: "Start wegen Wärmebedarf",
    deficit_start: "Start wegen Temperaturdefizit", demand_continues: "Heizt, Bedarf besteht", min_runtime: "Mindestlaufzeit",
    demand_satisfied: "Bedarf gedeckt", residual_heat: "Restwärme reicht aus",
  },
  en: {
    startup: "Starting, waiting for data", automation_disabled: "Automation disabled", manual_override: "Switched manually",
    relay_unavailable: "Relay unavailable", no_data: "No valid room data", overtemperature: "Flow temperature too high",
    frost_protection: "Frost protection", mode_off: "Mode off", frost_only: "Frost protection only", summer_mode: "Heating limit exceeded",
    no_demand: "No heat demand", waiting_confirmation: "Confirming demand", waiting_min_pause: "Waiting for minimum pause",
    waiting_max_starts: "Maximum starts per hour reached", demand_start: "Started on heat demand",
    deficit_start: "Started on temperature deficit", demand_continues: "Heating, demand continues", min_runtime: "Minimum run time",
    demand_satisfied: "Demand satisfied", residual_heat: "Residual heat is sufficient",
  },
};

const SOURCE_TEXT = {
  de: {
    window: "Fenster offen", room_off: "Raum aus", boost: "Boost", override: "Manuell", mode_off: "Modus Aus",
    frost_protection: "Frostschutz", vacation: "Urlaub", away: "Abwesend (Modus)", eco: "Eco (Modus)", comfort: "Komfort (Modus)",
    absent: "Niemand zu Hause", no_schedule: "Kein Zeitplan", schedule_comfort: "Zeitplan Komfort", schedule_eco: "Zeitplan Eco",
    optimum_start: "Optimaler Start", usage_active: "Raum genutzt", usage_idle: "Raum ungenutzt",
  },
  en: {
    window: "Window open", room_off: "Room off", boost: "Boost", override: "Manual", mode_off: "Mode off",
    frost_protection: "Frost protection", vacation: "Vacation", away: "Away (mode)", eco: "Eco (mode)", comfort: "Comfort (mode)",
    absent: "Nobody home", no_schedule: "No schedule", schedule_comfort: "Schedule comfort", schedule_eco: "Schedule eco",
    optimum_start: "Optimum start", usage_active: "Room in use", usage_idle: "Room unused",
  },
};

const ROOM_STATUS_TEXT = {
  de: { ok: "OK", degraded: "Teilweise Daten", stale: "Keine Daten", window_open: "Fenster offen", monitor_only: "Nur überwacht" },
  en: { ok: "OK", degraded: "Partial data", stale: "No data", window_open: "Window open", monitor_only: "Monitor only" },
};

const COLORS = ["#ff5722", "#1e88e5", "#43a047", "#8e24aa", "#fdd835", "#00897b", "#6d4c41"];

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function fmt(value, digits = 1, unit = "") {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return `${Number(value).toFixed(digits)}${unit ? " " + unit : ""}`;
}

/* ---------------------------------------------------------------- charts */

function timeChart({ series, height = 180, yUnit = "", thresholds = [], yMin, yMax, lang }) {
  const width = 900;
  const pad = { l: 44, r: 12, t: 10, b: 24 };
  const all = series.flatMap((s) => s.points);
  if (!all.length) return "";
  const xs = all.map((p) => p[0]);
  const ys = all.map((p) => p[1]).filter((v) => v !== null && Number.isFinite(v));
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  let lo = yMin ?? Math.min(...ys, ...thresholds.map((t) => t.value));
  let hi = yMax ?? Math.max(...ys, ...thresholds.map((t) => t.value));
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return "";
  if (hi - lo < 1e-6) { hi += 1; lo -= 1; }
  const span = hi - lo;
  if (yMin === undefined) lo -= span * 0.05;
  if (yMax === undefined) hi += span * 0.05;
  const sx = (x) => pad.l + ((x - x0) / Math.max(x1 - x0, 1)) * (width - pad.l - pad.r);
  const sy = (y) => pad.t + (1 - (y - lo) / (hi - lo)) * (height - pad.t - pad.b);

  const grid = [];
  for (let i = 0; i <= 4; i++) {
    const v = lo + ((hi - lo) * i) / 4;
    const y = sy(v);
    grid.push(`<line x1="${pad.l}" x2="${width - pad.r}" y1="${y}" y2="${y}" class="grid"/>`);
    grid.push(`<text x="${pad.l - 6}" y="${y + 4}" class="axis" text-anchor="end">${esc(fmt(v, span < 5 ? 1 : 0))}</text>`);
  }
  const ticks = 6;
  for (let i = 0; i <= ticks; i++) {
    const t = x0 + ((x1 - x0) * i) / ticks;
    const d = new Date(t);
    const label = x1 - x0 > 2 * 86400000
      ? d.toLocaleDateString(lang, { weekday: "short", day: "numeric" })
      : d.toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" });
    grid.push(`<text x="${sx(t)}" y="${height - 6}" class="axis" text-anchor="middle">${esc(label)}</text>`);
  }
  const lines = series.map((s, i) => {
    const color = s.color || COLORS[i % COLORS.length];
    let d = "";
    let prev = null;
    for (const [x, y] of s.points) {
      if (y === null || !Number.isFinite(y)) { prev = null; continue; }
      if (prev === null) d += `M${sx(x)},${sy(y)}`;
      else if (s.step) d += `H${sx(x)}V${sy(y)}`;
      else d += `L${sx(x)},${sy(y)}`;
      prev = y;
    }
    if (s.step && s.points.length && prev !== null) d += `H${sx(x1)}`;
    const fill = s.area ? `<path d="${d}V${sy(lo)}H${sx(s.points[0][0])}Z" fill="${color}" opacity="0.15"/>` : "";
    return `${fill}<path d="${d}" fill="none" stroke="${color}" stroke-width="${s.width || 2}"/>`;
  });
  const marks = thresholds.map((t, i) =>
    `<line x1="${pad.l}" x2="${width - pad.r}" y1="${sy(t.value)}" y2="${sy(t.value)}" stroke="${t.color}" stroke-dasharray="6 4"/>` +
    `<text x="${i % 2 ? pad.l + 4 : width - pad.r - 4}" y="${sy(t.value) - 4}" class="axis" text-anchor="${i % 2 ? "start" : "end"}" fill="${t.color}">${esc(t.label)}</text>`);
  const legend = series.map((s, i) =>
    `<span class="legend"><i style="background:${s.color || COLORS[i % COLORS.length]}"></i>${esc(s.name)}</span>`).join("");
  return `<div class="chart"><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${grid.join("")}${marks.join("")}${lines.join("")}</svg><div class="legends">${legend}${yUnit ? `<span class="legend unit">${esc(yUnit)}</span>` : ""}</div></div>`;
}

function scatterChart({ points, xLabel, yLabel, line = null, height = 200 }) {
  if (!points || !points.length) return "";
  const width = 420;
  const pad = { l: 44, r: 10, t: 10, b: 34 };
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (x1 - x0 < 1e-6) { x0 -= 1; x1 += 1; }
  if (y1 - y0 < 1e-6) { y0 -= 1; y1 += 1; }
  const sx = (x) => pad.l + ((x - x0) / (x1 - x0)) * (width - pad.l - pad.r);
  const sy = (y) => pad.t + (1 - (y - y0) / (y1 - y0)) * (height - pad.t - pad.b);
  const dots = points.map((p) => `<circle cx="${sx(p[0])}" cy="${sy(p[1])}" r="3" class="dot"/>`).join("");
  let fit = "";
  if (line) {
    const [a, b] = line;
    fit = `<line x1="${sx(x0)}" y1="${sy(a * x0 + b)}" x2="${sx(x1)}" y2="${sy(a * x1 + b)}" class="fit"/>`;
  }
  const axes = [
    `<text x="${pad.l - 6}" y="${sy(y1) + 4}" class="axis" text-anchor="end">${esc(fmt(y1))}</text>`,
    `<text x="${pad.l - 6}" y="${sy(y0)}" class="axis" text-anchor="end">${esc(fmt(y0))}</text>`,
    `<text x="${sx(x0)}" y="${height - 18}" class="axis">${esc(fmt(x0))}</text>`,
    `<text x="${sx(x1)}" y="${height - 18}" class="axis" text-anchor="end">${esc(fmt(x1))}</text>`,
    `<text x="${(width + pad.l) / 2}" y="${height - 4}" class="axis" text-anchor="middle">${esc(xLabel)}</text>`,
    `<line x1="${pad.l}" y1="${height - pad.b}" x2="${width - pad.r}" y2="${height - pad.b}" class="grid"/>`,
    `<line x1="${pad.l}" y1="${pad.t}" x2="${pad.l}" y2="${height - pad.b}" class="grid"/>`,
  ];
  return `<div class="chart small"><div class="chart-title">${esc(yLabel)}</div><svg viewBox="0 0 ${width} ${height}">${axes.join("")}${fit}${dots}</svg></div>`;
}

/* Weekly presence heatmap: one row per weekday, one cell per time slot. */
function presenceChart({ grid, slotMinutes, days }) {
  const slots = grid[0].length;
  const cell = 14;
  const rowHeight = 22;
  const left = 34;
  const top = 16;
  const width = left + slots * cell + 8;
  const height = top + grid.length * rowHeight + 18;
  const cells = grid.map((day, d) => day.map((value, i) => {
    const x = left + i * cell;
    const y = top + d * rowHeight;
    const known = value !== null && value !== undefined;
    const fill = known ? `rgba(255,138,0,${(0.08 + 0.92 * value).toFixed(3)})` : "rgba(128,128,128,0.12)";
    const label = known ? `${days[d]} ${String(Math.floor(i * slotMinutes / 60)).padStart(2, "0")}:${String((i * slotMinutes) % 60).padStart(2, "0")} – ${Math.round(value * 100)} %` : "";
    return `<rect x="${x}" y="${y}" width="${cell - 1}" height="${rowHeight - 3}" fill="${fill}"><title>${esc(label)}</title></rect>`;
  }).join("")).join("");
  const rowLabels = grid.map((_day, d) =>
    `<text x="${left - 6}" y="${top + d * rowHeight + rowHeight / 2}" class="axis" text-anchor="end" dominant-baseline="middle">${esc(days[d].slice(0, 2))}</text>`).join("");
  const hours = [];
  for (let hour = 0; hour <= 24; hour += 3) {
    const x = left + (hour * 60 / slotMinutes) * cell;
    hours.push(`<text x="${x}" y="${height - 4}" class="axis" text-anchor="middle">${hour}</text>`);
  }
  return `<div class="chart"><svg viewBox="0 0 ${width} ${height}">${cells}${rowLabels}${hours.join("")}</svg></div>`;
}

function barChart({ values, labels, title, height = 150 }) {
  const width = 420;
  const max = Math.max(1, ...values);
  const bw = (width - 20) / values.length;
  const bars = values.map((v, i) => {
    const h = (v / max) * (height - 40);
    const x = 10 + i * bw;
    return `<rect x="${x + 4}" y="${height - 24 - h}" width="${bw - 8}" height="${h}" class="bar"/>` +
      `<text x="${x + bw / 2}" y="${height - 28 - h}" class="axis" text-anchor="middle">${v}</text>` +
      `<text x="${x + bw / 2}" y="${height - 8}" class="axis" text-anchor="middle">${esc(labels[i])}</text>`;
  }).join("");
  return `<div class="chart small"><div class="chart-title">${esc(title)}</div><svg viewBox="0 0 ${width} ${height}">${bars}</svg></div>`;
}

/* ----------------------------------------------------------------- panel */

class HeatConductorPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "overview";
    this._state = null;
    this._params = null;
    this._draft = {};
    this._learning = null;
    this._changelog = null;
    this._history = null;
    this._historyRange = 24;
    this._simulation = null;
    this._simHours = 24;
    this._busy = false;
    this._message = null;
    this._error = null;
    this._timer = null;
    this.shadowRoot.addEventListener("click", (e) => this._onClick(e));
    this.shadowRoot.addEventListener("change", (e) => this._onChange(e));
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._init();
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) { menu.hass = hass; menu.narrow = this._narrow; }
  }

  set narrow(value) {
    this._narrow = value;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) menu.narrow = value;
  }

  set panel(value) { this._panel = value; }
  set route(value) { this._route = value; }

  connectedCallback() {
    if (this._hass && !this._timer) this._startTimer();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._timer = null;
  }

  get lang() {
    return (this._hass?.language || "en").startsWith("de") ? "de" : "en";
  }

  t(path) {
    return path.split(".").reduce((o, k) => (o ? o[k] : undefined), I18N[this.lang]) ?? path;
  }

  get isAdmin() {
    return Boolean(this._hass?.user?.is_admin);
  }

  async _ws(message) {
    return this._hass.callWS(message);
  }

  async _init() {
    this._render();
    this._startTimer();
    await this._loadState();
    await this._loadHistory();
  }

  _startTimer() {
    clearInterval(this._timer);
    this._timer = setInterval(() => {
      if (this._tab === "overview") this._loadState();
    }, 15000);
  }

  async _loadState() {
    try {
      this._state = await this._ws({ type: "heat_conductor/state" });
      this._error = null;
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
  }

  async _loadParams() {
    try {
      this._params = await this._ws({ type: "heat_conductor/params" });
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
  }

  async _loadLearning() {
    try {
      this._learning = await this._ws({ type: "heat_conductor/learning" });
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
  }

  async _loadChangelog() {
    try {
      this._changelog = (await this._ws({ type: "heat_conductor/changelog" })).entries;
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
  }

  async _loadHistory() {
    if (!this._state) return;
    const map = { ...this._state.history_entities };
    for (const room of this._state.rooms) {
      if (room.temperature_entity) map[`room_${room.room_id}`] = room.temperature_entity;
    }
    const ids = Object.values(map).filter(Boolean);
    if (!ids.length) return;
    const end = new Date();
    const start = new Date(end.getTime() - this._historyRange * 3600000);
    try {
      const result = await this._ws({
        type: "history/history_during_period",
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        entity_ids: ids,
        minimal_response: true,
        no_attributes: true,
        significant_changes_only: false,
      });
      const byKey = {};
      for (const [key, entityId] of Object.entries(map)) {
        const rows = result[entityId] || [];
        byKey[key] = rows.map((row) => [((row.lu ?? row.lc) || 0) * 1000, row.s]);
      }
      this._history = { map, data: byKey, start: start.getTime(), end: end.getTime() };
    } catch (err) {
      this._history = { error: err.message || String(err) };
    }
    this._render();
  }

  /* ------------------------------------------------------------ events */

  async _onClick(event) {
    const el = event.target.closest("[data-action]");
    if (!el) return;
    const action = el.dataset.action;
    if (action === "tab") {
      this._tab = el.dataset.tab;
      this._message = null;
      if (this._tab === "overview") { await this._loadState(); this._loadHistory(); }
      if (this._tab === "params" || this._tab === "simulate") await this._loadParams();
      if (this._tab === "learning" || this._tab === "schedule") await this._loadLearning();
      if (this._tab === "log") await this._loadChangelog();
      this._render();
    } else if (action === "refresh") {
      await this._loadState();
      this._loadHistory();
    } else if (action === "range") {
      this._historyRange = Number(el.dataset.hours);
      this._render();
      this._loadHistory();
    } else if (action === "reset-param") {
      const meta = this._params.params.find((p) => p.key === el.dataset.key);
      this._draft[meta.key] = meta.default;
      this._render();
    } else if (action === "discard") {
      this._draft = {};
      this._render();
    } else if (action === "save") {
      await this._saveParams();
    } else if (action === "reset-all") {
      for (const meta of this._params.params) this._draft[meta.key] = meta.default;
      this._render();
    } else if (action === "simulate-draft") {
      this._tab = "simulate";
      this._render();
    } else if (action === "run-sim") {
      await this._runSimulation();
    } else if (action === "sim-hours") {
      this._simHours = Number(el.dataset.hours);
      this._render();
    } else if (action === "reset-learning") {
      if (!confirm(this.t("confirmReset"))) return;
      const msg = { type: "heat_conductor/learning/reset" };
      if (el.dataset.room) msg.room_id = el.dataset.room;
      await this._ws(msg);
      await this._loadLearning();
    }
  }

  _onChange(event) {
    const el = event.target;
    if (!el.dataset || !el.dataset.param) return;
    const meta = this._params.params.find((p) => p.key === el.dataset.param);
    let value = meta.boolean ? el.checked : Number(el.value);
    if (!meta.boolean && !Number.isFinite(value)) return;
    if (value === meta.value) delete this._draft[meta.key];
    else this._draft[meta.key] = value;
    this._render();
  }

  async _saveParams() {
    const values = {};
    for (const [key, value] of Object.entries(this._draft)) {
      const meta = this._params.params.find((p) => p.key === key);
      if (meta && value !== meta.value) values[key] = value;
    }
    if (!Object.keys(values).length) return;
    this._busy = true;
    this._render();
    try {
      await this._ws({ type: "heat_conductor/params/set", values });
      this._draft = {};
      this._message = this.t("saved");
      await this._loadParams();
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._busy = false;
    this._render();
  }

  async _runSimulation() {
    this._busy = true;
    this._simulation = null;
    this._render();
    try {
      this._simulation = await this._ws({ type: "heat_conductor/simulate", values: this._draft, hours: this._simHours });
      this._error = null;
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._busy = false;
    this._render();
  }

  /* ------------------------------------------------------------ render */

  _render() {
    const tabs = ["overview", "params", "learning", "schedule", "simulate", "log"];
    let body = "";
    if (!this._state && !this._error) body = `<div class="card">${this.t("loading")}</div>`;
    else if (this._tab === "overview") body = this._renderOverview();
    else if (this._tab === "params") body = this._renderParams();
    else if (this._tab === "learning") body = this._renderLearning();
    else if (this._tab === "schedule") body = this._renderSchedule();
    else if (this._tab === "simulate") body = this._renderSimulate();
    else if (this._tab === "log") body = this._renderLog();

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="header">
        <ha-menu-button></ha-menu-button>
        <div class="title">${this.t("title")}</div>
        <div class="tabs">${tabs.map((tab) => `<button class="tab ${tab === this._tab ? "active" : ""}" data-action="tab" data-tab="${tab}">${this.t(`tabs.${tab}`)}</button>`).join("")}</div>
      </div>
      <div class="content">
        ${this._error ? `<div class="card error">${this.t("error")}: ${esc(this._error)}</div>` : ""}
        ${this._message ? `<div class="card ok">${esc(this._message)}</div>` : ""}
        ${body}
      </div>`;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu && this._hass) { menu.hass = this._hass; menu.narrow = this._narrow; }
  }

  _renderOverview() {
    const s = this._state;
    if (!s) return "";
    if (!s.loaded) return `<div class="card">${this.t("notLoaded")}</div>`;
    const lang = this.lang;
    const d = s.decision;
    const p = s.params;
    const demand = s.demand.total === null ? null : s.demand.total * 100;

    const machine = this._renderStateMachine(d.state);
    const gauge = `
      <div class="gauge">
        <div class="gauge-fill" style="width:${Math.min(demand ?? 0, 100)}%"></div>
        <div class="gauge-mark start" style="left:${p.start_threshold}%" title="${this.t("startThreshold")}"></div>
        <div class="gauge-mark stop" style="left:${p.stop_threshold}%" title="${this.t("stopThreshold")}"></div>
      </div>
      <div class="gauge-legend"><span>${this.t("totalDemand")}: <b>${fmt(demand, 0, "%")}</b></span>
      <span class="start">▲ ${this.t("startThreshold")} ${p.start_threshold} %</span>
      <span class="stop">▲ ${this.t("stopThreshold")} ${p.stop_threshold} %</span></div>`;

    const remaining = d.remaining_seconds;
    const timer = (label, active, totalMin) => {
      const pct = active && remaining !== null && totalMin > 0 ? Math.max(0, Math.min(100, 100 - (remaining / 60 / totalMin) * 100)) : 0;
      return `<div class="timer ${active ? "active" : ""}"><span>${label}</span><div class="bar-bg"><div class="bar-fg" style="width:${pct}%"></div></div><span>${active && remaining !== null ? `${fmt(remaining / 60, 0)} ${this.t("minutes")} ${this.t("remaining")}` : ""}</span></div>`;
    };
    const timers = `
      ${timer(this.t("confirm"), d.reason === "waiting_confirmation", p.start_confirm)}
      ${timer(this.t("minRun"), d.reason === "min_runtime", p.min_run)}
      ${timer(this.t("minPause"), d.reason === "waiting_min_pause", p.min_pause)}
      <div class="timer"><span>${this.t("startsHour")}</span><div class="bar-bg"><div class="bar-fg warn" style="width:${Math.min(100, (d.starts_last_hour / p.max_starts_per_hour) * 100)}%"></div></div><span>${d.starts_last_hour} / ${p.max_starts_per_hour}</span></div>`;

    const e = s.energy;
    const facts = [
      [this.t("outdoor"), `${fmt(s.outdoor.value, 1, "°C")} (${this.t("smoothed")} ${fmt(s.outdoor.smoothed, 1, "°C")})`],
      [this.t("forecast"), fmt(s.outdoor.forecast_12h, 1, "°C")],
      [this.t("flow") + " / " + this.t("return"), `${fmt(s.boiler.flow_temperature, 1)} / ${fmt(s.boiler.return_temperature, 1, "°C")}`],
      [this.t("burner"), s.boiler.burner_active === null ? this.t("unknown") : s.boiler.burner_active ? this.t("on") : this.t("off")],
      [this.t("energyToday"), e.has_gas_source ? fmt(e.gas_energy_today, 1, "kWh") : "–"],
      [this.t("power") + " / " + this.t("modulation"), e.has_gas_source ? `${fmt(e.burner_power, 1, "kW")} / ${fmt(e.burner_modulation, 0, "%")}` : "–"],
      [this.t("observation"), s.settings.observation_mode ? this.t("on") : this.t("off")],
      [this.t("roomControl"), s.settings.room_control_enabled ? this.t("on") : this.t("off")],
    ].map(([k, v]) => `<div class="fact"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("");

    const showUsage = s.rooms.some((r) => r.usage_entities > 0);
    const usageCell = (r) => {
      if (!showUsage) return "";
      if (!r.usage_entities || r.usage_enabled === false || r.in_use === null || r.in_use === undefined) return "<td>–</td>";
      return `<td>${r.in_use ? this.t("used") : this.t("unused")}</td>`;
    };
    const rows = s.rooms.map((r) => `
      <tr class="${r.status}">
        <td>${esc(r.name)}</td>
        <td>${fmt(r.temperature, 1)}</td>
        <td>${fmt(r.target, 1)}</td>
        <td>${r.setpoint ? esc(SOURCE_TEXT[lang][r.setpoint.source] || r.setpoint.source) : "–"}</td>
        <td>${r.valve === null ? "–" : fmt(r.valve * 100, 0, "%")}</td>
        <td>${fmt(r.deficit, 1, "K")}</td>
        <td><div class="mini"><div style="width:${Math.min(100, (r.demand ?? 0) * 100)}%"></div></div>${r.demand === null ? "–" : fmt(r.demand * 100, 0, "%")}</td>
        <td>${fmt(r.weight, 1)}</td>
        ${usageCell(r)}
        <td>${esc(ROOM_STATUS_TEXT[lang][r.status] || r.status || "–")}</td>
      </tr>`).join("");

    return `
      <div class="grid2">
        <div class="card">
          <div class="card-head"><h2>${this.t("boiler")}</h2><button data-action="refresh">${this.t("refresh")}</button></div>
          ${machine}
          <div class="reason">${this.t("reason")}: <b>${esc(REASON_TEXT[lang][d.reason] || d.reason)}</b> · ${this.t("requestHeat")}: <b>${d.request_heat ? this.t("yes") : this.t("no")}</b></div>
          ${gauge}
        </div>
        <div class="card">
          <h2>${this.t("timers")}</h2>
          ${timers}
          <div class="facts">${facts}</div>
        </div>
      </div>
      <div class="card">
        <h2>${this.t("rooms")}</h2>
        <div class="scroll"><table>
          <thead><tr><th>${this.t("room")}</th><th>${this.t("temp")}</th><th>${this.t("target")}</th><th>${this.t("source")}</th><th>${this.t("valve")}</th><th>${this.t("deficit")}</th><th>${this.t("demand")}</th><th>${this.t("weight")}</th>${showUsage ? `<th>${this.t("inUse")}</th>` : ""}<th>${this.t("status")}</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      </div>
      ${this._renderHistory()}`;
  }

  _renderStateMachine(active) {
    const states = [
      ["off", 20, 20], ["heating", 250, 20], ["summer", 20, 90], ["frost_protection", 250, 90],
      ["manual", 480, 20], ["failsafe", 480, 90], ["disabled", 480, 160], ["starting", 20, 160],
    ];
    const lang = this.lang;
    const boxes = states.map(([key, x, y]) =>
      `<g class="state ${key === active ? "active" : ""}"><rect x="${x}" y="${y}" width="200" height="48" rx="10"/><text x="${x + 100}" y="${y + 29}" text-anchor="middle">${esc(STATE_TEXT[lang][key])}</text></g>`).join("");
    return `<svg class="machine" viewBox="0 0 700 220">
      <defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="arrow"/></marker></defs>
      <path d="M220,36 H250" class="edge" marker-end="url(#arr)"/>
      <path d="M250,52 H220" class="edge" marker-end="url(#arr)"/>
      ${boxes}
    </svg>`;
  }

  _renderHistory() {
    const h = this._history;
    const range = `<div class="range"><button class="${this._historyRange === 24 ? "active" : ""}" data-action="range" data-hours="24">${this.t("h24")}</button><button class="${this._historyRange === 168 ? "active" : ""}" data-action="range" data-hours="168">${this.t("d7")}</button></div>`;
    if (!h) return `<div class="card"><div class="card-head"><h2>${this.t("history")}</h2>${range}</div>${this.t("loading")}</div>`;
    if (h.error) return `<div class="card"><div class="card-head"><h2>${this.t("history")}</h2>${range}</div>${esc(h.error)}</div>`;
    const num = (rows) => rows.map(([t, v]) => [t, v === "unavailable" || v === "unknown" ? null : Number(v)]);
    const bool = (rows) => rows.map(([t, v]) => [t, v === "on" ? 1 : v === "off" ? 0 : null]);
    const p = this._state.params;
    const charts = [];
    if (h.data.total_demand?.length) {
      charts.push(timeChart({
        series: [{ name: this.t("totalDemand"), points: num(h.data.total_demand), area: true, step: true }],
        thresholds: [
          { value: p.start_threshold, label: this.t("startThreshold"), color: "#e53935" },
          { value: p.stop_threshold, label: this.t("stopThreshold"), color: "#43a047" },
        ],
        yMin: 0, yMax: 100, yUnit: "%", lang: this.lang,
      }));
    }
    const binary = [];
    if (h.data.heat_request?.length) binary.push({ name: this.t("requestHeat"), points: bool(h.data.heat_request), step: true, color: "#ff5722" });
    if (h.data.burner_active?.length) binary.push({ name: this.t("burner"), points: bool(h.data.burner_active).map(([t, v]) => [t, v === null ? null : v * 0.8]), step: true, color: "#1e88e5" });
    if (binary.length) charts.push(timeChart({ series: binary, height: 90, yMin: 0, yMax: 1.1, lang: this.lang }));
    const temps = [];
    if (h.data.outdoor_temperature?.length) temps.push({ name: this.t("outdoor"), points: num(h.data.outdoor_temperature) });
    if (h.data.outdoor_temperature_smoothed?.length) temps.push({ name: `${this.t("outdoor")} (${this.t("smoothed")})`, points: num(h.data.outdoor_temperature_smoothed) });
    if (temps.length) charts.push(timeChart({ series: temps, thresholds: [{ value: p.heating_limit, label: PARAM_TEXT[this.lang].heating_limit[0], color: "#fb8c00" }], yUnit: "°C", lang: this.lang }));
    const boiler = [];
    if (h.data.flow_temperature?.length) boiler.push({ name: this.t("flow"), points: num(h.data.flow_temperature), color: "#e53935" });
    if (h.data.return_temperature?.length) boiler.push({ name: this.t("return"), points: num(h.data.return_temperature), color: "#1e88e5" });
    if (boiler.length) charts.push(timeChart({ series: boiler, yUnit: "°C", lang: this.lang }));
    const rooms = this._state.rooms.filter((r) => h.data[`room_${r.room_id}`]?.length)
      .map((r, i) => ({ name: r.name, points: num(h.data[`room_${r.room_id}`]), color: COLORS[i % COLORS.length] }));
    if (rooms.length) charts.push(timeChart({ series: rooms, yUnit: "°C", lang: this.lang }));
    const markers = (this._state.changelog_times || []).filter((t) => new Date(t).getTime() >= h.start);
    const note = markers.length ? `<div class="hint">${markers.length} × ${this.t("log")}</div>` : "";
    return `<div class="card"><div class="card-head"><h2>${this.t("history")}</h2>${range}</div>${charts.join("") || this.t("noHistory")}${note}</div>`;
  }

  _renderParams() {
    const data = this._params;
    if (!data) return `<div class="card">${this.t("loading")}</div>`;
    const lang = this.lang;
    const editable = data.can_edit;
    const changes = Object.keys(this._draft).length;
    const groups = data.groups.map((group) => {
      const items = data.params.filter((p) => p.group === group).map((meta) => {
        const [label, description, effect] = PARAM_TEXT[lang][meta.key] || [meta.key, "", null];
        const value = meta.key in this._draft ? this._draft[meta.key] : meta.value;
        const changed = meta.key in this._draft;
        const input = meta.boolean
          ? `<label class="switch"><input type="checkbox" data-param="${meta.key}" ${value ? "checked" : ""} ${editable ? "" : "disabled"}><span></span></label>`
          : `<input type="number" data-param="${meta.key}" value="${esc(value)}" min="${meta.min}" max="${meta.max}" step="${meta.step === "any" ? "any" : meta.step}" ${editable ? "" : "disabled"}><span class="unit">${esc(meta.unit || "")}</span>`;
        const def = meta.boolean ? (meta.default ? this.t("on") : this.t("off")) : `${meta.default}${meta.unit ? " " + meta.unit : ""}`;
        const range = meta.boolean ? "" : ` · ${meta.min}–${meta.max}`;
        return `<div class="param ${changed ? "changed" : ""}">
          <div class="param-main">
            <div class="param-label">${esc(label)}</div>
            <div class="param-desc">${esc(description)}</div>
            ${effect ? `<div class="param-effect">${this.t("higher")}: ${esc(effect)}</div>` : ""}
            <div class="param-meta">${this.t("default")}: ${esc(def)}${esc(range)}</div>
          </div>
          <div class="param-input">${input}${editable && value !== meta.default ? `<button class="link" data-action="reset-param" data-key="${meta.key}">${this.t("resetDefault")}</button>` : ""}</div>
        </div>`;
      }).join("");
      return `<div class="card"><h2>${esc(this.t(`groups.${group}`))}</h2>${items}</div>`;
    }).join("");
    const bar = `<div class="savebar">
      ${editable ? "" : `<span class="hint">${this.t("readOnly")}</span>`}
      <span>${changes} ${this.t("changed")}</span>
      <button data-action="simulate-draft" ${changes ? "" : "disabled"}>${this.t("simulateDraft")}</button>
      ${editable ? `<button data-action="reset-all">${this.t("resetAll")}</button>
      <button data-action="discard" ${changes ? "" : "disabled"}>${this.t("discard")}</button>
      <button class="primary" data-action="save" ${changes && !this._busy ? "" : "disabled"}>${this.t("save")}</button>` : ""}
    </div>`;
    return `${bar}${this._renderIllustration()}${groups}`;
  }

  _renderIllustration() {
    const p = this._params.params.reduce((acc, m) => ({ ...acc, [m.key]: m.key in this._draft ? this._draft[m.key] : m.value }), {});
    const w = 900, h = 170, x0 = 40, x1 = w - 20, y = (v) => 20 + (1 - v / 100) * 110;
    const curve = [5, 12, 30, 48, 55, 40, 22, 12, 8, 6, 15, 35];
    const step = (x1 - x0) / (curve.length - 1);
    const path = curve.map((v, i) => `${i ? "L" : "M"}${x0 + i * step},${y(v)}`).join("");
    return `<div class="card"><h2>${esc(this.t("groups.start_stop"))} · ${esc(this.t("groups.cycle_protection"))}</h2>
      <svg class="illu" viewBox="0 0 ${w} ${h}">
        <path d="${path}" class="illu-curve"/>
        <line x1="${x0}" x2="${x1}" y1="${y(p.start_threshold)}" y2="${y(p.start_threshold)}" class="illu-start"/>
        <text x="${x1}" y="${y(p.start_threshold) - 5}" text-anchor="end" class="axis">${esc(this.t("startThreshold"))} ${p.start_threshold} %</text>
        <line x1="${x0}" x2="${x1}" y1="${y(p.stop_threshold)}" y2="${y(p.stop_threshold)}" class="illu-stop"/>
        <text x="${x1}" y="${y(p.stop_threshold) + 14}" text-anchor="end" class="axis">${esc(this.t("stopThreshold"))} ${p.stop_threshold} %</text>
        <rect x="${x0 + step * 2}" y="140" width="${Math.min(p.start_confirm / 10, 1) * step}" height="10" class="illu-confirm"/>
        <rect x="${x0 + step * 2.6}" y="152" width="${Math.min(p.min_run / 20, 3) * step}" height="10" class="illu-run"/>
        <rect x="${x0 + step * 6}" y="152" width="${Math.min(p.min_pause / 20, 3) * step}" height="10" class="illu-pause"/>
        <text x="${x0}" y="148" class="axis">${esc(this.t("confirm"))}</text>
        <text x="${x0}" y="162" class="axis">${esc(this.t("minRun"))} / ${esc(this.t("minPause"))}</text>
      </svg></div>`;
  }

  _renderLearning() {
    const data = this._learning;
    if (!data) return `<div class="card">${this.t("loading")}</div>`;
    const lang = this.lang;
    const statRow = (label, stat, unit, digits) =>
      `<tr><td>${esc(label)}</td><td>${stat.count}</td><td>${stat.mean === null ? "–" : fmt(stat.mean, digits, unit)}</td><td>${stat.std === null ? "–" : fmt(stat.std, digits)}</td><td>${stat.usable ? "✓" : "–"}</td></tr>`;
    const rooms = data.rooms.map((room) => {
      const bands = Object.entries(room.heat_rate).map(([band, stat]) => statRow(this.t(`bands.${band}`), stat, "K/h", 2)).join("");
      const history = room.history.length
        ? timeChart({
            series: [{ name: this.t("heatRate"), points: room.history.map((d) => [new Date(d.day).getTime(), d.heat_rate]) }],
            height: 120, yUnit: "K/h", lang,
          })
        : "";
      return `<div class="card">
        <div class="card-head"><h2>${esc(room.name)}</h2>${data.can_edit ? `<button data-action="reset-learning" data-room="${esc(room.room_id)}">${this.t("resetRoom")}</button>` : ""}</div>
        <table><thead><tr><th>${this.t("band")}</th><th>${this.t("samples")}</th><th>${this.t("heatRate")}</th><th>${this.t("std")}</th><th></th></tr></thead><tbody>${bands}</tbody></table>
        <p class="hint">${this.t("usedFor")}: ${this.t("usedHeat")}</p>
        <table><tbody>
          ${statRow(this.t("coolingTau"), room.cooling_tau, "h", 1)}
          ${statRow(this.t("deadTime"), room.dead_time, "min", 0)}
        </tbody></table>
        <p class="hint">${this.t("usedCool")} ${this.t("usedDead")}</p>
        <div class="grid2">
          ${scatterChart({ points: room.heat_points, xLabel: `${this.t("outdoor")} °C`, yLabel: `${this.t("heatPoints")} (K/h)` }) || `<div class="hint">${this.t("heatPoints")}: ${this.t("notEnough")}</div>`}
          ${scatterChart({ points: room.cool_points, xLabel: "ΔT K", yLabel: `${this.t("coolPoints")} (h)` }) || `<div class="hint">${this.t("coolPoints")}: ${this.t("notEnough")}</div>`}
        </div>
        ${history ? `<h3>${this.t("learnHistory")}</h3>${history}` : ""}
      </div>`;
    }).join("");
    const b = data.boiler;
    const labels = [...b.buckets.map((v, i) => `<${v}`), `≥${b.buckets[b.buckets.length - 1]}`].map((l) => `${l}`);
    const bandRows = (stats, unit) => Object.entries(stats).map(([band, stat]) => statRow(this.t(`bands.${band}`), stat, unit, 0)).join("");
    const c = data.heating_curve;
    const curve = c.slope !== null ? `<p>${this.t("slope")}: <b>${fmt(c.slope, 2)}</b> · ${this.t("flowAt0")}: <b>${fmt(c.flow_at_0, 1, "°C")}</b></p>` : `<p class="hint">${this.t("notEnough")}</p>`;
    return `
      <div class="card"><div class="card-head"><p>${this.t("learningIntro")}</p>${data.can_edit ? `<button data-action="reset-learning">${this.t("resetLearning")}</button>` : ""}</div></div>
      ${rooms}
      <div class="card"><h2>${this.t("boilerCycles")}</h2>
        <div class="grid2">
          ${barChart({ values: b.run_histogram, labels, title: `${this.t("runs")} (${this.t("minutes")})` })}
          ${barChart({ values: b.pause_histogram, labels, title: `${this.t("pauses")} (${this.t("minutes")})` })}
        </div>
        <div class="grid2">
          <table><thead><tr><th>${this.t("runs")}</th><th>${this.t("samples")}</th><th>${this.t("mean")}</th><th>${this.t("std")}</th><th></th></tr></thead><tbody>${bandRows(b.runs, "min")}</tbody></table>
          <table><thead><tr><th>${this.t("pauses")}</th><th>${this.t("samples")}</th><th>${this.t("mean")}</th><th>${this.t("std")}</th><th></th></tr></thead><tbody>${bandRows(b.pauses, "min")}</tbody></table>
        </div>
      </div>
      <div class="card"><h2>${this.t("heatingCurve")}</h2>${curve}
        ${scatterChart({ points: c.points, xLabel: `${this.t("outdoor")} °C`, yLabel: `${this.t("flow")} °C`, line: c.slope !== null ? [c.slope, c.flow_at_0] : null })}
      </div>`;
  }

  _renderSchedule() {
    const data = this._learning;
    if (!data) return `<div class="card">${this.t("loading")}</div>`;
    const p = data.presence;
    const state = this._state && this._state.learned_schedule;
    const days = this.t("weekdays");
    const hhmm = (minutes) => `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
    const windows = p.windows.map((day, i) => {
      const text = day.length
        ? day.map((w) => `${hhmm(w.start)}–${hhmm(w.end === 1440 ? 1439 : w.end)}`).join(", ")
        : `<span class="hint">${this.t("noWindows")}</span>`;
      return `<tr><td>${esc(days[i])}</td><td>${text}</td></tr>`;
    }).join("");
    const status = [
      [this.t("daysObserved"), `${p.days_observed} / ${p.min_days}`],
      [this.t("status"), p.ready ? this.t("scheduleReady") : this.t("scheduleNotReady")],
      [this.t("learnedScheduleState"), state ? (state.enabled ? this.t("on") : this.t("off")) : "–"],
      [this.t("learnedScheduleNow"), state && state.comfort_now !== null && state.comfort_now !== undefined
        ? (state.comfort_now ? this.t("comfortNow") : this.t("ecoNow")) : "–"],
    ].map(([k, v]) => `<div class="fact"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("");
    return `
      <div class="card">
        <div class="card-head"><h2>${this.t("scheduleTitle")}</h2></div>
        <p>${this.t("scheduleIntro")}</p>
        <div class="facts">${status}</div>
      </div>
      <div class="card">
        <h2>${this.t("presenceHeat")}</h2>
        ${presenceChart({ grid: p.grid, slotMinutes: p.slot_minutes, days: this.t("weekdays") })}
      </div>
      <div class="card">
        <h2>${this.t("suggestion")}</h2>
        <table><tbody>${windows}</tbody></table>
      </div>`;
  }

  _renderSimulate() {
    const lang = this.lang;
    const draftKeys = Object.keys(this._draft);
    const draftList = draftKeys.length
      ? `<ul>${draftKeys.map((k) => `<li>${esc((PARAM_TEXT[lang][k] || [k])[0])}: <b>${esc(this._draft[k])}</b></li>`).join("")}</ul>`
      : `<p class="hint">${this.t("noDraft")}</p>`;
    const hours = [24, 48, 168].map((hh) => `<button class="${this._simHours === hh ? "active" : ""}" data-action="sim-hours" data-hours="${hh}">${hh} h</button>`).join("");
    let result = "";
    const sim = this._simulation;
    if (this._busy) result = `<div class="card">${this.t("running")}</div>`;
    else if (sim) {
      const row = (label, a, b) => `<tr><td>${esc(label)}</td><td>${esc(a ?? "–")}</td><td>${esc(b ?? "–")}</td></tr>`;
      const toPoints = (series, key, scale = 1) => series.map((s) => [new Date(s.t).getTime(), s[key] === null ? null : s[key] * scale]);
      result = `<div class="card">
        <table><thead><tr><th></th><th>${this.t("current")}</th><th>${this.t("draft")}</th></tr></thead><tbody>
          ${row(this.t("starts"), sim.current.starts, sim.draft.starts)}
          ${row(this.t("runtime"), sim.current.runtime_minutes, sim.draft.runtime_minutes)}
          ${row(this.t("deficitShare"), fmt(sim.current.deficit_share, 1, "%"), fmt(sim.draft.deficit_share, 1, "%"))}
          ${row(`${this.t("realBurner")} – ${this.t("starts")}`, sim.current.real_burner_starts, "")}
          ${row(`${this.t("realBurner")} – ${this.t("runtime")}`, sim.current.real_burner_runtime_minutes, "")}
        </tbody></table>
        <h3>${this.t("simChart")}</h3>
        ${timeChart({ series: [{ name: `${this.t("totalDemand")}`, points: toPoints(sim.current.series, "demand"), area: true, step: true, color: "#9e9e9e" }], yMin: 0, yMax: 100, yUnit: "%", lang })}
        ${timeChart({
          series: [
            { name: `${this.t("requestHeat")} – ${this.t("current")}`, points: toPoints(sim.current.series, "request"), step: true, color: "#ff5722" },
            { name: `${this.t("requestHeat")} – ${this.t("draft")}`, points: toPoints(sim.draft.series, "request", 0.8), step: true, color: "#8e24aa" },
            { name: this.t("realBurner"), points: toPoints(sim.current.series, "burner", 0.6), step: true, color: "#1e88e5" },
          ],
          height: 110, yMin: 0, yMax: 1.1, lang,
        })}
      </div>`;
    }
    return `<div class="card"><p>${this.t("simIntro")}</p>
      <h3>${this.t("draft")}</h3>${draftList}
      <div class="range">${this.t("hours")}: ${hours}</div>
      <button class="primary" data-action="run-sim" ${this._busy ? "disabled" : ""}>${this.t("run")}</button></div>${result}`;
  }

  _renderLog() {
    const entries = this._changelog;
    if (!entries) return `<div class="card">${this.t("loading")}</div>`;
    if (!entries.length) return `<div class="card">${this.t("emptyLog")}</div>`;
    const lang = this.lang;
    const rows = entries.map((e) => `<tr><td>${esc(new Date(e.time).toLocaleString(lang))}</td><td>${esc(e.user ?? "–")}</td><td>${esc((PARAM_TEXT[lang][e.key] || [e.key])[0])}</td><td>${esc(e.old)}</td><td>${esc(e.new)}</td></tr>`).join("");
    return `<div class="card"><h2>${this.t("log")}</h2><div class="scroll"><table><thead><tr><th>${this.t("time")}</th><th>${this.t("user")}</th><th>${this.t("parameter")}</th><th>${this.t("oldValue")}</th><th>${this.t("newValue")}</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
  }
}

const STYLE = `
  :host { display:block; background: var(--primary-background-color, #fafafa); color: var(--primary-text-color, #212121); min-height: 100vh; font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
  .header { display:flex; align-items:center; flex-wrap:wrap; gap:8px; padding: 4px 12px; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); position: sticky; top:0; z-index:2; }
  .title { font-size: 20px; margin-right: 16px; }
  .tabs { display:flex; flex-wrap:wrap; gap:4px; }
  .tab { background: transparent; border: none; color: inherit; padding: 12px 10px; cursor: pointer; font-size: 14px; opacity: .8; border-bottom: 2px solid transparent; }
  .tab.active { opacity: 1; border-bottom-color: currentColor; }
  .content { padding: 16px; max-width: 1400px; margin: 0 auto; box-sizing: border-box; }
  .card { background: var(--card-background-color, #fff); border-radius: var(--ha-card-border-radius, 12px); box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,.15)); border: 1px solid var(--divider-color, transparent); padding: 16px; margin-bottom: 16px; }
  .card.error { border-color: var(--error-color, #db4437); color: var(--error-color, #db4437); }
  .card.ok { border-color: var(--success-color, #43a047); }
  .card-head { display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; }
  h2 { font-size: 18px; margin: 0 0 12px; font-weight: 500; }
  h3 { font-size: 15px; margin: 16px 0 8px; font-weight: 500; }
  button { background: var(--secondary-background-color, #eee); color: var(--primary-text-color); border: 1px solid var(--divider-color, #ccc); border-radius: 8px; padding: 6px 12px; cursor: pointer; font: inherit; }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  button:disabled { opacity: .5; cursor: default; }
  button.link { background:none; border:none; color: var(--primary-color); padding: 4px; }
  button.active { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .grid2 { display:grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; }
  .grid2 > .card { margin-bottom: 0; }
  .machine { width:100%; max-height: 220px; }
  .machine .state rect { fill: var(--secondary-background-color, #eee); stroke: var(--divider-color, #bbb); }
  .machine .state text { fill: var(--primary-text-color); font-size: 15px; }
  .machine .state.active rect { fill: var(--primary-color); stroke: var(--primary-color); }
  .machine .state.active text { fill: var(--text-primary-color, #fff); font-weight: 600; }
  .machine .edge { stroke: var(--secondary-text-color); stroke-width: 2; fill:none; }
  .machine .arrow { fill: var(--secondary-text-color); }
  .reason { margin: 8px 0 16px; }
  .gauge { position:relative; height: 22px; background: var(--secondary-background-color, #eee); border-radius: 11px; overflow: visible; }
  .gauge-fill { height:100%; background: var(--primary-color); border-radius: 11px; }
  .gauge-mark { position:absolute; top:-4px; width:3px; height:30px; }
  .gauge-mark.start { background: #e53935; } .gauge-mark.stop { background: #43a047; }
  .gauge-legend { display:flex; flex-wrap:wrap; gap: 12px; margin-top: 8px; font-size: 13px; }
  .gauge-legend .start { color:#e53935; } .gauge-legend .stop { color:#43a047; }
  .timer { display:grid; grid-template-columns: 160px 1fr 120px; align-items:center; gap: 8px; margin-bottom: 8px; font-size: 13px; opacity: .6; }
  .timer.active { opacity: 1; font-weight: 500; }
  .bar-bg { background: var(--secondary-background-color, #eee); height: 10px; border-radius: 5px; overflow:hidden; }
  .bar-fg { background: var(--primary-color); height: 100%; }
  .bar-fg.warn { background: #fb8c00; }
  .facts { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 6px 16px; margin-top: 16px; }
  .fact { display:flex; justify-content:space-between; gap: 8px; border-bottom: 1px solid var(--divider-color, #eee); padding: 4px 0; font-size: 13px; }
  .scroll { overflow-x:auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align:left; padding: 6px 8px; border-bottom: 1px solid var(--divider-color, #eee); white-space: nowrap; }
  th { color: var(--secondary-text-color); font-weight: 500; }
  tr.stale td, tr.degraded td { color: var(--warning-color, #fb8c00); }
  tr.window_open td { color: var(--info-color, #039be5); }
  .mini { display:inline-block; width: 60px; height: 8px; background: var(--secondary-background-color, #eee); border-radius: 4px; margin-right: 6px; vertical-align: middle; overflow:hidden; }
  .mini div { height:100%; background: var(--primary-color); }
  .chart { margin: 8px 0 16px; }
  .chart svg { width: 100%; height: auto; display:block; }
  .chart.small svg { max-height: 240px; }
  .chart-title { font-size: 13px; color: var(--secondary-text-color); margin-bottom: 4px; }
  .grid { stroke: var(--divider-color, #ddd); stroke-width: 1; }
  .axis { fill: var(--secondary-text-color, #777); font-size: 11px; }
  .dot { fill: var(--primary-color); opacity: .7; }
  .fit { stroke: #e53935; stroke-width: 2; }
  .bar { fill: var(--primary-color); opacity: .8; }
  .legends { display:flex; flex-wrap:wrap; gap: 12px; font-size: 12px; margin-top: 4px; }
  .legend i { display:inline-block; width: 12px; height: 3px; margin-right: 4px; vertical-align: middle; }
  .legend.unit { color: var(--secondary-text-color); }
  .range { display:flex; gap: 6px; align-items:center; margin: 8px 0; flex-wrap:wrap; }
  .hint { color: var(--secondary-text-color); font-size: 13px; }
  .savebar { position: sticky; top: 56px; z-index: 1; display:flex; flex-wrap:wrap; align-items:center; gap: 8px; justify-content:flex-end; background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #ddd); border-radius: 12px; padding: 8px 12px; margin-bottom: 16px; }
  .param { display:flex; justify-content:space-between; gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--divider-color, #eee); flex-wrap: wrap; }
  .param:last-child { border-bottom: none; }
  .param.changed { background: linear-gradient(90deg, rgba(3,169,244,.08), transparent); }
  .param-main { flex: 1 1 380px; }
  .param-label { font-weight: 500; }
  .param-desc { font-size: 13px; margin-top: 2px; }
  .param-effect { font-size: 13px; margin-top: 2px; color: var(--secondary-text-color); }
  .param-meta { font-size: 12px; margin-top: 4px; color: var(--secondary-text-color); }
  .param-input { display:flex; align-items:center; gap: 6px; min-width: 250px; justify-content: flex-start; }
  .param-input input[type=number] { width: 100px; padding: 6px; border-radius: 6px; border: 1px solid var(--divider-color, #ccc); background: var(--card-background-color); color: var(--primary-text-color); font: inherit; }
  .unit { color: var(--secondary-text-color); font-size: 13px; min-width: 40px; }
  .switch { position: relative; display:inline-block; width: 40px; height: 22px; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .switch span { position:absolute; inset:0; background: var(--divider-color, #ccc); border-radius: 11px; transition: .2s; }
  .switch span:before { content:""; position:absolute; width: 16px; height: 16px; left: 3px; top: 3px; background: #fff; border-radius: 50%; transition: .2s; }
  .switch input:checked + span { background: var(--primary-color); }
  .switch input:checked + span:before { transform: translateX(18px); }
  .illu { width: 100%; height: auto; }
  .illu-curve { fill:none; stroke: var(--primary-color); stroke-width: 3; }
  .illu-start { stroke:#e53935; stroke-dasharray: 6 4; } .illu-stop { stroke:#43a047; stroke-dasharray: 6 4; }
  .illu-confirm { fill:#fb8c00; } .illu-run { fill: var(--primary-color); } .illu-pause { fill:#9e9e9e; }
  @media (max-width: 600px) { .timer { grid-template-columns: 1fr; } .content { padding: 8px; } }
`;

customElements.define("heat-conductor-panel", HeatConductorPanel);
