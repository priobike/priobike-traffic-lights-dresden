import json
import os
import time

import paho.mqtt.client as mqtt

from log import log

CTRLMESSAGES_MQTT_HOST = os.getenv('FROST_MQTT_HOST')
CTRLMESSAGES_MQTT_PORT = int(os.getenv('FROST_MQTT_PORT'))
CTRLMESSAGES_MQTT_USER = os.getenv('FROST_MQTT_USER')
CTRLMESSAGES_MQTT_PASS = os.getenv('FROST_MQTT_PASS')
if any(v is None for v in [CTRLMESSAGES_MQTT_HOST, CTRLMESSAGES_MQTT_PORT, CTRLMESSAGES_MQTT_USER, CTRLMESSAGES_MQTT_PASS]):
    log('Missing environment variables')
    exit(1)

FROST_MQTT_HOST = os.getenv('FROST_MQTT_HOST')
FROST_MQTT_PORT = int(os.getenv('FROST_MQTT_PORT'))
FROST_MQTT_USER = os.getenv('FROST_MQTT_USER')
FROST_MQTT_PASS = os.getenv('FROST_MQTT_PASS')
if any(v is None for v in [FROST_MQTT_HOST, FROST_MQTT_PORT, FROST_MQTT_USER, FROST_MQTT_PASS]):
    log('Missing environment variables')
    exit(1)

def run_tls_message_converter(things):
    """
    Run the TLS Message Converter - Bridge from the TLS controller service to the FROST-Server.

    See: https://github.com/priobike/priobike-tls-controller

    The TLS controller sends MQTT messages that are interpreted by the physical test traffic lights for Dresden.
    This script converts these messages into FROST Observations to make them available to our prediction service.
    """

    # Unwrap all the datastream IDs from the things for faster access.
    # We will need these IDs later to publish the Observations.
    primary_signal_ids_by_thing = {}
    cycle_second_ids_by_thing = {}
    for thing in things:
        for datastream in thing['Datastreams']:
            if datastream['properties']['layerName'] == 'primary_signal':
                primary_signal_ids_by_thing[thing['name']] = datastream['@iot.id']
            elif datastream['properties']['layerName'] == 'cycle_second':
                cycle_second_ids_by_thing[thing['name']] = datastream['@iot.id']

    # Initiate the MQTT clients: one for inbound messages and one for outbound messages.
    client_inbound = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if CTRLMESSAGES_MQTT_USER and CTRLMESSAGES_MQTT_PASS:
        client_inbound.username_pw_set(CTRLMESSAGES_MQTT_USER, CTRLMESSAGES_MQTT_PASS)
    client_outbound = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if CTRLMESSAGES_MQTT_USER and CTRLMESSAGES_MQTT_PASS:
        client_outbound.username_pw_set(CTRLMESSAGES_MQTT_USER, CTRLMESSAGES_MQTT_PASS)

    # Define two healthcheck vars to monitor the connection to the MQTT broker.
    message_received = None # Will be set to a timestamp when a message is received.
    message_published = None # Will be set to a timestamp when a message is published.

    def on_publish(*args, **kwargs):
        """
        Callback for when a message is published.
        """
        # Tell the healthcheck that the outbound connection is still up and running.
        nonlocal message_published
        message_published = time.time()

    def on_inbound_message(client, userdata, message):
        """
        Callback for when a message is received from the inbound MQTT client.
        """
        # Tell the healthcheck that the inbound connection is still up and running.
        nonlocal message_received
        message_received = time.time()

        # Decode the message and check whether we obtained a TLS controller message.
        content = message.payload.decode('utf-8')
        topic = message.topic
        if not topic.startswith('simulation/sg/'):
            return
        thing_name = topic.split('/')[-1] # e.g. SG1 or SG2

        # Prepare the Observation payload.
        current_time = time.time()
        result_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(current_time))
        phenomenon_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(current_time))

        log(f'Converting message for {thing_name} to Observation: {content}')
        
        # Traffic light starts a new program cycle: Make a Program Observation.
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
        
        # Traffic light changes its color: Make a Primary Signal Observation.
        current_state = {
            'RED': 1,
            'RED_AMBER': 4,
            'GREEN': 3,
            'AMBER': 2,
        }.get(content) # Convert the TLS controller format to the FROST format.
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
        """
        Callback for when the MQTT client is disconnected.
        """
        log(f'Disconnected with result code {rc}')
        # Exit the script if the connection is lost.
        # Docker will restart the container and try to reconnect.
        exit(1)

    log('Connecting MQTT clients...')
    client_inbound.on_message = on_inbound_message
    client_inbound.on_connect = lambda *args, **kwargs: log('Connected to inbound MQTT broker')
    client_inbound.on_disconnect = on_disconnect
    client_inbound.on_publish = on_publish
    client_inbound.connect(CTRLMESSAGES_MQTT_HOST, CTRLMESSAGES_MQTT_PORT, 60)
    # Only two topics are relevant for the TLS controller.
    client_inbound.subscribe("simulation/sg/SG1")
    client_inbound.subscribe("simulation/sg/SG2")
    client_inbound.loop_start() # Important, otherwise the client won't receive any messages.

    client_outbound.on_connect = lambda *args, **kwargs: log('Connected to outbound MQTT broker')
    client_outbound.on_disconnect = on_disconnect
    client_outbound.on_publish = on_publish
    if FROST_MQTT_USER and FROST_MQTT_PASS:
        client_outbound.username_pw_set(FROST_MQTT_USER, FROST_MQTT_PASS)
    client_outbound.connect(FROST_MQTT_HOST, FROST_MQTT_PORT, 60)
    client_outbound.loop_start() # Important, otherwise the client won't publish any messages.

    # Wait forever, but periodically check the health of the MQTT connections.
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

# Run the TLS Message Converter if this script is called directly.
if __name__ == '__main__':
    from syncer import get_all_things

    log('Fetching things to process...')
    things = get_all_things()
    # Throw away any things that are not the TLS traffic lights.
    things_for_tls_message_converter = [
        t for t in things 
        if t['name'] == 'SG1' or t['name'] == 'SG2'
    ]

    if len(things_for_tls_message_converter) == 0:
        log('No things found')
        exit(1)

    log(f'Found {len(things_for_tls_message_converter)} things')
    run_tls_message_converter(things_for_tls_message_converter)