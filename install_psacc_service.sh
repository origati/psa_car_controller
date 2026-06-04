#!/bin/bash

set -e

SCRIPT_DIR="$(dirname "$0")"

sudo cp "$SCRIPT_DIR/psa_car_controller.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable psa_car_controller
sudo systemctl restart psa_car_controller

echo "Servei instal·lat i reiniciat."
sudo systemctl status psa_car_controller --no-pager
