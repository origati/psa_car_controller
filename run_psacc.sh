#!/bin/bash

cd "$(dirname "$0")"

if [ -f ".venv/bin/activate" ]; then
  source ".venv/bin/activate"
fi

# Avisa el daemon de càrrega de domotica a l'instant quan arriba un event MQTT
# del cotxe, en comptes d'esperar el seu proper cicle de polling.
export CHARGER_WEBHOOK_URL="http://127.0.0.1:8080/car/mqtt_event"

python3 -u -m psa_car_controller -r
