import json
import random
import time

import paho.mqtt.client as mqtt

from log import log

dark = 0
red = 1
amber = 2
green = 3
redamber = 4

def generate_cycle(thing_name):
    """
    Generate a random program (cycle) for a thing.
    """
    random.seed(hash(thing_name))
    states = random.choices([
        [red, green, red],
        [red, redamber, green, amber, red],
    ], k=1, weights=[
        50,
        50,
    ])[0]

    states_lengths = []
    for state in states:
        if state == red:
            states_lengths.append(random.randint(5, 30))
        elif state == amber:
            states_lengths.append(random.randint(3, 5))
        elif state == green:
            states_lengths.append(random.randint(10, 30))
        elif state == redamber:
            states_lengths.append(1)
        elif state == dark:
            states_lengths.append(random.randint(5, 10))
        else:
            raise ValueError('Unknown state')

    cycle = []
    for state, state_length in zip(states, states_lengths):
        cycle.extend([state] * state_length)

    return cycle

def run_message_generator(things):
    # Healthcheck vars
    message_published = None
    def on_publish(*args, **kwargs):
        nonlocal message_published
        message_published = time.time()

    def on_disconnect(client, userdata, rc):
        log(f'Disconnected with result code {rc}')
        exit(1)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_publish = on_publish
    client.on_disconnect = on_disconnect
    client.loop_start()
    client.connect("priobike.vkw.tu-dresden.de", 20056, 60)

    cycles_by_thing = { thing['name']: generate_cycle(hash(thing['name'])) for thing in things }
    primary_signal_ids_by_thing = {}
    cycle_second_ids_by_thing = {}
    for thing in things:
        for datastream in thing['Datastreams']:
            # properties -> layerName
            if datastream['properties']['layerName'] == 'primary_signal':
                primary_signal_ids_by_thing[thing['name']] = datastream['@iot.id']
            elif datastream['properties']['layerName'] == 'cycle_second':
                cycle_second_ids_by_thing[thing['name']] = datastream['@iot.id']

    start = 0
    last_primary_signal = {}
    sent_messages = 0

    # Every second, look at the current time and publish the current state
    log('Starting message generator')
    while True:
        for thing_name, cycle in cycles_by_thing.items():
            ds_primary_signal = primary_signal_ids_by_thing.get(thing_name)
            ds_cycle_second = cycle_second_ids_by_thing.get(thing_name)
            if ds_primary_signal is None or ds_cycle_second is None:
                log(f'No datastream for thing {thing_name}')
                continue

            current_time = time.time()
            current_second = int(current_time - start)
            current_state = cycle[current_second % len(cycle)]
            current_time_in_cycle = current_second % len(cycle)

            should_publish_primary_signal = False
            if thing_name not in last_primary_signal or last_primary_signal[thing_name] != current_state:
                last_primary_signal[thing_name] = current_state
                should_publish_primary_signal = True

            should_publish_cycle_second = current_time_in_cycle == 0

            result_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(current_time))
            phenomenon_time = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(current_time))

            if should_publish_primary_signal:
                payload = {
                    'phenomenonTime': phenomenon_time,
                    'result': current_state,
                    'resultTime': result_time,
                    'Datastream': { '@iot.id': ds_primary_signal }
                }
                client.publish(f'v1.1/Datastreams({ds_primary_signal})/Observations', json.dumps(payload), retain=True, qos=1)
                sent_messages += 1

            if should_publish_cycle_second:
                payload = {
                    'phenomenonTime': phenomenon_time,
                    'result': 0,
                    'resultTime': result_time,
                    'Datastream': { '@iot.id': ds_cycle_second }
                }
                client.publish(f'v1.1/Datastreams({ds_cycle_second})/Observations', json.dumps(payload), retain=True, qos=1)
                sent_messages += 1
            
        log(f'Message Generator: sent {sent_messages} Observations so far')

        time.sleep(1)

        # Healthcheck
        with open('health.txt', 'w') as f:
            if message_published is not None:
                f.write(f'ok')
            else:
                f.write(f'error')
        message_published = None

if __name__ == '__main__':
    from syncer import get_all_things
    log('Fetching things to process...')
    things = get_all_things()
    log(f'Found {len(things)} things')
    if len(things) == 0:
        log('No things found')
        exit(1)
    things_for_message_generator = [
        t for t in things 
        if t['name'] != 'SG1' and t['name'] != 'SG2'
    ]
    run_message_generator(things_for_message_generator)