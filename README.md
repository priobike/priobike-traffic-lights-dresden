### Quickstart

#### Prerequesites

```bash
export FROST_BASE_URL="https://priobike.vkw.tu-dresden.de/staging/frost-server-web/FROST-Server/v1.1/"
export FROST_MQTT_HOST="priobike.vkw.tu-dresden.de"
export FROST_MQTT_PORT="20056"
export FROST_MQTT_USER=""
export FROST_MQTT_PASS=""
export CTRLMESSAGES_MQTT_HOST="priobike.vkw.tu-dresden.de"
export CTRLMESSAGES_MQTT_PORT="20032"
export CTRLMESSAGES_MQTT_USER="backend"
export CTRLMESSAGES_MQTT_PASS="nWK8Am3d2Hbupx"
```

#### Run the syncer

```bash
python3 src/syncer.py
```

This script inserts traffic lights into the FROST server. Note that this script depends on the POST method to be allowed in the FROST server, meaning it should only be executed from a container within the internal docker network.

#### Run the generator

```bash
python3 src/generator.py
```

This script generates Observations based on pseudorandom traffic light programs. Note: the same traffic light will always get the same random program. The Observations are published to the FROST mqtt broker.

#### Run the converter

```bash
python3 src/converter.py
```

This script converts the control messages from the TLS message converter arriving on a MQTT broker to Observations and publishes them to the FROST mqtt broker.

See: https://github.com/priobike/priobike-tls-controller

#### Getting `locations.geojson`

Overpass turbo query

```overpass
/*
This query searches for traffic signals in Dresden, Germany, and includes the node IDs.
*/

[out:json];
// Define the area for Dresden
area[name="Dresden"]->.a;
// Search for nodes with the tag "highway" and value "traffic_signals" within the defined area
node["highway"="traffic_signals"](area.a);
out body;
>;
out skel qt;
```

#### Getting `segments.geojson`

Overpass turbo query

```overpass
/*
This query searches for traffic signals in Dresden, Germany,
returns their location, direction, and associated road segment.
*/

[out:json];
// Define the area for Dresden
area[name="Dresden"]->.a;
// Search for nodes with the tag "highway" and value "traffic_signals" within the defined area,
// and include the direction tag
node["highway"="traffic_signals"](area.a);
// Find the road segments (ways) connected to the traffic signals
way(bn);
out body;
>;
out skel qt;
```