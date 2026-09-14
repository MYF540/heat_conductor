// HeatConductor relay watchdog for Shelly Gen2+ devices (e.g. Shelly 1 Gen3/Gen4, Shelly Pro 1).
//
// HeatConductor calls   http://<shelly-ip>/script/<script-id>/heartbeat?armed=1   every minute.
//   armed=1  HeatConductor controls the boiler: without heartbeats the relay is switched off.
//   armed=0  observation mode or automation off: the script does not interfere.
//
// Installation: Shelly web UI -> Scripts -> Create script -> paste -> Save -> Start,
// enable "Run on startup". Enter the heartbeat URL in HeatConductor
// (Configure -> Central entities -> Relay watchdog URL).
//
// After a reboot the script starts armed: if Home Assistant does not answer within
// TIMEOUT_SEC, the boiler stays off (fail-safe "boiler off").

let CONFIG = {
  switchId: 0,
  timeoutSec: 600,
  checkIntervalSec: 30,
};

function uptime() {
  return Shelly.getComponentStatus("sys").uptime;
}

let state = {
  armed: true,
  lastBeat: uptime(),
};

HTTPServer.registerEndpoint("heartbeat", function (request, response) {
  let query = request.query || "";
  state.armed = query.indexOf("armed=0") < 0;
  state.lastBeat = uptime();
  response.code = 200;
  response.headers = [["Content-Type", "application/json"]];
  response.body = JSON.stringify({ ok: true, armed: state.armed });
  response.send();
});

Timer.set(CONFIG.checkIntervalSec * 1000, true, function () {
  if (!state.armed) {
    return;
  }
  if (uptime() - state.lastBeat < CONFIG.timeoutSec) {
    return;
  }
  let status = Shelly.getComponentStatus("switch:" + CONFIG.switchId);
  if (status && status.output) {
    print("HeatConductor watchdog: no heartbeat for " + CONFIG.timeoutSec + " s, switching boiler off");
    Shelly.call("Switch.Set", { id: CONFIG.switchId, on: false });
  }
});

print("HeatConductor watchdog started");
