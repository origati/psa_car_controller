# CLAUDE.md — psa_car_controller

> Mantén aquest fitxer actualitzat quan facis canvis rellevants al projecte
> (arquitectura, bugs corregits, comportaments no obvis, configuració).

## Vehicle

- **Opel Combo-e EV** (VIN: W0VEMZKU4S8513616)
- Bateria: ~50 kWh brut, ~46.3 kWh net usable (`NET_KWH` a `opel.py`)
- Preacondicionador NO suportat (retorna 400 `authorization.denied.cvs.response.no.matching.service.key`)

## Servei a la Raspberry Pi

- Ruta: `/home/origati/Develop/Domotica/psa_car_controller/`
- Servei systemd: `/etc/systemd/system/psa_car_controller.service`
- Script d'arrencada: `run_psacc.sh` → `python3 -u -m psa_car_controller -r`
  - `-r` = guarda dades a BD
  - **NO** hi ha `-R` (refresc automàtic): es va treure (`8a54eb7 llevar autoupdate`) perquè `domotica` va agafar el control total del refresc de bateria. Sense `-R` ni `-c`, `start_refresh_thread()` no es crida mai i `__refresh_vehicle_info` (i el fix `_seconds_until_aligned`) queden inerts. Qui refresca l'estat del cotxe és `domotica` (`charger_controller.py::_wakeup_then_refresh`, cada hora: wakeup + espera ~40s + lectura sense cache). psacc només serveix cache local (MQTT) + la REST quan li demanen.
- Servidor: escolta només a `127.0.0.1:5000` dins la Pi (no exposat a la xarxa). Per accedir-hi de fora: `ssh -f -N -L 5001:127.0.0.1:5000 origati@100.119.150.78` i obrir `http://127.0.0.1:5001` al navegador local.

## Arquitectura de cache (dos nivells)

1. **Cache local** (`car.status` en memòria) — s'actualitza cridant la PSA REST API o via events MQTT. Servit amb `?from_cache=1`.
2. **Cache PSA** — els servidors de PSA guarden l'últim estat que el cotxe ha enviat. No es refresca fins que el cotxe comunica (ignició, càrrega, wakeup).

El cache local és buit/obsolet després de cada reinici de psacc fins que arriba un event MQTT o es fa una crida REST sense cache.

## MQTT

- **Topics rellevants**:
  - `psa/RemoteServices/events/MPHRTServices/<vin>` — events push del cotxe (càrrega, posició…)
  - `psa/RemoteServices/to/cid/<cid>/#` — respostes a comandes enviades
- **Events de càrrega** (`charging_state`): camp `rate` (W), `cable_detected` (0/1), `soc_batt` (%), `autonomy_zev` (km)
- **De l'MQTT NOMÉS ens fiam de la transició positiva**: `rate > 0` → càrrega en curs, `cable_detected == 1` → endollat. **NO** ens fiem de `rate == 0` ni `cable_detected == 0` com a prova d'aturada/desendollada: mesurat empíricament amb l'Opel Combo-e (EasyWallbox AC, sense OCPP) durant 2h de càrrega real ininterrompuda, `rate` va ser 0 en 26 de 33 mostres i `cable_detected` va ser 0 en **33 de 33** — és a dir, aquest camp mai reflecteix "endollat" durant una càrrega real amb aquest wallbox. Cap debounce raonable ho arregla (poden passar minuts sencers a 0). L'aturada/desendollada real només la confirma el refresc REST periòdic (`_IDLE_REFRESH_INTERVAL`/`_CHARGING_REFRESH_INTERVAL` a domotica `charger_controller.py`). Tampoc ens fiem del nivell de bateria (`soc_batt`): escala BMS diferent de `level` i pot enviar valors brossa al wakeup.

### Wakeup a `__on_mqtt_connect` (`RemoteClient.py`)

Quan psacc es (re)connecta a MQTT, dispara `_wakeup_all_cars` amb un `Timer(2s)`. El wakeup de `__keep_mqtt` (cridat a `start()`) es descartava perquè es publicava abans del CONNACK (paho descarta QoS 0 sense connexió establerta). La solució actual és el timer al callback `on_connect`.

### Timing del wakeup

El cotxe tarda **~25-30 segons** a respondre a un wakeup quan dorm. PSA pot retornar `process_code 901` (vehicle asleep) com a estat intermedi — no és un error final, el cotxe acaba responent.

### Webhook cap al daemon de `domotica`

`_update_car_status_from_mqtt` (`RemoteClient.py`) crida `_notify_charger_webhook()` cada cop que un event MQTT porta `rate` o `cable_detected` — fa un POST fire-and-forget (thread separat, timeout 3s, errors silenciats) a `CHARGER_WEBHOOK_URL` (env var, definida a `run_psacc.sh` com `http://127.0.0.1:8080/car/mqtt_event`). Objectiu: que el daemon de càrrega de `domotica` reaccioni a l'instant a canvis reals del cotxe (engegar/aturar càrrega, connectar/desconnectar cable) en lloc d'esperar el seu propi cicle de polling (fins a 5 min). Si `CHARGER_WEBHOOK_URL` no està definida, no fa res (opt-in). Al costat de `domotica`, l'endpoint `/car/mqtt_event` només crida `wake_daemon()` (`charger/daemon.py`) — no fa cap avaluació ell mateix, deixa que ho faci el propi thread del daemon per evitar curses.

