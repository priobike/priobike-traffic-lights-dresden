

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