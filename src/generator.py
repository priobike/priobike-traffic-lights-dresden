import json
import math
import os
import random
import time
from datetime import datetime

import paho.mqtt.client as mqtt

from log import log

FROST_MQTT_HOST = os.getenv('FROST_MQTT_HOST')
FROST_MQTT_PORT = int(os.getenv('FROST_MQTT_PORT'))
FROST_MQTT_USER = os.getenv('FROST_MQTT_USER')
FROST_MQTT_PASS = os.getenv('FROST_MQTT_PASS')
if any(v is None for v in [FROST_MQTT_HOST, FROST_MQTT_PORT, FROST_MQTT_USER, FROST_MQTT_PASS]):
    log('Missing environment variables')
    exit(1)

# Define the possible states of a traffic light.
dark = 0
red = 1
amber = 2
green = 3
redamber = 4

def generate_cycles(thing_name):
    """
    Generate a random program (cycles per hour) for a thing.

    For the same thing, this function will always return the same cycle.
    """
    cycles = []
    for hour_of_day in range(24):
        random.seed(hash(thing_name) + hour_of_day)

        # Simulate that traffic lights turn off at night.
        probability_of_dark = [
            1 - min(
                1.0, 
                0.7
                + ((math.sin((math.pi / 4) * (h - 4)) + 1) / 2) * 0.1
                + ((math.sin((math.pi / 12) * (h - 6)) + 1) / 2) * 0.3
            )
            for h in range(24)
        ]
        if random.random() < probability_of_dark[hour_of_day]:
            cycles.append([dark] * 60)
            continue

        states = random.choices([
            [red, green, red],
            [red, redamber, green, amber, red],
            [red, red],
            [green, green],
        ], k=1, weights=[ 
            # Based on analyses of real traffic light programs in Hamburg.
            2930, 
            2405,
            1753,
            622,
        ])[0]

        states_lengths = []
        for state in states:
            if state == red:
                states_lengths.append(random.randint(5, 30))
            elif state == amber:
                states_lengths.append(random.randint(3, 5)) # Constrained by German traffic light law
            elif state == green:
                states_lengths.append(random.randint(10, 30))
            elif state == redamber:
                states_lengths.append(1) # Constrained by German traffic light law
            elif state == dark:
                states_lengths.append(random.randint(5, 10))
            else:
                raise ValueError('Unknown state')

        cycle = []
        for state, state_length in zip(states, states_lengths):
            cycle.extend([state] * state_length)
        cycles.append(cycle)

    # Don't change the program every hour.
    random.seed(hash(thing_name))
    probability_of_program_change = random.random()
    program_ids = list(range(24))
    for i in range(24):
        if random.random() < probability_of_program_change:
            cycles[i] = cycles[i - 1]
            program_ids[i] = program_ids[i - 1]

    return cycles, program_ids

def run_message_generator(things):
    """
    Run the Observation message generator.

    This function will generate and publish Observations for the given things.
    """
    # Define a healthcheck var to monitor the connection to the MQTT broker.
    message_published = None # Will be set to a timestamp when a message is received.
    def on_publish(*args, **kwargs):
        """
        Callback for when a message is published.
        """
        # Tell the healthcheck that the outbound connection is still up and running.
        nonlocal message_published
        message_published = time.time()

    def on_disconnect(client, userdata, rc):
        """
        Callback for when the MQTT client is disconnected.
        """
        log(f'Disconnected with result code {rc}')
        # Exit the script if the connection is lost.
        # Docker will restart the container and try to reconnect.
        exit(1)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_publish = on_publish
    client.on_disconnect = on_disconnect
    client.loop_start()
    if FROST_MQTT_USER and FROST_MQTT_PASS:
        client.username_pw_set(FROST_MQTT_USER, FROST_MQTT_PASS)
    client.connect(FROST_MQTT_HOST, FROST_MQTT_PORT, 60)

    # Generate cycles for all things.
    cycles_by_thing_and_hour = { 
        thing['name']: generate_cycles(thing['name'])
        for thing in things 
    }

    # Unwrap all the datastream IDs from the things for faster access.
    # We will need these IDs later to publish the Observations.
    primary_signal_ids_by_thing = {}
    cycle_second_ids_by_thing = {}
    signal_program_ids_by_thing = {}
    for thing in things:
        for datastream in thing['Datastreams']:
            # properties -> layerName
            if datastream['properties']['layerName'] == 'primary_signal':
                primary_signal_ids_by_thing[thing['name']] = datastream['@iot.id']
            elif datastream['properties']['layerName'] == 'cycle_second':
                cycle_second_ids_by_thing[thing['name']] = datastream['@iot.id']
            elif datastream['properties']['layerName'] == 'signal_program':
                signal_program_ids_by_thing[thing['name']] = datastream['@iot.id']

    start = 0 # Used as a reference point (unix time 0)
    last_primary_signal = {} # The last state of the primary signal for each thing
    last_program = {} # The last program for each thing
    sent_messages = 0 # Counter for the number of messages sent

    # Every second, look at the current time and publish the current state
    log('Starting message generator')
    while True:
        for thing_name, (cycles_by_hour, program_ids_by_hour) in cycles_by_thing_and_hour.items():
            # Get the needed datastreams
            ds_primary_signal = primary_signal_ids_by_thing.get(thing_name)
            ds_cycle_second = cycle_second_ids_by_thing.get(thing_name)
            ds_signal_program = signal_program_ids_by_thing.get(thing_name)
            if ds_primary_signal is None or ds_cycle_second is None or ds_signal_program is None:
                log(f'No datastream for thing {thing_name}')
                continue

            hour = datetime.now().hour

            # Get the current time in the cycle.
            cycle = cycles_by_hour[hour]
            current_time = time.time()
            current_second = int(current_time - start)
            current_state = cycle[current_second % len(cycle)]
            current_time_in_cycle = current_second % len(cycle)
            current_program = program_ids_by_hour[hour]

            # Only publish the primary signal if it has changed.
            should_publish_primary_signal = False
            if thing_name not in last_primary_signal or last_primary_signal[thing_name] != current_state:
                last_primary_signal[thing_name] = current_state
                should_publish_primary_signal = True
            # Only publish the cycle second if it has changed.
            should_publish_cycle_second = current_time_in_cycle == 0
            # Only publish the signal program if it has changed.
            should_publish_signal_program = False
            if thing_name not in last_program or last_program[thing_name] != current_program:
                last_program[thing_name] = current_program
                should_publish_signal_program = True

            # Prepare the Observation payload.
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

            if should_publish_signal_program:
                payload = {
                    'phenomenonTime': phenomenon_time,
                    'result': current_program,
                    'resultTime': result_time,
                    'Datastream': { '@iot.id': ds_signal_program }
                }
                client.publish(f'v1.1/Datastreams({ds_signal_program})/Observations', json.dumps(payload), retain=True, qos=1)
                sent_messages += 1
            
        log(f'Message Generator: sent {sent_messages} Observations so far')

        time.sleep(1)
        # Check the health of the MQTT connections.
        with open('health.txt', 'w') as f:
            if message_published is not None:
                f.write(f'ok')
            else:
                f.write(f'error')
        message_published = None

# Run the message generator if this script is called directly.
if __name__ == '__main__':
    from syncer import get_all_things

    log('Fetching things to process...')
    things = get_all_things()
    things_for_message_generator = [
        t for t in things 
        if t['name'] != 'SG1' and t['name'] != 'SG2'
    ]

    if len(things_for_message_generator) == 0:
        log('No things found')
        exit(1)

    log(f'Found {len(things_for_message_generator)} things')
    run_message_generator(things_for_message_generator)