## Reautenticació OAuth (`invalid_grant`)

Si els logs (`journalctl -u psa_car_controller.service`) mostren `oauth2_client.credentials_manager.OAuthError: 400 - invalid_grant : grant is invalid` de forma repetida (cada ~10 min, a `refresh_token_now` a `oauth.py:79`), el `refresh_token` guardat a `config.json` ha quedat invalidat per PSA/Stellantis (caducitat o revocació al seu costat, no és un bug del codi). Cal refer el login manual:

**Causa habitual — sessió única per compte**: Stellantis només permet un `refresh_token`/sessió activa alhora per compte. L'app oficial (MyOpel) s'obre automàticament al fer servir el cotxe (pantalla/infotainment en arrencar), i això revoca la sessió de psacc encara que s'acabi de renovar (vist: renovat i invalidat als 16 min). No hi ha manera d'evitar-ho des del codi de psacc — cal esperar-ho i refer login quan calgui, o evitar obrir/usar l'app oficial mentre psacc necessiti la sessió activa.

1. Obrir `http://<ip-pi>:5001/config` (pestanya "User config"), omplir marca/email/contrasenya i "Submit".
2. Si l'auto-login falla (`HeadlessOAuthError`), apareix un enllaç "Go to login" → `/config_connect?url=<auth_url>`.
3. A `/config_connect`: clic a "1. Click here" → login PSA/AWS Cognito fins "LOGIN SUCCESSFUL".
4. Abans de prémer el botó final "OK", obrir DevTools → Network.
5. Clicar "OK"; a Network buscar la petició `mystellantis://oauth2redirect/...` i copiar el paràmetre `code=` (36 caràcters).
6. Enganxar el codi al camp "Code" de `/config_connect` i "Submit" → crida `finish_oauth` → `connect_with_code` → desa el nou `refresh_token`/`remote_refresh_token` a `config.json`.

Rutes implicades: `web/view/views.py`, `web/view/config_views.py`, `web/view/config_oauth.py`, `psa/setup/app_decoder.py` (`InitialSetup.connect`), `psa/oauth.py`.

## Bugs corregits

### KeyError `precond_state` (`RemoteClient.py` ~línia 107)
Events MQTT sense `precond_state` causaven excepció. Fix: `data.get("precond_state")` defensiu.

### Bucle infinit de wakeups per sentinel `0xFFE` (`RemoteClient.py`)
PSA usa `remaining_time=4094` (0xFFE) com a sentinel "valor desconegut". El codi el tractava com a temps real → disparava wakeup → nou event MQTT → bucle infinit cada 60s fins desconnexió.
Fix original: `REMAINING_TIME_UNKNOWN = 0xFFE` exclòs a la condició de `_fix_not_updated_api`. (NOTA: `_fix_not_updated_api` i tota la lògica de wakeup-des-de-MQTT es va perdre en un merge amb upstream; `RemoteClient.py` actual ja no dispara wakeups per events, així que el bucle no pot tornar per aquesta via.)

### Lectura REST fallida esborrava el cache (`psacc/application/psa_client.py::get_vehicle_info`)
Amb `car.status = res` al final del bucle, un `res is None` (503 típic de PSA quan el cotxe dorm) deixava `car.status = None`. Conseqüències mentre estava a `None`: `/get_vehicleinfo?from_cache=1` → `None.to_dict()` → HTTP 500, i els events MQTT deixaven d'actualitzar res (`_update_car_status_from_mqtt` surt d'hora si `car.status is None`) fins a la propera lectura OK. Fix: `if res is not None: car.status = res` (mantenir el darrer estat bo). A `web/view/api.py`, `/get_vehicleinfo` també cau a `car.status` i torna un `502` JSON en lloc d'un stacktrace quan no hi ha res.

### Falses aturades per `rate`/`cable_detected` sorollosos (`RemoteClient.py::_update_car_status_from_mqtt`)
El codi marcava `status = "Stopped"` i `plugged = False` amb una sola mostra MQTT de `rate == 0` / `cable_detected == 0`, assumint que eren senyals fiables. En producció (Combo-e + EasyWallbox AC) això disparava aturades falses en ple mig d'una càrrega real (domotica detectava "canvi extern: charging True → False" i tornava a enviar `iniciar_carga()`, amb soroll de log i risc de deixar la càrrega pausada fins al proper refresc REST si en aquell moment `should_start` no es complia). Un primer intent amb debounce de 30s no va ser suficient perquè `rate` pot estar minuts sencers a 0 durant càrrega real.
Fix: eliminat l'ús de `rate == 0` / `cable_detected == 0` per baixar l'estat. Ara només pugen l'estat (`rate > 0` → `InProgress`, `cable_detected == 1` → `plugged = True`); la baixada només la confirma el refresc REST periòdic.

## Fitxers clau

| Fitxer | Funció |
|--------|--------|
| `psa_car_controller/psa/RemoteClient.py` | Client MQTT: connexió, wakeup, actualització cache des d'events |
| `psa_car_controller/psacc/__init__.py` | Motor principal, càrrega de config, integració REST+MQTT |
| `psa_car_controller/web/app.py` | Endpoints Flask (`/get_vehicleinfo`, `/wakeup`, `/charge_now`…) |
| `run_psacc.sh` | Script d'arrencada del servei |
