import json, geopandas as gpd
from topojson import Topology

with open('taiwan-towns-65000.topo.json') as f:
    topo = json.load(f)

# Convert to GeoJSON
topology = Topology(topo, object_name='map')
geojson = json.loads(topology.to_geojson())
gdf = gpd.GeoDataFrame.from_features(
    geojson['features']
)
gdf.plot(column='name', legend=True)
