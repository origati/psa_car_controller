"""Estat intern (en memòria) de connexió/autenticació amb PSA.

Mòdul additiu i de només lectura des de fora: registra quan les peces de la
cadena d'autenticació (oauth principal, token remot, MQTT) han anat bé o
malament, perquè un consumidor extern (p.ex. domotica) pugui saber si les
comandes cap al cotxe funcionaran de veritat, sense haver de llegir logs.
"""
import threading
import time
from typing import Any, Optional

_lock = threading.Lock()

_state: dict[str, Any] = {
    "oauth_ok": None,
    "oauth_last_ok_at": None,
    "oauth_last_error": None,
    "oauth_last_error_at": None,
    "remote_token_ok": None,
    "remote_token_last_ok_at": None,
    "remote_token_last_error": None,
    "remote_token_last_error_at": None,
    "rate_limited_at": None,
    "rate_limited_msg": None,
    "mqtt_connected": None,
    "mqtt_last_connect_at": None,
    "mqtt_last_disconnect_at": None,
    "mqtt_last_result_code": None,
}


def _set(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def mark_oauth_ok() -> None:
    _set(oauth_ok=True, oauth_last_ok_at=time.time())


def mark_oauth_error(message: str) -> None:
    _set(oauth_ok=False, oauth_last_error=message, oauth_last_error_at=time.time())


def mark_remote_token_ok() -> None:
    _set(remote_token_ok=True, remote_token_last_ok_at=time.time())


def mark_remote_token_error(message: str) -> None:
    _set(remote_token_ok=False, remote_token_last_error=message, remote_token_last_error_at=time.time())


def mark_rate_limited(message: str) -> None:
    _set(rate_limited_at=time.time(), rate_limited_msg=message)


def mark_mqtt_connect(result_code: int) -> None:
    _set(mqtt_connected=(result_code == 0), mqtt_last_connect_at=time.time(), mqtt_last_result_code=result_code)


def mark_mqtt_disconnect(result_code: int) -> None:
    _set(mqtt_connected=False, mqtt_last_disconnect_at=time.time(), mqtt_last_result_code=result_code)


# Un cop passats aquests segons des de l'últim rate-limit, ja no el comptam
# com "actiu" (el semàfor intern allibera als 1800s com a màxim).
_RATE_LIMIT_WINDOW_S = 1800


def get_state() -> dict[str, Optional[Any]]:
    with _lock:
        state = dict(_state)
    now = time.time()
    rate_limited_at = state.get("rate_limited_at")
    state["rate_limited_active"] = bool(rate_limited_at and (now - rate_limited_at) < _RATE_LIMIT_WINDOW_S)

    oauth_broken = state["oauth_ok"] is False
    remote_broken = state["remote_token_ok"] is False
    if oauth_broken or remote_broken:
        overall = "error"
    elif state["rate_limited_active"]:
        overall = "rate_limited"
    elif state["oauth_ok"] or state["remote_token_ok"] or state["mqtt_connected"]:
        overall = "ok"
    else:
        overall = "unknown"
    state["overall"] = overall
    return state
