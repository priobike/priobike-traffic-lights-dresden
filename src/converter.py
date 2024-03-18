"""
TLS Message Converter - Bridge from the TLS controller service to the FROST-Server.

See: https://github.com/priobike/priobike-tls-controller

The TLS controller sends MQTT messages that are interpreted by the physical test traffic lights for Dresden.
This script converts these messages into FROST Observations to make them available to our prediction service.
"""

import json
import time

import paho.mqtt.client as mqtt

from log import log


def run_tls_message_converter(things):
    primary_signal_ids_by_thing = {}
    cycle_second_ids_by_thing = {}
    for thing in things:
        for datastream in thing['Datastreams']:
            if datastream['properties']['layerName'] == 'primary_signal':
                primary_signal_ids_by_thing[thing['name']] = datastream['@iot.id']
            elif datastream['properties']['layerName'] == 'cycle_second':
                cycle_second_ids_by_thing[thing['name']] = datastream['@iot.id']

    client_inbound = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_password = "cmoMyQu3cKgNo8"
    mqtt_username = "backend"
    client_inbound.username_pw_set(mqtt_username, mqtt_password)
    client_outbound = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    # Healthcheck vars
    message_received = None
    message_published = None

    def on_publish(*args, **kwargs):
        nonlocal message_published
        message_published = time.time()

    def on_inbound_message(client, userdata, message):
        nonlocal message_received
        message_received = time.time()

        content = message.payload.decode('utf-8')
        topic = message.topic
        
        if not topic.startswith('simulation/sg/'):
            return
        thing_name = topic.split('/')[-1]

        current_time = time.time()
        result_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(current_time))
        phenomenon_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(current_time))

        log(f'Converting message for {thing_name} to Observation: {content}')
        if content == 'startNewCycle':
            ds_cycle_second = cycle_second_ids_by_thing.get(thing_name)
            if ds_cycle_second is None:
                raise ValueError(f'No cycle for thing {thing_name}')
            payload = payload = {
                'phenomenonTime': phenomenon_time,
                'result': 0,
                'resultTime': result_time,
                'Datastream': { '@iot.id': ds_cycle_second }
            }
            client_outbound.publish(f'v1.1/Datastreams({ds_cycle_second})/Observations', json.dumps(payload), retain=True, qos=1)
            log(f'Published Observation for {thing_name} to topic: v1.1/Datastreams({ds_cycle_second})/Observations')
            return
        
        current_state = {
            'RED': 1,
            'RED_AMBER': 4,
            'GREEN': 3,
            'AMBER': 2,
        }.get(content)
        
        ds_primary_signal = primary_signal_ids_by_thing.get(thing_name)
        if ds_primary_signal is None:
            raise ValueError(f'No primary signal for thing {thing_name}')
        payload = {
            'phenomenonTime': phenomenon_time,
            'result': current_state,
            'resultTime': result_time,
            'Datastream': { '@iot.id': ds_primary_signal }
        }
        client_outbound.publish(f'v1.1/Datastreams({ds_primary_signal})/Observations', json.dumps(payload), retain=True, qos=1)
        log(f'Published Observation for {thing_name} to topic: v1.1/Datastreams({ds_primary_signal})/Observations')

    def on_disconnect(client, userdata, rc):
        log(f'Disconnected with result code {rc}')
        exit(1)

    log('Connecting MQTT clients...')
    client_inbound.on_message = on_inbound_message
    client_inbound.on_disconnect = on_disconnect
    client_inbound.on_publish = on_publish
    client_inbound.connect("priobike.vkw.tu-dresden.de", 20032, 60)
    client_inbound.subscribe("simulation/sg/SG1")
    client_inbound.subscribe("simulation/sg/SG2")
    client_inbound.loop_start()

    client_outbound.on_disconnect = on_disconnect
    client_outbound.on_publish = on_publish
    client_outbound.connect("priobike.vkw.tu-dresden.de", 20056, 60)
    client_outbound.loop_start()

    while True:
        time.sleep(60)
        # Healthcheck
        with open('health.txt', 'w') as f:
            if message_received is not None and message_published is not None:
                f.write(f'ok')
            else:
                f.write(f'error')
        message_received = None
        message_published = None

if __name__ == '__main__':
    from syncer import get_all_things
    log('Fetching things to process...')
    things = get_all_things()
    if len(things) == 0:
        log('No things found')
        exit(1)
    things_for_tls_message_converter = [
        t for t in things 
        if t['name'] == 'SG1' or t['name'] == 'SG2'
    ]
    log(f'Found {len(things_for_tls_message_converter)} things')
    run_tls_message_converter(things_for_tls_message_converter)