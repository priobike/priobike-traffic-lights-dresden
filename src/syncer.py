import json

import requests
import shapely
from tqdm import tqdm

BASE_URL = "http://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/"

def get_all_things():
    # Get all traffic lights
    things = []
    link = f'{BASE_URL}Things?$expand=Locations,Datastreams'
    while True:
        response = requests.get(link)
        things.extend(response.json()['value'])
        if '@iot.nextLink' in response.json():
            link = response.json()['@iot.nextLink']
            continue
        break
    return things

def sync_things():
    # Fetch all things from FROST server and delete them
    print("Deleting all things from the FROST server.")
    while True:
        response = requests.get(f'{BASE_URL}Things')
        if len(response.json()['value']) == 0:
            break
        print(f"Deleting {len(response.json()['value'])} things")
        for thing in tqdm(response.json()['value']):
            requests.delete(f'{BASE_URL}Things({thing["@iot.id"]})')
        assert response.status_code == 201 or response.status_code == 200

    with open('locations.geojson') as f:
        traffic_lights_locations = json.load(f)

    with open('segments.geojson') as f:
        traffic_light_segments = json.load(f)

    traffic_light_geometries = [
        # SG1
        [
            [
                13.728873431682585,
                51.03007550963579
            ],
            [
                13.728240430355072,
                51.030041772135085
            ]
        ],
        # SG2
        [
            [
                13.728149235248566,
                51.03061783658934
            ],
            [
                13.728147894144058,
                51.030635548560134
            ],
            [
                13.727828040719032,
                51.03061488459357
            ]
        ]
    ]

    # Snap each traffic light to the nearest segment
    print("OSM Preprocessing: snapping traffic lights to the nearest segment.")
    for feature in tqdm(traffic_lights_locations['features']):
        point = shapely.geometry.shape(feature['geometry'])
        nearest_line = None
        nearest_distance = float('inf')
        for segment in traffic_light_segments['features']:
            if segment['geometry']['type'] == 'MultiLineString' or segment['geometry']['type'] == 'Polygon':
                for line in segment['geometry']['coordinates']:
                    line = shapely.geometry.LineString(line)
                    distance = point.distance(line)
                    if distance < nearest_distance:
                        nearest_distance = distance
                        nearest_line = line
            elif segment['geometry']['type'] == 'LineString':
                line = shapely.geometry.LineString(segment['geometry']['coordinates'])
                distance = point.distance(line)
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_line = line
            else:
                print(f'WARN Unknown geometry type: {segment["geometry"]["type"]}')

        nearest_point_idx = None
        nearest_point_distance = float('inf')
        for i, (segment_point_1, segment_point_2) in enumerate(zip(nearest_line.coords[:-1], nearest_line.coords[1:])):
            segment_point_1 = shapely.geometry.Point(segment_point_1)
            segment_point_2 = shapely.geometry.Point(segment_point_2)
            distance = shapely.geometry.LineString([segment_point_1, segment_point_2]).distance(point)
            if distance < nearest_point_distance:
                nearest_point_distance = distance
                nearest_point_idx = i

        # Connection geometry: from the traffic light to the end of the segment
        connection = [
            point.coords[0],
        ] + nearest_line.coords[nearest_point_idx + 1:]

        traffic_light_geometries.append(connection)

    base_idx = 0 # Offset for the lane IDs
    def get_idx():
        nonlocal base_idx
        base_idx += 1
        return base_idx

    print("Inserting the generated traffic lights into the FROST server.")
    for i, geometry in tqdm(enumerate(traffic_light_geometries)):
        thing_id = get_idx()
        thing_name = f"SG{i}"

        locations_id = get_idx()
        location = {
            "description": "The given geometry composed out of ingress lane, egress lane and the real route represents the location of the lane connection.",
            "encodingType": "application/vnd.geo+json",
            "@iot.id": locations_id,
            "location": {
                "type": "Feature",
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [
                        geometry, # Completely irrelevant, just use the same geometry for the ingress
                        geometry,
                        geometry, # Completely irrelevant, just use the same geometry for the egress
                    ]
                }
            },
            "name": thing_name,
            "@iot.selfLink": f"http://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/Locations({locations_id})"
        }

        dstr_program_id = get_idx()
        dstr_program_sensor_id = get_idx()
        dstr_program_observed_property_id = get_idx()
        dstr_program = {
            "description": "A unique ID (name) of the current signal program of the traffic light. It is not the control program",
            "@iot.id": dstr_program_id,
            "name": f"Signal program ID at {thing_name}",
            "observationType": "http://defs.opengis.net/elda-common/ogc-def/resource?uri=http://www.opengis.net/def/property/OGC/0/SensorStatus",
            "properties": {
                "layerName": "signal_program",
                "namespace": "Not yet available",
                "ownerData": "Free and Hanseatic City of Hamburg",
                "serviceName": "HH_STA_traffic_lights",
                "resultsNature": "Primary",
                "signalGroupID": "K2",
                "mediaMonitored": "Transport",
                "lastUpdateSignalProgram": "2021-10-22T07:40:30.138+00:00" # Completely irrelevant
            },
            "resultTime": None,
            "@iot.selfLink": f"http://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/Datastreams({dstr_program_id})",
            "unitOfMeasurement": {
                "name": "Status",
                "symbol": "-",
                "definition": "morgen, mittag, ..."
            },
            "Sensor": {
                "description": "Not available",
                "encodingType": "Not available",
                "@iot.id": dstr_program_sensor_id,
                "metadata": "Not available",
                "name": "Signal program indicator",
                "@iot.selfLink": f"http://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/Sensors({dstr_program_sensor_id})"
            },
            "ObservedProperty": {
                "description": "A signal is information broadcasted e.g. visually or acoustically. The possible transmitted information is reported in the API entity 'datastream' using the 'unitOfMeasurment'-field",
                "definition": "Not available",
                "@iot.id": dstr_program_observed_property_id,
                "name": "Signal",
                "@iot.selfLink": f"http://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/ObservedProperties({dstr_program_observed_property_id})"
            }
        }

        dstr_cycle_id = get_idx()
        dstr_cycle_sensor_id = get_idx()
        dstr_cycle_observed_property_id = get_idx()
        dstr_cycle = {
            "description": "Current second in the traffic signal cycle",
            "@iot.id": dstr_cycle_id,
            "name": f"Cycle second at {thing_name}",
            "observationType": "Primary",
            "properties": {
                "layerName": "cycle_second",
                "namespace": "Not yet available",
                "ownerData": "Free and Hanseatic City of Hamburg",
                "serviceName": "HH_STA_traffic_lights",
                "resultsNature": "Primary",
                "signalGroupID": "K2",
                "mediaMonitored": "Transport",
                "lastUpdateCycleSecond": "2021-10-22T07:40:30.140+00:00" # Completely irrelevant
            },
            "resultTime": None,
            "@iot.selfLink": f"http://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/Datastreams({dstr_cycle_id})",
            "unitOfMeasurement": {
                "name": "Second",
                "symbol": "s",
                "definition": ""
            },
            "Sensor": {
                "description": "Not available",
                "encodingType": "Not available",
                "@iot.id": dstr_cycle_sensor_id,
                "metadata": "Not available",
                "name": "Cycle second indicator",
                "@iot.selfLink": f"http://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/Sensors({dstr_cycle_sensor_id})"
            },
            "ObservedProperty": {
                "description": "A signal is information broadcasted e.g. visually or acoustically. The possible transmitted information is reported in the API entity 'datastream' using the 'unitOfMeasurment'-field",
                "definition": "Not available",
                "@iot.id": dstr_cycle_observed_property_id,
                "name": "Signal",
                "@iot.selfLink": f"http://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/ObservedProperties({dstr_cycle_observed_property_id})"
            }
        }

        dstr_primary_id = get_idx()
        dstr_primary_sensor_id = get_idx()
        dstr_primary_observed_property_id = get_idx()
        dstr_primary = {
            "description": "Datastream to broadcast the lane connection's signal value of a signal group",
            "@iot.id": dstr_primary_id,
            "name": f"Primary signal heads at {thing_name}",
            "observationType": "http://defs.opengis.net/elda-common/ogc-def/resource?uri=http://www.opengis.net/def/property/OGC/0/SensorStatus",
            "properties": {
                "layerName": "primary_signal",
                "namespace": "Not yet available",
                "ownerData": "Free and Hanseatic City of Hamburg",
                "serviceName": "HH_STA_traffic_lights",
                "resultsNature": "Primary",
                "signalGroupID": "K2",
                "mediaMonitored": "Transport"
            },
            "resultTime": None,
            "@iot.selfLink": f"hhttp://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/Datastreams({dstr_primary_id})",
            "unitOfMeasurement": {
                "name": "Status",
                "symbol": "Integer dimensionless",
                "definition": "0=dark,1=red,2=amber,3=green,4=red-amber,5=amber-flashing,6=green-flashing,9=unknown"
            },
            "Sensor": {
                "description": "A signal head emits information. The data specific implementation/type of signal heads is described in the 'datastream'",
                "encodingType": "Not available",
                "@iot.id": dstr_primary_sensor_id,
                "metadata": "Signal heads belong to the basic components of a traffic signal system. Depending on the road users and the applications to which the signals are assigned different signal heads exist. Optical signal heads generally apply to motor vehicle signals, pedestrian signals, cycle signals, tram and bus signals, auxiliary signals (amber flashing light), speed signals",
                "name": "Signal heads of traffic lights",
                "@iot.selfLink": f"http://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/Sensors({dstr_primary_sensor_id})"
            },
            "ObservedProperty": {
                "description": "A signal is information broadcasted e.g. visually or acoustically. The possible transmitted information is reported in the API entity 'datastream' using the 'unitOfMeasurment'-field",
                "definition": "Not available",
                "@iot.id": dstr_primary_observed_property_id,
                "name": "Signal",
                "@iot.selfLink": f"http://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/ObservedProperties({dstr_primary_observed_property_id})"
            }
        }

        sg_json = {
            "description": "Connection of lanes subject to a specific signal head",
            "@iot.id": thing_id,
            "name": thing_name,
            "properties": {
                "topic": "Transportation and traffic",
                "assetID": "Not available",
                "keywords": [
                    "TLF",
                    "LSA",
                    "Dresden"
                ],
                "laneType": "Radfahrer",
                "language": "EN",
                "ownerThing": "TU Dresden",
                "connectionID": f"{get_idx()}", # Completely irrelevant
                "egressLaneID": f"{get_idx()}", # Completely irrelevant
                "ingressLaneID": f"{get_idx()}", # Completely irrelevant
                "infoLastUpdate": "2021-10-22T07:40:29.229+00:00", # Completely irrelevant
                "trafficLightsID": f"{get_idx()}" # Completely irrelevant
            },
            "@iot.selfLink": f"http://priobike.vkw.tu-dresden.de:20055/FROST-Server/v1.1/Things({thing_id})",
            "Locations": [ location ],
            "Datastreams": [
                dstr_program,
                dstr_cycle,
                dstr_primary,
            ]
        }

        # Remove the existing thing
        response = requests.post(f'{BASE_URL}Things', json=sg_json)
        assert response.status_code == 201 or response.status_code == 200
    
    print("Finished inserting things.")
    return get_all_things()