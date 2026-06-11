from unittest.mock import MagicMock, patch

from psa_car_controller.psa.connected_car_api import Vehicles, ApiClient
from psa_car_controller.psa.constants import DISCONNECTED
from psa_car_controller.psacc.model.car import Car
from tests.data.car_status import ELECTRIC_CAR_STATUS

import unittest

from paho.mqtt.client import MQTTMessage

from psa_car_controller.psa.RemoteClient import MQTT_EVENT_TOPIC
from tests.utils import get_rc

message_without_precond = b'{"date":"2022-03-30T12:00:52Z","etat_res_elec":0,"precond_state":{},"charging_state":{"program":{' \
                          b'"hour":22,"minute":30},"available":1,"remaining_time":0,"rate":0,"cable_detected":1,"soc_batt":76,' \
                          b'"autonomy_zev":178,"type":0,"hmi_state":0,"mode":2},"stolen_state":0,"vin":"vin",' \
                          b'"reason":0,"signal_quality":3,"sev_stop_date":"2022-03-30T11:10:25Z","fds":[],"sev_state":0,' \
                          b'"obj_counter":1,"privacy_customer":0,"privacy_applicable":0,"privacy_applicable_max":2,' \
                          b'"superlock_state":0} '
message_without_charge_info = b'{"date":"2022-03-30T13:18:56Z","etat_res_elec":5,"precond_state":{"available":1,' \
    b'"programs":{"program1":{"hour":34,"minute":7,"on":0,"day":[0,0,0,0,0,0,0]},' \
    b'"program2":{"hour":34,"minute":7,"on":0,"day":[0,0,0,0,0,0,0]},"program3":{' \
    b'"hour":34,"minute":7,"on":0,"day":[0,0,0,0,0,0,0]},"program4":{"hour":34,"minute":7,' \
    b'"on":0,"day":[0,0,0,0,0,0,0]}},"asap":0,"status":0,"aff":1},"charging_state":{' \
    b'"program":{"hour":22,"minute":30},"available":1,"rate":0,"cable_detected":1,' \
    b'"soc_batt":61,"type":0,"aff":1,"hmi_state":0,"mode":2},"stolen_state":0,' \
    b'"vin":"VIN","reason":4,"signal_quality":5,' \
    b'"sev_stop_date":"2022-03-30T12:41:10Z","fds":["NDR01","NBM01","NCG01","NAO01",' \
    b'"NAS01"],"sev_state":1,"obj_counter":2,"privacy_customer":0,"privacy_applicable":0,' \
    b'"privacy_applicable_max":2,"superlock_state":0} '


class TestUnit(unittest.TestCase):

    @patch('psa_car_controller.psa.RemoteClient.record_battery_csv')
    def test_update_car_status_from_mqtt(self, _patched_record):
        # GIVEN
        remote_client = get_rc()
        vin = "myvin"
        car = Car("a", "b", "c")
        car.status = ApiClient()._ApiClient__deserialize(ELECTRIC_CAR_STATUS, "Status")
        electric = car.status.get_energy('Electric')
        electric.charging.status = DISCONNECTED
        electric.charging.plugged = False
        remote_client.vehicles_list.get_car_by_vin = MagicMock(return_value=car)
        # WHEN rate > 0 i cable connectat
        remote_client._update_car_status_from_mqtt(
            vin, {'rate': 20, 'cable_detected': 1, 'autonomy_zev': 150})
        # THEN estat, plugged i autonomia actualitzats a l'instant
        self.assertEqual(electric.charging.status, "InProgress")
        self.assertTrue(electric.charging.plugged)
        self.assertEqual(electric.autonomy, 150)
        # WHEN rate = 0 després d'estar carregant
        remote_client._update_car_status_from_mqtt(vin, {'rate': 0, 'cable_detected': 0})
        # THEN detecta el final de la càrrega
        self.assertEqual(electric.charging.status, "Stopped")
        self.assertFalse(electric.charging.plugged)

    def test_message_without_precond(self):
        remote_client = get_rc()
        msg = MQTTMessage(topic=MQTT_EVENT_TOPIC.encode("utf-8"))
        msg.payload = message_without_precond
        remote_client._on_mqtt_message(None, None, msg)
        self.assertEqual(remote_client.precond_programs, {})

    def test_message_without_charge_info(self):
        remote_client = get_rc()
        msg = MQTTMessage(topic=MQTT_EVENT_TOPIC.encode("utf-8"))
        msg.payload = message_without_charge_info
        remote_client._on_mqtt_message(None, None, msg)
