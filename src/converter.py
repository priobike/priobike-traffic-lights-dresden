"""
TLS Message Converter - Bridge from the TLS controller service to the FROST-Server.

See: https://github.com/priobike/priobike-tls-controller

The TLS controller sends MQTT messages that are interpreted by the physical test traffic lights for Dresden.
This script converts these messages into FROST Observations to make them available to our prediction service.
"""

import time

import paho.mqtt.client as mqtt


async def run_tls_message_converter(things):
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

    def on_message(client, userdata, message):
        content = message.payload.decode('utf-8')
        topic = message.topic
        
        if not topic.startswith('simulation/sg/'):
            return
        thing_name = topic.split('/')[-1]

        current_time = time.time()
        result_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(current_time))
        phenomenon_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(current_time))

        print(f'Converting message for {thing_name} to Observation: {content}')
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
            client_outbound.publish(f'v1.1/Datastreams({ds_cycle_second})/Observations', str(payload), retain=True)
            print(f'Published Observation for {thing_name} to topic: v1.1/Datastreams({ds_cycle_second})/Observations')
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
        client_outbound.publish(f'v1.1/Datastreams({ds_primary_signal})/Observations', str(payload), retain=True)
        print(f'Published Observation for {thing_name} to topic: v1.1/Datastreams({ds_primary_signal})/Observations')

    print('Starting TLS message converter')
    client_inbound.on_message = on_message
    client_inbound.connect("priobike.vkw.tu-dresden.de", 20032, 60)
    client_inbound.subscribe("simulation/sg/SG1")
    client_inbound.subscribe("simulation/sg/SG2")
    client_outbound.connect("priobike.vkw.tu-dresden.de", 20056, 60)

    client_inbound.loop_start()

if __name__ == '__main__':
    import asyncio

    from syncer import get_all_things
    things = get_all_things()
    things_for_tls_message_converter = [t for t in things if t['name'] == 'SG1' or t['name'] == 'SG2']
    asyncio.run(run_tls_message_converter(things_for_tls_message_converter))

    # Wait forever
    while True:
        time.sleep(1)