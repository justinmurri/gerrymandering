"""
Simple demo script: generates a shapefile of fake "districts" you can open in QGIS.
Requires: geopandas, shapely
Install with: pip install geopandas shapely
"""

import geopandas as gpd
from shapely.geometry import Polygon
import pandas as pd

# --- Create 4 simple square "districts" side by side ---
districts = [
    {"district": 1, "party": "Democrat", "votes_dem": 5200, "votes_rep": 3100, "geometry": Polygon([(0,0),(1,0),(1,1),(0,1)])},
    {"district": 2, "party": "Republican","votes_dem": 2800, "votes_rep": 6400, "geometry": Polygon([(1,0),(2,0),(2,1),(1,1)])},
    {"district": 3, "party": "Democrat",  "votes_dem": 4900, "votes_rep": 3800, "geometry": Polygon([(0,1),(1,1),(1,2),(0,2)])},
    {"district": 4, "party": "Republican","votes_dem": 3100, "votes_rep": 5500, "geometry": Polygon([(1,1),(2,1),(2,2),(1,2)])},
]

# --- Build a GeoDataFrame ---
gdf = gpd.GeoDataFrame(districts, crs="EPSG:4326")  # WGS84 coordinate system

# --- Save as shapefile (QGIS can open this directly) ---
output_path = "demo_districts.shp"
gdf.to_file(output_path)

print(f"Shapefile saved to: {output_path}")
print(f"Files created: demo_districts.shp, .dbf, .shx, .prj, .cpg")
print()
print("To open in QGIS:")
print("  1. Open QGIS")
print("  2. Layer > Add Layer > Add Vector Layer")
print("  3. Browse to demo_districts.shp and click Add")
print("  4. Right-click the layer > Properties > Symbology")
print("     to color by 'party' or 'votes_dem'")
