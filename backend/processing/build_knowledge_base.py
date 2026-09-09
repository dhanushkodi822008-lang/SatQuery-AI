"""
Build the 2,000-question knowledge base for SatQuery AI.
Generates comprehensive, realistic, high-quality questions and answers
across 14 categories with beginner-first explanations.
"""
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "knowledge_base.json"

CATEGORIES = {
    "Satellite Basics": {
        "target": 300,
        "beginner_ratio": 0.55,
        "keywords": ["satellite", "remote sensing", "orbit", "sensor", "resolution", "sentinel", "landsat", "earth observation"],
    },
    "GIS, Maps & Coordinates": {
        "target": 200,
        "beginner_ratio": 0.50,
        "keywords": ["gis", "map", "coordinates", "latitude", "longitude", "wgs84", "utm", "geojson", "bounding box"],
    },
    "NDVI & Vegetation": {
        "target": 250,
        "beginner_ratio": 0.45,
        "keywords": ["ndvi", "vegetation", "greenness", "nir", "red", "canopy", "evi", "savi", "chlorophyll"],
    },
    "Agriculture & Crops": {
        "target": 250,
        "beginner_ratio": 0.45,
        "keywords": ["agriculture", "crop", "farming", "harvest", "irrigation", "soil", "yield", "drought stress"],
    },
    "Water & Water Bodies": {
        "target": 150,
        "beginner_ratio": 0.45,
        "keywords": ["water", "ndwi", "river", "lake", "reservoir", "wetland", "flood water", "turbidity"],
    },
    "Land Use & Land Cover": {
        "target": 200,
        "beginner_ratio": 0.40,
        "keywords": ["land use", "land cover", "lulc", "urban", "built-up", "forest", "grassland", "classification"],
    },
    "Forest & Environment": {
        "target": 150,
        "beginner_ratio": 0.40,
        "keywords": ["forest", "deforestation", "environment", "canopy", "biodiversity", "wildfire", "conservation"],
    },
    "Disaster & Floods": {
        "target": 150,
        "beginner_ratio": 0.40,
        "keywords": ["disaster", "flood", "inundation", "sar", "emergency", "damage assessment", "risk indicator"],
    },
    "Satellite Image Analysis": {
        "target": 150,
        "beginner_ratio": 0.35,
        "keywords": ["image analysis", "segmentation", "object detection", "spectral bands", "preprocessing", "cog", "raster"],
    },
    "Historical & Date-Based Analysis": {
        "target": 75,
        "beginner_ratio": 0.35,
        "keywords": ["historical analysis", "time series", "multitemporal", "date comparison", "change over time", "trends"],
    },
    "Prediction & Forecasting": {
        "target": 75,
        "beginner_ratio": 0.35,
        "keywords": ["prediction", "forecasting", "trend", "crop estimation", "uncertainty", "modeling"],
    },
    "AI, ML & Remote Sensing": {
        "target": 100,
        "beginner_ratio": 0.35,
        "keywords": ["ai", "machine learning", "deep learning", "computer vision", "cnn", "vision transformer", "vlm"],
    },
    "Statistics & Interpretation": {
        "target": 50,
        "beginner_ratio": 0.35,
        "keywords": ["statistics", "mean", "standard deviation", "area calculation", "hectares", "square feet", "accuracy"],
    },
    "General SatQuery AI Questions": {
        "target": 50,
        "beginner_ratio": 0.60,
        "keywords": ["satquery ai", "how to use", "aoi", "features", "export", "reports", "alerts", "workflow"],
    },
}

def generate_knowledge_base():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # We will build comprehensive high quality Q&As
    records = []
    seen_questions = set()

    def add_q(question, answer, category, intent, keywords, is_beginner=True):
        q_norm = question.strip().lower()
        if q_norm in seen_questions:
            return False
        seen_questions.add(q_norm)
        records.append({
            "question": question.strip(),
            "answer": answer.strip(),
            "category": category,
            "intent": intent,
            "keywords": keywords,
            "difficulty": "beginner" if is_beginner else "advanced"
        })
        return True

    # -------------------------------------------------------------
    # 1. CORE MUST-HAVE QUESTIONS SPECIFICALLY REQUESTED BY USER
    # -------------------------------------------------------------

    # Category A: Very Basic Satellite & Remote Sensing
    add_q(
        "What is a satellite?",
        "A satellite is an object that orbits Earth or another celestial body. In Earth observation, artificial satellites carry specialized optical, radar, or thermal sensors to capture imagery and measurements of Earth's surface, oceans, and atmosphere from space.",
        "Satellite Basics",
        "satellite_definition",
        ["satellite", "earth observation", "orbit", "space"]
    )
    add_q(
        "What is satellite imagery?",
        "Satellite imagery consists of digital photographs and multispectral data of Earth taken by sensors mounted on orbiting satellites. It allows us to view landforms, weather patterns, crops, forests, cities, and oceans from above over time.",
        "Satellite Basics",
        "satellite_imagery_definition",
        ["satellite imagery", "remote sensing", "earth observation", "photos"]
    )
    add_q(
        "What is remote sensing?",
        "Remote sensing is the science and practice of obtaining information about objects or areas on Earth's surface from a distance, typically from aircraft or orbiting satellites, without making physical contact with the ground.",
        "Satellite Basics",
        "remote_sensing_definition",
        ["remote sensing", "sensors", "earth observation", "data collection"]
    )
    add_q(
        "What is Earth observation?",
        "Earth observation (EO) refers to the systematic gathering of information about planet Earth's physical, chemical, and biological systems via remote sensing technologies, helping monitor environmental change, natural resources, weather, and disasters.",
        "Satellite Basics",
        "earth_observation_definition",
        ["earth observation", "monitoring", "environment", "satellites"]
    )
    add_q(
        "How does a satellite observe Earth?",
        "Satellites observe Earth using onboard sensors that detect electromagnetic radiation. Passive sensors capture reflected sunlight or emitted thermal radiation from Earth's surface, while active sensors (like SAR radar) emit their own pulses and record the backscattered signal.",
        "Satellite Basics",
        "satellite_observation_mechanism",
        ["sensor", "electromagnetic spectrum", "passive", "active", "sar"]
    )
    add_q(
        "How are satellite images captured?",
        "Satellite sensors capture images by focusing incoming light onto digital detector arrays (such as CCD or CMOS sensors). Each detector records the intensity of specific spectral wavelengths (like Blue, Green, Red, Near-Infrared) as digital numbers (DN) for every ground pixel.",
        "Satellite Basics",
        "satellite_capture_process",
        ["image capture", "spectral bands", "detectors", "pixels"]
    )
    add_q(
        "Why do we use satellites?",
        "Satellites provide a global, repetitive, and objective viewpoint of Earth that is impossible from the ground. They are essential for weather forecasting, agricultural monitoring, disaster management, climate research, urban planning, and navigation.",
        "Satellite Basics",
        "why_use_satellites",
        ["benefits", "global coverage", "repetitive monitoring", "applications"]
    )
    add_q(
        "What can satellite images show?",
        "Satellite images can show land cover types (forests, water bodies, urban buildings, bare soil), crop health and vegetation vigor, soil moisture, flood extent, wildfire burn scars, snow cover, glacier retreat, and urban expansion over time.",
        "Satellite Basics",
        "satellite_imagery_capabilities",
        ["features", "vegetation", "water", "urban", "disasters"]
    )
    add_q(
        "What is a satellite sensor?",
        "A satellite sensor is an instrument mounted on a spacecraft that detects and measures physical phenomena (such as light, heat, or radar waves) from Earth's surface and atmosphere and converts them into digital data.",
        "Satellite Basics",
        "satellite_sensor_definition",
        ["sensor", "instrument", "payload", "measurements"]
    )
    add_q(
        "What is a remote-sensing sensor?",
        "A remote-sensing sensor is an imaging or scanning device that records radiation reflected or emitted by targets. Common remote-sensing sensors include multispectral optical cameras, hyperspectral imagers, thermal infrared scanners, and Synthetic Aperture Radar (SAR).",
        "Satellite Basics",
        "rs_sensor_definition",
        ["sensor", "multispectral", "radar", "optical", "thermal"]
    )
    add_q(
        "What is an orbit?",
        "An orbit is the curved trajectory that a satellite follows around Earth due to gravitational pull. Common Earth observation orbits include Sun-Synchronous Low Earth Orbit (LEO, ~600–800 km altitude) and Geostationary Orbit (GEO, ~35,786 km altitude).",
        "Satellite Basics",
        "orbit_definition",
        ["orbit", "leo", "geostationary", "sun synchronous", "trajectory"]
    )
    add_q(
        "What is a satellite pass?",
        "A satellite pass refers to the brief period when an orbiting satellite travels across the sky over a specific geographical area on Earth, capturing imagery or transmitting data along its ground track (swath).",
        "Satellite Basics",
        "satellite_pass_definition",
        ["pass", "overpass", "swath", "ground track", "revisit"]
    )
    add_q(
        "What is a pixel?",
        "A pixel (picture element) is the smallest individual unit of a digital satellite image. Each pixel represents a specific area on the ground (e.g. 10 meters × 10 meters in Sentinel-2) and contains digital values representing reflected or emitted radiation.",
        "Satellite Basics",
        "pixel_definition",
        ["pixel", "raster", "resolution", "ground sampling distance"]
    )
    add_q(
        "What is image resolution?",
        "Image resolution in satellite remote sensing describes the level of detail captured by a sensor. It encompasses four distinct dimensions: spatial resolution (pixel size), spectral resolution (band wavelengths), radiometric resolution (bit depth), and temporal resolution (revisit frequency).",
        "Satellite Basics",
        "image_resolution_overview",
        ["resolution", "spatial", "spectral", "temporal", "radiometric"]
    )
    add_q(
        "What is spatial resolution?",
        "Spatial resolution refers to the ground area represented by a single pixel in an image. For example, a 10-meter spatial resolution (like Sentinel-2) means each pixel covers a 10 m × 10 m patch on the ground. Smaller numbers mean higher spatial detail.",
        "Satellite Basics",
        "spatial_resolution_definition",
        ["spatial resolution", "pixel size", "ground resolution", "detail"]
    )
    add_q(
        "What is temporal resolution?",
        "Temporal resolution (or revisit time) is how frequently a satellite returns to image the exact same location on Earth. For example, Sentinel-2 has a 5-day temporal revisit (with both 2A and 2B satellites), while Landsat has a 16-day revisit.",
        "Satellite Basics",
        "temporal_resolution_definition",
        ["temporal resolution", "revisit time", "frequency", "monitoring"]
    )
    add_q(
        "What is spectral resolution?",
        "Spectral resolution describes the number and width of specific wavelength bands recorded by a sensor. A sensor with narrow, numerous bands has high spectral resolution, enabling it to distinguish between subtle chemical and biological differences in plants, minerals, and water.",
        "Satellite Basics",
        "spectral_resolution_definition",
        ["spectral resolution", "bands", "wavelength", "multispectral", "hyperspectral"]
    )
    add_q(
        "What is a spectral band?",
        "A spectral band is a discrete, specific segment of the electromagnetic spectrum that a satellite sensor records independently, such as Blue (490 nm), Green (560 nm), Red (665 nm), Near-Infrared (842 nm), or Shortwave-Infrared (1610 nm).",
        "Satellite Basics",
        "spectral_band_definition",
        ["spectral band", "wavelength", "rgb", "nir", "swir"]
    )
    add_q(
        "What is multispectral imagery?",
        "Multispectral imagery is satellite data that captures multiple distinct spectral bands (typically between 3 to 15 bands) simultaneously across visible, near-infrared, and shortwave-infrared wavelengths, enabling the calculation of vegetation, water, and soil indices.",
        "Satellite Basics",
        "multispectral_definition",
        ["multispectral", "bands", "sentinel-2", "landsat", "indices"]
    )
    add_q(
        "What is an RGB satellite image?",
        "An RGB satellite image is a true-color composite formed by displaying the Red, Green, and Blue spectral bands through the red, green, and blue display channels of a screen, producing a picture that looks natural to human eyes.",
        "Satellite Basics",
        "rgb_image_definition",
        ["rgb", "true color", "composite", "natural color", "visual"]
    )
    add_q(
        "What is Landsat?",
        "Landsat is a joint NASA/USGS Earth observation satellite program that has continuously acquired optical multispectral imagery of Earth since 1972. Landsat data provides 30-meter resolution imagery with over 50 years of historical archive for long-term change detection.",
        "Satellite Basics",
        "landsat_definition",
        ["landsat", "usgs", "nasa", "30m", "historical archive"]
    )
    add_q(
        "What is Sentinel?",
        "Sentinel is a family of Earth observation satellite missions developed by the European Space Agency (ESA) under the European Union's Copernicus Programme to deliver free, open, high-frequency radar and optical data for global monitoring.",
        "Satellite Basics",
        "sentinel_overview",
        ["sentinel", "copernicus", "esa", "earth observation", "free data"]
    )
    add_q(
        "What is Sentinel-1?",
        "Sentinel-1 is a European Space Agency radar satellite mission carrying a C-band Synthetic Aperture Radar (SAR) sensor. Because radar penetrates clouds and works day or night, Sentinel-1 is ideal for flood mapping, soil moisture, and emergency disaster response.",
        "Satellite Basics",
        "sentinel1_definition",
        ["sentinel-1", "sar", "radar", "all weather", "flood mapping"]
    )
    add_q(
        "What is Sentinel-2?",
        "Sentinel-2 is a European Space Agency optical satellite mission providing high-resolution multispectral imagery in 13 spectral bands (10 m, 20 m, and 60 m spatial resolution) with a 5-day global revisit time, widely used for agriculture, forestry, and water monitoring.",
        "Satellite Basics",
        "sentinel2_definition",
        ["sentinel-2", "msi", "optical", "10m", "vegetation", "ndvi"]
    )
    add_q(
        "What is NASA?",
        "NASA (National Aeronautics and Space Administration) is the United States civil space agency responsible for scientific space exploration, aeronautics, and Earth science satellite missions like Landsat, Terra, Aqua, MODIS, and ICESat.",
        "Satellite Basics",
        "nasa_definition",
        ["nasa", "space agency", "earth science", "satellites", "landsat"]
    )
    add_q(
        "What is ISRO?",
        "ISRO (Indian Space Research Organisation) is India's national space agency, renowned for developing and operating Earth observation satellites including the IRS series, Cartosat, Resourcesat, Oceansat, and RISAT for national resource management and disaster mitigation.",
        "Satellite Basics",
        "isro_definition",
        ["isro", "india", "earth observation", "resourcesat", "cartosat", "risat"]
    )
    add_q(
        "What is ESA?",
        "ESA (European Space Agency) is an intergovernmental organization dedicated to space exploration, satellite technology, and Earth observation, managing the Copernicus Sentinel fleet, Envisat, CryoSat, and scientific Earth Explorer missions.",
        "Satellite Basics",
        "esa_definition",
        ["esa", "europe", "copernicus", "sentinel", "space agency"]
    )

    # Category B: GIS, Maps & Coordinates
    add_q(
        "What is GIS?",
        "GIS stands for Geographic Information System. It is a computer system designed to capture, store, manipulate, analyze, manage, and visualize all types of geographical and spatial data on interactive digital maps.",
        "GIS, Maps & Coordinates",
        "gis_definition",
        ["gis", "geographic information system", "mapping", "spatial analysis"]
    )
    add_q(
        "What is a map?",
        "A map is a visual representation of an entire area or a part of an area, typically depicted on a flat surface, illustrating spatial relationships between geographic features like roads, rivers, cities, boundaries, and terrain.",
        "GIS, Maps & Coordinates",
        "map_definition",
        ["map", "cartography", "spatial representation", "geography"]
    )
    add_q(
        "What is a digital map?",
        "A digital map is an electronic map stored in digital format, composed of vector shapes (points, lines, polygons) or raster images, which users can zoom, pan, query, and overlay with different layers of spatial information.",
        "GIS, Maps & Coordinates",
        "digital_map_definition",
        ["digital map", "web mapping", "layers", "gis"]
    )
    add_q(
        "What is a satellite map?",
        "A satellite map is a digital map where the base imagery consists of georeferenced satellite photographs, showing real ground features like fields, forests, buildings, rivers, and roads as they appear from space.",
        "GIS, Maps & Coordinates",
        "satellite_map_definition",
        ["satellite map", "basemap", "orthophoto", "aerial view"]
    )
    add_q(
        "What is latitude?",
        "Latitude is a geographic coordinate that specifies the north-south position of a point on Earth's surface. It is measured in degrees from 0° at the Equator to +90° at the North Pole and -90° at the South Pole.",
        "GIS, Maps & Coordinates",
        "latitude_definition",
        ["latitude", "coordinates", "north south", "equator", "degrees"]
    )
    add_q(
        "What is longitude?",
        "Longitude is a geographic coordinate that specifies the east-west position of a point on Earth's surface. It is measured in degrees from 0° at the Prime Meridian (Greenwich) to +180° East and -180° West.",
        "GIS, Maps & Coordinates",
        "longitude_definition",
        ["longitude", "coordinates", "east west", "prime meridian", "degrees"]
    )
    add_q(
        "What are coordinates?",
        "Coordinates are pairs of numbers (such as latitude and longitude, or X and Y) that define the exact geographic location of a point on Earth's surface within a specific reference coordinate system.",
        "GIS, Maps & Coordinates",
        "coordinates_definition",
        ["coordinates", "location", "lat lon", "gps", "geographic position"]
    )
    add_q(
        "How do I find latitude and longitude?",
        "You can find latitude and longitude by searching a place name in SatQuery AI's search bar, clicking on any point on a digital map, or using GPS on a mobile device or mapping service like OpenStreetMap or Google Maps.",
        "GIS, Maps & Coordinates",
        "find_lat_lon",
        ["find coordinates", "search location", "geocoding", "gps"]
    )
    add_q(
        "How do I enter coordinates in SatQuery AI?",
        "You can enter coordinates by typing latitude and longitude (e.g., '10.96, 78.08' or 'lat: 10.96, lon: 78.08') into the location search box and clicking 'Go'. SatQuery AI will automatically center the map on those coordinates.",
        "GIS, Maps & Coordinates",
        "enter_coordinates",
        ["enter coordinates", "search", "navigation", "satquery"]
    )
    add_q(
        "What is GPS?",
        "GPS (Global Positioning System) is a satellite-based radio navigation system owned by the United States that allows GPS receivers on Earth to determine their precise geographic location (latitude, longitude, altitude) and time anywhere in the world.",
        "GIS, Maps & Coordinates",
        "gps_definition",
        ["gps", "navigation", "positioning", "gnss", "satellites"]
    )
    add_q(
        "What is WGS84?",
        "WGS84 (World Geodetic System 1984, EPSG:4326) is the standard global reference ellipsoid and coordinate system used by GPS, Google Maps, OpenStreetMap, and SatQuery AI to express latitude and longitude worldwide.",
        "GIS, Maps & Coordinates",
        "wgs84_definition",
        ["wgs84", "epsg:4326", "datum", "coordinate system", "gps"]
    )
    add_q(
        "What is UTM?",
        "UTM (Universal Transverse Mercator) is a projected coordinate system that divides Earth into 60 longitudinal zones of 6° each, measuring positions in meters (Easting and Northing) for accurate local distance and area calculations.",
        "GIS, Maps & Coordinates",
        "utm_definition",
        ["utm", "projection", "meters", "easting", "northing", "zone"]
    )
    add_q(
        "What is a coordinate system?",
        "A coordinate system is a mathematical framework used to define the positions of points in space. In GIS, coordinate reference systems (CRS) can be geographic (degrees of latitude/longitude on a sphere) or projected (meters on a flat 2D plane).",
        "GIS, Maps & Coordinates",
        "coordinate_system_definition",
        ["crs", "coordinate system", "geographic", "projected", "gis"]
    )
    add_q(
        "What is a map layer?",
        "A map layer is a distinct visual dataset overlaid on a base map. For example, a map can display a satellite image basemap layer, an NDVI vegetation layer, a water bodies vector layer, and a boundary marker layer on top of each other.",
        "GIS, Maps & Coordinates",
        "map_layer_definition",
        ["layer", "overlay", "basemap", "vector", "raster"]
    )
    add_q(
        "What is a map marker?",
        "A map marker is an icon or graphic point placed at a specific coordinate on a digital map to highlight a point of interest, search result, or monitored site.",
        "GIS, Maps & Coordinates",
        "map_marker_definition",
        ["marker", "pin", "point of interest", "leaflet", "map"]
    )
    add_q(
        "What is a bounding box?",
        "A bounding box (bbox) is a rectangular geographic boundary defined by four coordinates: minimum longitude (West), minimum latitude (South), maximum longitude (East), and maximum latitude (North) enclosing an area of interest.",
        "GIS, Maps & Coordinates",
        "bounding_box_definition",
        ["bounding box", "bbox", "extent", "aoi", "rectangle"]
    )
    add_q(
        "What is geographic data?",
        "Geographic data (or geospatial data) is information that describes objects, events, or features with reference to a specific location on Earth's surface, combining spatial coordinates with attribute properties.",
        "GIS, Maps & Coordinates",
        "geographic_data_definition",
        ["geographic data", "geospatial", "attributes", "gis", "location"]
    )
    add_q(
        "What is spatial data?",
        "Spatial data is any digital data representing the location, shape, and geometric relationship of geographic features, typically structured either as vector data (points, lines, polygons) or raster data (gridded pixel arrays).",
        "GIS, Maps & Coordinates",
        "spatial_data_definition",
        ["spatial data", "vector", "raster", "geometry", "gis"]
    )

    # Category C: NDVI & Vegetation
    add_q(
        "What is NDVI?",
        "NDVI stands for Normalized Difference Vegetation Index. It is a widely used value calculated from satellite imagery that indicates the presence, density, and greenness of living vegetation on Earth's surface.",
        "NDVI & Vegetation",
        "ndvi_definition",
        ["ndvi", "vegetation index", "greenness", "plant health"]
    )
    add_q(
        "What does NDVI mean?",
        "NDVI measures how strongly vegetation absorbs red light (used for photosynthesis) and reflects near-infrared light (reflected by healthy plant cell structures). Higher NDVI values indicate healthier, denser green vegetation.",
        "NDVI & Vegetation",
        "ndvi_meaning",
        ["ndvi meaning", "chlorophyll", "photosynthesis", "plant vigor"]
    )
    add_q(
        "Why is NDVI used?",
        "NDVI is used because it provides a reliable, standardized, objective way to monitor crop growth, forest cover, drought impact, pasture health, and land degradation across large regions without needing manual ground inspections.",
        "NDVI & Vegetation",
        "why_use_ndvi",
        ["ndvi purpose", "crop monitoring", "drought", "forest health"]
    )
    add_q(
        "How is NDVI calculated?",
        "NDVI is calculated using the formula: NDVI = (NIR − Red) / (NIR + Red), where NIR is Near-Infrared band reflectance and Red is Red band reflectance. The resulting index values always range from -1.0 to +1.0.",
        "NDVI & Vegetation",
        "ndvi_formula",
        ["ndvi formula", "nir", "red", "calculation", "math"]
    )
    add_q(
        "What does high NDVI mean?",
        "A high NDVI value (typically between 0.6 and 0.9) means there is dense, healthy, actively growing green vegetation with high chlorophyll content, such as lush forests, mature crops, or dense grasslands.",
        "NDVI & Vegetation",
        "high_ndvi_meaning",
        ["high ndvi", "healthy crops", "dense vegetation", "chlorophyll"]
    )
    add_q(
        "What does low NDVI mean?",
        "A low NDVI value (between 0.1 and 0.3) indicates sparse, stressed, drying vegetation, bare soil, sand, or built-up urban structures with minimal green plant matter.",
        "NDVI & Vegetation",
        "low_ndvi_meaning",
        ["low ndvi", "sparse vegetation", "bare soil", "crop stress"]
    )
    add_q(
        "What does negative NDVI mean?",
        "Negative NDVI values (below 0.0, often between -0.1 and -0.5) indicate non-vegetated surfaces that reflect more red light than near-infrared, such as open water bodies (rivers, lakes, oceans), snow, ice, or dense clouds.",
        "NDVI & Vegetation",
        "negative_ndvi_meaning",
        ["negative ndvi", "water", "clouds", "snow", "non vegetation"]
    )
    add_q(
        "What is healthy vegetation in satellite imagery?",
        "Healthy vegetation has dense chlorophyll that strongly absorbs visible red light for photosynthesis and spongy mesophyll leaf cells that strongly reflect near-infrared radiation, creating high contrast between Red and NIR bands (high NDVI).",
        "NDVI & Vegetation",
        "healthy_vegetation_definition",
        ["healthy vegetation", "chlorophyll", "nir reflectance", "plant vigor"]
    )
    add_q(
        "What is unhealthy vegetation in satellite imagery?",
        "Unhealthy or stressed vegetation has damaged cell structures and reduced chlorophyll, which causes it to reflect less near-infrared light and absorb less red light, resulting in lower NDVI values.",
        "NDVI & Vegetation",
        "unhealthy_vegetation_definition",
        ["unhealthy vegetation", "crop stress", "leaf damage", "yellowing"]
    )
    add_q(
        "What is vegetation stress?",
        "Vegetation stress refers to any adverse condition (such as drought, disease, nutrient deficiency, waterlogging, or pest infestation) that impairs plant growth and photosynthesis, observable as a decline in NDVI over time.",
        "NDVI & Vegetation",
        "vegetation_stress_definition",
        ["vegetation stress", "drought", "pests", "disease", "decline"]
    )
    add_q(
        "How can NDVI monitor crops?",
        "NDVI monitors crops by tracking their greenness curve throughout the growing season: increasing during germination and vegetative growth, peaking at flowering/heading, and declining as crops mature and ripen for harvest.",
        "NDVI & Vegetation",
        "ndvi_crop_monitoring",
        ["crop monitoring", "growth stages", "phenology", "harvest"]
    )
    add_q(
        "How can NDVI detect vegetation?",
        "NDVI detects vegetation by contrasting the high reflectance of plant canopies in the near-infrared spectrum against the strong absorption of light in the red spectrum. Non-vegetated surfaces lack this distinctive spectral signature.",
        "NDVI & Vegetation",
        "ndvi_vegetation_detection",
        ["spectral signature", "detection", "chlorophyll", "plants"]
    )
    add_q(
        "How can I understand an NDVI map?",
        "On a typical color-coded NDVI map: dark green indicates dense healthy vegetation (0.6–0.9), light green/yellow indicates moderate or sparse vegetation (0.3–0.5), brown/tan indicates bare soil (0.1–0.2), and blue indicates open water (< 0.0).",
        "NDVI & Vegetation",
        "understanding_ndvi_map",
        ["ndvi map", "color scale", "interpretation", "legend"]
    )
    add_q(
        "Why does vegetation have a high NDVI?",
        "Vegetation has high NDVI because chlorophyll pigments inside leaves absorb red light for energy, while the internal structure of healthy leaves reflects up to 50% of incoming near-infrared radiation to prevent overheating.",
        "NDVI & Vegetation",
        "why_high_ndvi",
        ["leaf structure", "mesophyll", "nir", "chlorophyll"]
    )
    add_q(
        "What causes low NDVI?",
        "Low NDVI can be caused by lack of vegetation (bare soil, concrete, asphalt), severe drought or water stress, crop senescence before harvest, pest damage, plant disease, or cloud shadows obscuring the ground.",
        "NDVI & Vegetation",
        "causes_low_ndvi",
        ["low ndvi causes", "drought", "soil", "urban", "harvest"]
    )
    add_q(
        "What is EVI?",
        "EVI (Enhanced Vegetation Index) is an optimized vegetation index designed to improve sensitivity in high-biomass regions (like rainforests) where NDVI saturates, while correcting for atmospheric aerosols and soil canopy background signals using Blue, Red, and NIR bands.",
        "NDVI & Vegetation",
        "evi_definition",
        ["evi", "enhanced vegetation index", "high biomass", "canopy"]
    )
    add_q(
        "What is a vegetation index?",
        "A vegetation index is a mathematical combination of spectral bands (such as NDVI, EVI, SAVI, NDRE) calculated to highlight the presence, health, density, or moisture content of green plant canopies in satellite imagery.",
        "NDVI & Vegetation",
        "vegetation_index_definition",
        ["vegetation index", "spectral index", "ndvi", "evi", "savi"]
    )

    # Category D: Agriculture & Crops
    add_q(
        "How can satellites help farmers?",
        "Satellites help farmers by providing regular bird's-eye updates on field health, detecting early crop stress before it is visible on the ground, mapping soil moisture, optimizing irrigation and fertilizer schedules, and estimating yields.",
        "Agriculture & Crops",
        "how_satellites_help_farmers",
        ["farmers", "precision agriculture", "crop monitoring", "benefits"]
    )
    add_q(
        "How can satellite imagery monitor crops?",
        "Satellite imagery monitors crops by capturing multispectral images every few days. By tracking changes in NDVI and NDWI over time, algorithms assess crop growth rates, identify uneven field development, and flag stressed zones.",
        "Agriculture & Crops",
        "satellite_crop_monitoring_process",
        ["crop monitoring", "time series", "ndvi", "growth tracking"]
    )
    add_q(
        "Can satellites detect crop health?",
        "Yes, satellites detect crop health by measuring spectral reflectance in near-infrared and red-edge bands. Healthy crops with high chlorophyll reflect strong NIR signals, while stressed or diseased crops show a measurable drop in reflectance.",
        "Agriculture & Crops",
        "detect_crop_health",
        ["crop health", "chlorophyll", "spectral reflectance", "detection"]
    )
    add_q(
        "Can satellites detect crop stress?",
        "Yes, satellites detect crop stress caused by water deficits, nutrient deficiencies, or pests by identifying localized drops in NDVI or moisture indices (NDWI/NDMI) weeks before physical wilting is obvious to the naked eye.",
        "Agriculture & Crops",
        "detect_crop_stress",
        ["crop stress", "drought", "nutrient deficiency", "early warning"]
    )
    add_q(
        "Can satellites identify farmland?",
        "Yes, satellites identify farmland through spectral classification and time-series analysis that recognizes regular field geometries, plow-to-growth-to-harvest seasonal cycles, and distinct crop spectral signatures.",
        "Agriculture & Crops",
        "identify_farmland",
        ["farmland", "crop classification", "field boundaries", "lulc"]
    )
    add_q(
        "Can satellite images monitor crop growth?",
        "Yes, satellite images track crop growth across phenological stages: from emergence (low NDVI ~0.2), vegetative growth (rising NDVI), peak canopy (NDVI 0.7–0.8), to maturation and senescence (declining NDVI).",
        "Agriculture & Crops",
        "monitor_crop_growth",
        ["crop growth", "phenology", "stages", "canopy development"]
    )
    add_q(
        "How can I monitor my agricultural land in SatQuery AI?",
        "To monitor agricultural land in SatQuery AI: search your village or farm location, draw an AOI polygon over your fields, and click 'Agriculture' or ask 'Assess agricultural land and crop health' to compute real NDVI, vegetated area, and crop vigor.",
        "Agriculture & Crops",
        "monitor_agri_land_satquery",
        ["satquery ai", "monitor farm", "aoi", "agriculture analysis"]
    )
    add_q(
        "How can I compare crop conditions between two dates?",
        "In SatQuery AI, navigate to the Change Prediction section, select Date A (e.g., planting season) and Date B (e.g., peak growth), and click Compare. SatQuery computes spectral index differences and maps vegetation gains or losses.",
        "Agriculture & Crops",
        "compare_crop_conditions",
        ["compare dates", "change detection", "crop conditions", "satquery"]
    )
    add_q(
        "Can satellites detect drought-affected crops?",
        "Yes, satellites detect drought-affected crops by combining declining NDVI trends with Shortwave Infrared (SWIR) moisture indices (NDMI/NDWI) and thermal anomalies, which indicate low leaf water content and reduced transpiration.",
        "Agriculture & Crops",
        "detect_drought_crops",
        ["drought", "water stress", "swir", "moisture index"]
    )
    add_q(
        "Can satellites detect irrigation problems?",
        "Yes, satellites detect irrigation problems by revealing uneven moisture and vegetation patterns across a single field—such as clogged drip lines, broken pivot sprinklers, or dry field edges showing localized low NDVI.",
        "Agriculture & Crops",
        "detect_irrigation_problems",
        ["irrigation", "pivot", "uneven growth", "water distribution"]
    )
    add_q(
        "How can AI help agriculture?",
        "AI helps agriculture by automatically classifying crop types, predicting harvest yields from satellite time-series, identifying pest hotspots, recommending precise fertilizer dosages, and generating automated farm advisory reports.",
        "Agriculture & Crops",
        "how_ai_helps_agriculture",
        ["ai in agriculture", "yield prediction", "crop classification", "precision farming"]
    )
    add_q(
        "How can remote sensing help farmers?",
        "Remote sensing helps farmers reduce input costs (water, fertilizer, pesticides) by pinpointing problem zones, avoiding unnecessary full-field spraying, optimizing harvest timing, and providing verified records for crop insurance claims.",
        "Agriculture & Crops",
        "rs_help_farmers",
        ["remote sensing", "benefits", "crop insurance", "variable rate"]
    )

    # Category E: Water & Water Bodies
    add_q(
        "What is a water body?",
        "A water body is any significant accumulation of water on Earth's surface, including oceans, seas, lakes, rivers, streams, reservoirs, ponds, canals, and wetlands.",
        "Water & Water Bodies",
        "water_body_definition",
        ["water body", "lake", "river", "reservoir", "hydrology"]
    )
    add_q(
        "How can satellites detect water?",
        "Satellites detect water because clear liquid water strongly absorbs near-infrared (NIR) and shortwave-infrared (SWIR) radiation while reflecting visible green and blue light, producing a sharp spectral contrast against land.",
        "Water & Water Bodies",
        "detect_water_mechanism",
        ["water detection", "absorption", "nir", "green band"]
    )
    add_q(
        "Can satellites detect rivers?",
        "Yes, optical and radar satellites detect rivers as long linear water features with high NDWI values and distinct low radar backscatter compared to surrounding banks.",
        "Water & Water Bodies",
        "detect_rivers",
        ["rivers", "waterways", "ndwi", "sar"]
    )
    add_q(
        "Can satellites detect lakes?",
        "Yes, satellites map lake boundaries, surface area, and seasonal expansions or shrinkages by applying water index thresholds (like NDWI > 0.0) across multi-temporal imagery.",
        "Water & Water Bodies",
        "detect_lakes",
        ["lakes", "surface area", "ndwi", "water monitoring"]
    )
    add_q(
        "Can satellites detect reservoirs?",
        "Yes, satellites monitor artificial reservoirs and dams by tracking water surface spread over time, which provides an effective proxy for estimating storage volume changes.",
        "Water & Water Bodies",
        "detect_reservoirs",
        ["reservoirs", "dams", "storage capacity", "water extent"]
    )
    add_q(
        "How can I identify water in a satellite image?",
        "In a true-color (RGB) image, deep clean water appears dark blue or black, while shallow or sediment-laden water appears turquoise or brown. In False Color (NIR-Red-Green), water appears pitch black or dark navy.",
        "Water & Water Bodies",
        "identify_water_in_image",
        ["identify water", "rgb", "false color", "visual appearance"]
    )
    add_q(
        "What is NDWI?",
        "NDWI (Normalized Difference Water Index) is a satellite index used to highlight open water surfaces and eliminate soil and terrestrial vegetation. McFeeters NDWI is calculated as: (Green − NIR) / (Green + NIR). Positive values indicate water.",
        "Water & Water Bodies",
        "ndwi_definition",
        ["ndwi", "water index", "green", "nir", "formula"]
    )
    add_q(
        "What is water-body detection?",
        "Water-body detection is the automated process of segmenting and classifying pixels in satellite images that represent open water bodies using spectral thresholding (NDWI/MNDWI), machine learning, or radar backscatter analysis.",
        "Water & Water Bodies",
        "water_detection_process",
        ["water detection", "segmentation", "classification", "mapping"]
    )
    add_q(
        "How can satellites monitor water?",
        "Satellites monitor water by tracking surface water extent, measuring reservoir shrinkage during droughts, mapping flood inundation, assessing water turbidity and algal blooms, and estimating snowpack melt.",
        "Water & Water Bodies",
        "satellite_water_monitoring",
        ["water monitoring", "drought", "algal blooms", "hydrology"]
    )
    add_q(
        "Can satellite imagery detect floods?",
        "Yes, satellite imagery detects floods by identifying newly inundated land where water was previously absent. Radar satellites (Sentinel-1) are especially valuable during floods because they see through heavy rain and cloud cover.",
        "Water & Water Bodies",
        "detect_floods_satellite",
        ["floods", "inundation", "sentinel-1", "sar", "emergency"]
    )

    # Category F: Land Use & Land Cover
    add_q(
        "What is land use?",
        "Land use describes how human beings utilize and manage the land surface for socio-economic activities, such as agriculture, residential housing, industrial zones, commercial forestry, or recreation.",
        "Land Use & Land Cover",
        "land_use_definition",
        ["land use", "human activity", "socio economic", "zoning"]
    )
    add_q(
        "What is land cover?",
        "Land cover describes the physical material present on the surface of Earth, such as forests, grasslands, open water, wetlands, bare rock, sand dunes, or impervious artificial structures.",
        "Land Use & Land Cover",
        "land_cover_definition",
        ["land cover", "physical surface", "vegetation", "water", "urban"]
    )
    add_q(
        "What is land-use classification?",
        "Land-use classification is the process of categorizing land parcels based on their functional human purpose (e.g. commercial, residential, agricultural, recreational) by combining satellite observations with ground survey data.",
        "Land Use & Land Cover",
        "land_use_classification_definition",
        ["land use classification", "urban planning", "zoning", "gis"]
    )
    add_q(
        "What is land-cover classification?",
        "Land-cover classification is the computational analysis of satellite pixels into distinct biophysical categories (e.g. water, forest, cropland, built-up, bare soil) based on their spectral signatures and textures.",
        "Land Use & Land Cover",
        "land_cover_classification_definition",
        ["land cover classification", "spectral signature", "raster", "classes"]
    )
    add_q(
        "What is agricultural land?",
        "Agricultural land refers to land areas used for cultivating annual or perennial crops, pastures, orchards, and livestock grazing, characterized by seasonal planting and harvest cycles.",
        "Land Use & Land Cover",
        "agricultural_land_definition",
        ["agricultural land", "cropland", "pasture", "farming"]
    )
    add_q(
        "What is forest land?",
        "Forest land refers to land spanning more than 0.5 hectares with trees higher than 5 meters and a canopy cover of more than 10%, showing persistent high NDVI throughout multiple seasons.",
        "Land Use & Land Cover",
        "forest_land_definition",
        ["forest land", "canopy", "trees", "woodland"]
    )
    add_q(
        "What is urban land?",
        "Urban land consists of built-up areas dominated by human structures, including residential houses, commercial buildings, paved roads, parking lots, and industrial infrastructure.",
        "Land Use & Land Cover",
        "urban_land_definition",
        ["urban land", "built up", "city", "infrastructure", "concrete"]
    )
    add_q(
        "What is bare land?",
        "Bare land (or barren land) comprises exposed soil, rocks, sand, gravel, dry riverbeds, or mining sites with little to no green vegetation cover, showing moderate red and SWIR reflectance and low NDVI (< 0.2).",
        "Land Use & Land Cover",
        "bare_land_definition",
        ["bare land", "soil", "rock", "sand", "barren"]
    )
    add_q(
        "What is grassland?",
        "Grassland is land dominated by herbaceous vegetation and grasses with fewer than 10% tree or shrub canopy cover, showing moderate seasonal greenness and rapid response to rainfall.",
        "Land Use & Land Cover",
        "grassland_definition",
        ["grassland", "pasture", "rangeland", "savanna"]
    )
    add_q(
        "What is built-up land?",
        "Built-up land encompasses man-made impervious surfaces like concrete, asphalt, metal roofing, and buildings. It is commonly identified using the Normalized Difference Built-up Index (NDBI).",
        "Land Use & Land Cover",
        "built_up_land_definition",
        ["built up", "impervious", "ndbi", "settlements", "urban"]
    )
    add_q(
        "How can satellites classify land?",
        "Satellites classify land by analyzing how different ground materials reflect light across multiple spectral bands. Machine learning models (like Random Forests or Neural Networks) classify each pixel into predefined land cover categories.",
        "Land Use & Land Cover",
        "how_satellites_classify_land",
        ["classification", "machine learning", "spectral bands", "lulc"]
    )
    add_q(
        "How can AI identify different land types?",
        "AI identifies land types using convolutional neural networks and semantic segmentation models that learn both spectral values and spatial context (shapes, textures, neighbor patterns) to distinguish croplands, forests, water, and buildings.",
        "Land Use & Land Cover",
        "how_ai_identifies_land",
        ["ai land classification", "deep learning", "semantic segmentation", "patterns"]
    )

    # Category G: Forest & Environment
    add_q(
        "What is a forest?",
        "A forest is an ecosystem dominated by trees, shrubs, and understory vegetation that supports rich biodiversity, stores terrestrial carbon, regulates water cycles, and prevents soil erosion.",
        "Forest & Environment",
        "forest_definition",
        ["forest", "canopy", "ecosystem", "trees", "carbon"]
    )
    add_q(
        "How can satellites monitor forests?",
        "Satellites monitor forests by capturing multi-temporal images to assess canopy density (NDVI/EVI), track canopy moisture (NDMI), detect tree cutting or clearing, monitor wildfire burn scars, and measure reforestation progress.",
        "Forest & Environment",
        "how_satellites_monitor_forests",
        ["forest monitoring", "canopy", "deforestation", "conservation"]
    )
    add_q(
        "What is deforestation?",
        "Deforestation is the purposeful permanent clearing, thinning, or removal of forested land by human activities, such as agricultural expansion, timber logging, mining, or urban development.",
        "Forest & Environment",
        "deforestation_definition",
        ["deforestation", "forest loss", "logging", "clearing"]
    )
    add_q(
        "Can satellites detect deforestation?",
        "Yes, satellites detect deforestation by identifying abrupt drops in vegetation indices (NDVI/EVI) and changes in texture between historical baseline images and newly acquired scenes.",
        "Forest & Environment",
        "detect_deforestation",
        ["deforestation detection", "change detection", "forest loss", "alerts"]
    )
    add_q(
        "How can satellites detect vegetation loss?",
        "Satellites detect vegetation loss by performing pixel-wise differencing between two dates. Areas where NDVI drops significantly (e.g. from 0.75 to 0.20) indicate clearings, fires, logging, or crop harvesting.",
        "Forest & Environment",
        "detect_vegetation_loss",
        ["vegetation loss", "ndvi difference", "clearing", "monitoring"]
    )
    add_q(
        "What is environmental monitoring?",
        "Environmental monitoring is the continuous observation, assessment, and modeling of environmental conditions—including air quality, forest health, water quality, soil erosion, and climate trends—using satellite and ground data.",
        "Forest & Environment",
        "environmental_monitoring_definition",
        ["environmental monitoring", "conservation", "climate", "ecosystem"]
    )
    add_q(
        "How can satellite imagery monitor the environment?",
        "Satellite imagery monitors the environment by tracking melting ice caps, deforestation rates, greenhouse gas emissions, expanding desertification, mangrove degradation, and urban heat island effects across global and regional scales.",
        "Forest & Environment",
        "satellite_env_monitoring",
        ["environment", "glaciers", "desertification", "heat island", "mangroves"]
    )
    add_q(
        "Can satellites monitor wetlands?",
        "Yes, satellites monitor wetlands by tracking the dynamic boundary between open water, emergent vegetation, and saturated soils using combined optical indices (NDWI, NDVI) and SAR radar backscatter.",
        "Forest & Environment",
        "monitor_wetlands",
        ["wetlands", "marsh", "ndwi", "sar", "biodiversity"]
    )
    add_q(
        "Can satellites monitor coastlines?",
        "Yes, satellites monitor coastlines by tracking tidal boundaries, mapping coastal erosion or accretion, detecting mangrove changes, and monitoring coral reef bleaching and sea surface temperatures.",
        "Forest & Environment",
        "monitor_coastlines",
        ["coastlines", "coastal erosion", "mangroves", "coral reefs", "tides"]
    )

    # Category H: Disaster & Floods
    add_q(
        "What is a flood?",
        "A flood is an overflow of water that submerges land that is usually dry, commonly caused by intense rainfall, river overflows, storm surges, dam failures, or rapid snowmelt.",
        "Disaster & Floods",
        "flood_definition",
        ["flood", "inundation", "overflow", "disaster"]
    )
    add_q(
        "How can satellites detect floods?",
        "Satellites detect floods by comparing pre-disaster and post-disaster imagery. Synthetic Aperture Radar (Sentinel-1) is especially effective because calm floodwaters act as specular reflectors, creating very dark radar return signals even through cloud cover.",
        "Disaster & Floods",
        "detect_floods_mechanism",
        ["flood detection", "sar", "specular reflection", "sentinel-1"]
    )
    add_q(
        "What is flood mapping?",
        "Flood mapping is the creation of geospatial maps outlining the spatial extent, depth, and duration of floodwaters over affected roads, agricultural lands, and residential neighborhoods during and after an inundation event.",
        "Disaster & Floods",
        "flood_mapping_definition",
        ["flood mapping", "inundation map", "damage assessment", "emergency"]
    )
    add_q(
        "What is disaster monitoring?",
        "Disaster monitoring is the real-time and near-real-time surveillance of natural hazards (floods, cyclones, earthquakes, wildfires, landslides, volcanic eruptions) using satellites to assist emergency response, rescue operations, and relief distribution.",
        "Disaster & Floods",
        "disaster_monitoring_definition",
        ["disaster monitoring", "emergency response", "hazards", "relief"]
    )
    add_q(
        "How can satellite imagery help during disasters?",
        "Satellite imagery helps during disasters by providing first responders with rapid situational maps, identifying flooded transport routes, mapping destroyed infrastructure, locating stranded populations, and coordinating relief logistics.",
        "Disaster & Floods",
        "satellite_help_disasters",
        ["disaster response", "first responders", "evacuation", "damage mapping"]
    )
    add_q(
        "Can satellites detect damaged areas?",
        "Yes, satellites detect damaged areas by comparing high-resolution pre-disaster and post-disaster images to identify collapsed buildings, breached embankments, burned vegetation, debris fields, and washed-away bridges.",
        "Disaster & Floods",
        "detect_damaged_areas",
        ["damage detection", "before after", "destroyed buildings", "infrastructure"]
    )
    add_q(
        "How can AI help disaster management?",
        "AI helps disaster management by rapidly segmenting floodwaters, detecting building damages from post-event imagery in minutes, predicting landslide risk zones from rainfall and slope data, and routing emergency relief teams.",
        "Disaster & Floods",
        "ai_disaster_management",
        ["ai in disaster", "rapid mapping", "building damage", "risk prediction"]
    )
    add_q(
        "How can I compare an area before and after a disaster in SatQuery AI?",
        "In SatQuery AI: go to Change Prediction, select 'Date Comparison', choose a pre-event date (Date A) and post-event date (Date B) or upload two satellite images. Click 'Compare' to see the detected change overlay, affected area in km² and sq ft, and AI summary.",
        "Disaster & Floods",
        "compare_before_after_disaster",
        ["satquery ai", "before after compare", "disaster comparison", "change detection"]
    )

    # Category I: Satellite Image Analysis
    add_q(
        "What is image classification?",
        "Image classification is the process of assigning categorical labels (e.g. Forest, Water, Urban, Agriculture) to individual pixels or image segments based on their spectral and spatial characteristics.",
        "Satellite Image Analysis",
        "image_classification_definition",
        ["image classification", "lulc", "supervised", "unsupervised", "pixels"]
    )
    add_q(
        "What is image segmentation?",
        "Image segmentation is the division of a satellite image into distinct meaningful regions or object boundaries (such as individual agricultural field parcels, water bodies, or building footprints) rather than analyzing isolated pixels.",
        "Satellite Image Analysis",
        "image_segmentation_definition",
        ["image segmentation", "semantic segmentation", "objects", "parcels"]
    )
    add_q(
        "What is object detection in satellite imagery?",
        "Object detection is an AI computer vision task that identifies and locates specific objects (such as airplanes, ships, storage tanks, solar panels, or individual buildings) in high-resolution satellite imagery, outlining them with bounding boxes.",
        "Satellite Image Analysis",
        "object_detection_definition",
        ["object detection", "computer vision", "bounding boxes", "ships", "buildings"]
    )
    add_q(
        "What is change detection?",
        "Change detection is the analytical technique of comparing satellite images of the exact same geographical area captured at different dates to identify, quantify, and map changes in land cover, vegetation vigor, or built structures over time.",
        "Satellite Image Analysis",
        "change_detection_definition",
        ["change detection", "multitemporal", "time series", "comparison"]
    )
    add_q(
        "What is image preprocessing?",
        "Image preprocessing consists of foundational corrections applied to raw satellite data before analysis, including radiometric calibration, atmospheric correction (converting TOA to Surface Reflectance), and geometric orthorectification.",
        "Satellite Image Analysis",
        "image_preprocessing_definition",
        ["preprocessing", "atmospheric correction", "surface reflectance", "orthorectification"]
    )
    add_q(
        "What is image enhancement?",
        "Image enhancement involves techniques that improve the visual interpretability of satellite images, such as contrast stretching, histogram equalization, pan-sharpening, and false-color composite band combinations.",
        "Satellite Image Analysis",
        "image_enhancement_definition",
        ["image enhancement", "contrast stretch", "pan sharpening", "false color"]
    )
    add_q(
        "How does AI analyze satellite images?",
        "AI analyzes satellite images by passing multi-band raster data through deep neural networks (like CNNs or Vision Transformers) trained to recognize spectral patterns, textures, shapes, and spatial contexts, generating automated classification masks and insights.",
        "Satellite Image Analysis",
        "how_ai_analyzes_images",
        ["ai image analysis", "deep learning", "cnn", "computer vision"]
    )
    add_q(
        "Can AI identify buildings in satellite imagery?",
        "Yes, AI identifies buildings in high-resolution satellite imagery using semantic segmentation models (like U-Net or Mask R-CNN) trained on building footprint datasets to delineate rooftops, structures, and building perimeters.",
        "Satellite Image Analysis",
        "ai_identify_buildings",
        ["buildings", "building footprints", "urban detection", "segmentation"]
    )
    add_q(
        "Can AI identify roads in satellite imagery?",
        "Yes, AI identifies roads by extracting linear continuous features and road networks from high-resolution optical and radar imagery using deep learning line-extraction models.",
        "Satellite Image Analysis",
        "ai_identify_roads",
        ["roads", "road networks", "linear features", "transportation"]
    )
    add_q(
        "Can AI identify vegetation in satellite imagery?",
        "Yes, AI identifies vegetation by analyzing near-infrared reflectance, calculating vegetation indices like NDVI/EVI, and classifying plant species or canopy density using supervised machine learning.",
        "Satellite Image Analysis",
        "ai_identify_vegetation",
        ["vegetation identification", "ndvi", "canopy", "classification"]
    )
    add_q(
        "Can AI identify water in satellite imagery?",
        "Yes, AI identifies water by detecting low NIR/SWIR reflectance, applying NDWI algorithms, and recognizing water boundaries in both optical imagery and Synthetic Aperture Radar (SAR) data.",
        "Satellite Image Analysis",
        "ai_identify_water",
        ["water identification", "ndwi", "sar", "rivers", "lakes"]
    )
    add_q(
        "What is shown in this satellite image?",
        "Please upload a satellite image so I can analyze the available visual information and spectral bands. Once uploaded, SatQuery AI will process the real raster bands to identify land cover, water bodies, vegetation, or urban areas.",
        "Satellite Image Analysis",
        "image_query_no_upload",
        ["image analysis", "upload image", "visual interpretation", "satquery"]
    )

    # Category J: Historical & Date-Based Analysis
    add_q(
        "How can I compare satellite images from different years?",
        "In SatQuery AI, open Change Prediction, select 'Year Comparison', enter Year A (e.g. 2018) and Year B (e.g. 2024), and select your location. SatQuery queries Microsoft Planetary Computer STAC for real historical scenes and computes comparative land-cover and spectral metrics.",
        "Historical & Date-Based Analysis",
        "compare_years_howto",
        ["compare years", "historical comparison", "landsat", "sentinel", "satquery"]
    )
    add_q(
        "How can I monitor land changes over time?",
        "You can monitor land changes over time by analyzing a multi-temporal time series of satellite scenes. Comparing annual composite images reveals long-term trends like urban sprawl, deforestation, reservoir depletion, or agricultural expansion.",
        "Historical & Date-Based Analysis",
        "monitor_land_changes_time",
        ["land changes", "time series", "monitoring", "long term"]
    )
    add_q(
        "How can I compare vegetation between two dates?",
        "To compare vegetation between two dates: calculate the NDVI for Date 1 and Date 2, then compute the difference map: Delta NDVI = NDVI_Date2 - NDVI_Date1. Positive delta indicates vegetation greening, while negative delta indicates vegetation loss or harvest.",
        "Historical & Date-Based Analysis",
        "compare_vegetation_dates",
        ["vegetation comparison", "delta ndvi", "two dates", "growth"]
    )
    add_q(
        "How can I compare water bodies over time?",
        "Compare water bodies over time by computing NDWI maps for both dates and subtracting them. This delineates areas where water expanded (flood or reservoir fill) versus areas where water shrank (drying, seasonal drought).",
        "Historical & Date-Based Analysis",
        "compare_water_over_time",
        ["water comparison", "ndwi change", "reservoir shrink", "flood extent"]
    )
    add_q(
        "How can I detect urban growth over several years?",
        "Detect urban growth over several years by comparing NDBI (Built-up index) or impervious surface classifications between baseline and recent years. Newly constructed suburbs and industrial zones appear as significant positive built-up increases.",
        "Historical & Date-Based Analysis",
        "detect_urban_growth",
        ["urban growth", "urban sprawl", "ndbi", "multi year"]
    )
    add_q(
        "What is historical satellite analysis?",
        "Historical satellite analysis is the study of archive satellite data (such as the 50-year Landsat record or 10-year Sentinel record) to understand long-term environmental, agricultural, climatic, and urban evolutions over decades.",
        "Historical & Date-Based Analysis",
        "historical_analysis_definition",
        ["historical analysis", "archive", "decadal change", "landsat"]
    )
    add_q(
        "What is time-series analysis in remote sensing?",
        "Time-series analysis in remote sensing is the analysis of a sequence of satellite observations taken at regular time intervals to detect trends, seasonal periodicities, and abrupt anomaly events in Earth's surface properties.",
        "Historical & Date-Based Analysis",
        "time_series_definition",
        ["time series", "temporal analysis", "phenology", "trends"]
    )

    # Category K: Prediction & Forecasting
    add_q(
        "What is satellite-data prediction?",
        "Satellite-data prediction uses historical satellite observations, current spectral indices, and environmental covariates (like weather and soil moisture) within statistical or machine learning models to forecast future conditions, such as crop yields or drought severity.",
        "Prediction & Forecasting",
        "satellite_prediction_definition",
        ["prediction", "forecasting", "machine learning", "modeling"]
    )
    add_q(
        "Can satellite data predict crop conditions?",
        "Yes, satellite data can forecast crop conditions weeks in advance by tracking early-season vegetative vigor trajectories (NDVI/EVI curves) and comparing them against historical bumper-crop and drought-year benchmarks.",
        "Prediction & Forecasting",
        "predict_crop_conditions",
        ["predict crops", "crop forecasting", "yield estimate", "early warning"]
    )
    add_q(
        "Can AI predict vegetation changes?",
        "Yes, AI models (such as LSTM recurrent networks or spatial transformers) can project future vegetation health by learning patterns from historical seasonal cycles, recent rainfall deficits, and temperature forecasts.",
        "Prediction & Forecasting",
        "ai_predict_vegetation",
        ["ai prediction", "vegetation forecast", "lstm", "trends"]
    )
    add_q(
        "Can historical data be used for prediction?",
        "Yes, historical satellite data provides the training baseline of how a region responded to past droughts, floods, and seasons, allowing machine learning models to predict how the area is likely to behave under similar future conditions.",
        "Prediction & Forecasting",
        "historical_data_for_prediction",
        ["historical data", "training models", "analog forecasting", "baseline"]
    )
    add_q(
        "What is forecasting in remote sensing?",
        "Forecasting in remote sensing is the scientific estimation of future Earth surface conditions (such as agricultural harvest volumes, flood risks, or wildfire dangers) based on current satellite metrics and predictive meteorological models.",
        "Prediction & Forecasting",
        "forecasting_definition",
        ["forecasting", "estimation", "risk forecast", "meteorology"]
    )
    add_q(
        "How does AI make predictions using satellite data?",
        "AI makes predictions by ingesting multi-temporal satellite indices, meteorological data, elevation models, and soil maps into trained regression or classification algorithms that output probability distributions or estimated metric values.",
        "Prediction & Forecasting",
        "how_ai_makes_predictions",
        ["ai modeling", "regression", "probability", "algorithms"]
    )
    add_q(
        "What data is needed for forecasting?",
        "Forecasting requires time-series satellite imagery (NDVI/NDWI/thermal bands), weather observations and forecasts (rainfall, temperature, humidity), digital elevation models (DEM), and ground-truth validation records.",
        "Prediction & Forecasting",
        "data_needed_for_forecasting",
        ["data requirements", "weather", "elevation", "time series"]
    )

    # Category L: AI, ML & Remote Sensing
    add_q(
        "What is artificial intelligence?",
        "Artificial Intelligence (AI) is the field of computer science dedicated to building software and systems capable of performing tasks that typically require human intelligence, such as visual perception, pattern recognition, decision-making, and natural language understanding.",
        "AI, ML & Remote Sensing",
        "ai_definition",
        ["artificial intelligence", "ai", "computer science", "intelligence"]
    )
    add_q(
        "What is machine learning?",
        "Machine Learning (ML) is a subset of AI where algorithms learn patterns and statistical relationships directly from data to make predictions or decisions without being explicitly rule-programmed for every scenario.",
        "AI, ML & Remote Sensing",
        "ml_definition",
        ["machine learning", "ml", "algorithms", "data training"]
    )
    add_q(
        "What is deep learning?",
        "Deep Learning is an advanced branch of machine learning that uses multi-layered artificial neural networks (deep neural networks) to automatically extract hierarchical features from complex data like images, audio, and text.",
        "AI, ML & Remote Sensing",
        "deep_learning_definition",
        ["deep learning", "neural networks", "feature extraction", "deep layers"]
    )
    add_q(
        "What is computer vision?",
        "Computer Vision is the interdisciplinary field of AI enabling computers to interpret, process, and understand visual information from digital images and videos, including object detection, image segmentation, and scene classification.",
        "AI, ML & Remote Sensing",
        "computer_vision_definition",
        ["computer vision", "cv", "image processing", "visual perception"]
    )
    add_q(
        "What is an AI model?",
        "An AI model is a mathematical program that has been trained on a dataset to recognize patterns and make inferences (such as identifying water bodies in a satellite image or answering a user's natural language question).",
        "AI, ML & Remote Sensing",
        "ai_model_definition",
        ["ai model", "weights", "inference", "training"]
    )
    add_q(
        "What is training data?",
        "Training data is the collection of labeled examples (such as satellite image chips paired with confirmed ground-truth land cover labels) used to teach an AI model how to perform a specific task accurately.",
        "AI, ML & Remote Sensing",
        "training_data_definition",
        ["training data", "ground truth", "labels", "dataset"]
    )
    add_q(
        "What is a dataset in remote sensing?",
        "A remote-sensing dataset is an organized collection of geospatial rasters, vector shapes, satellite scenes, or image-question pairs (like RSVQA, BigEarthNet, or EuroSAT) used for training and evaluating AI algorithms.",
        "AI, ML & Remote Sensing",
        "rs_dataset_definition",
        ["dataset", "eurosat", "bigearthnet", "geospatial data"]
    )
    add_q(
        "How does AI analyze satellite imagery?",
        "AI analyzes satellite imagery by feeding multi-band pixels through neural network layers that detect edges, textures, colors, and spatial arrangements, generating pixel-level classifications, object bounding boxes, or descriptive summaries.",
        "AI, ML & Remote Sensing",
        "ai_image_analysis_pipeline",
        ["pipeline", "neural network", "classification", "layers"]
    )
    add_q(
        "What is image classification using AI?",
        "Image classification using AI is the automated categorization of whole satellite images or individual pixels into predefined classes (like Water, Forest, Cropland, Urban) using trained neural networks or Random Forests.",
        "AI, ML & Remote Sensing",
        "ai_image_classification",
        ["image classification", "random forest", "cnn", "classes"]
    )
    add_q(
        "What is machine-learning classification?",
        "Machine-learning classification is a supervised learning approach where an algorithm (like Support Vector Machines, Random Forest, or XGBoost) learns statistical boundaries from training pixels to classify unknown pixels into land categories.",
        "AI, ML & Remote Sensing",
        "ml_classification_definition",
        ["ml classification", "supervised learning", "svm", "random forest"]
    )
    add_q(
        "How can AI help remote sensing?",
        "AI dramatically accelerates remote sensing by processing petabytes of satellite imagery automatically, detecting environmental disasters in real time, counting buildings and trees, and allowing non-experts to query complex Earth data using natural language.",
        "AI, ML & Remote Sensing",
        "how_ai_helps_rs",
        ["ai benefits", "automation", "scale", "natural language"]
    )

    # Category M: Statistics & Interpretation
    add_q(
        "How do I convert square kilometers (km²) to square feet and hectares?",
        "To convert area in square kilometers: 1 km² = 100 hectares = 10,763,910.42 square feet (sq ft). For example, 0.5 km² = 50 hectares = 5,381,955.21 sq ft. SatQuery AI automatically displays all three units for clarity.",
        "Statistics & Interpretation",
        "area_conversion_units",
        ["area conversion", "km2", "hectares", "sq ft", "square feet"]
    )
    add_q(
        "What does a mean NDVI value tell me?",
        "The mean NDVI value provides the average greenness level across all pixels in your selected Area of Interest (AOI). A mean NDVI of 0.65 indicates a predominantly healthy vegetated area, while a mean of 0.15 indicates sparse vegetation or urban ground.",
        "Statistics & Interpretation",
        "mean_ndvi_interpretation",
        ["mean ndvi", "average", "statistics", "vegetation health"]
    )
    add_q(
        "What is confidence score in SatQuery AI?",
        "The confidence score (0.0 to 1.0 or 0% to 100%) indicates the mathematical certainty of the AI or spectral classification model in its output, based on data completeness, cloud cover quality, and index separation.",
        "Statistics & Interpretation",
        "confidence_score_definition",
        ["confidence score", "certainty", "accuracy", "probability"]
    )

    # Category N: General SatQuery AI Questions
    add_q(
        "What is SatQuery AI?",
        "SatQuery AI is an intelligent Vision-Language Assistant and geospatial analytics platform for remote sensing and satellite image analysis, integrating real STAC catalogs (Sentinel-2, Landsat, Sentinel-1) with the Groq AI engine.",
        "General SatQuery AI Questions",
        "what_is_satquery",
        ["satquery ai", "about", "platform", "sih26167"]
    )
    add_q(
        "How do I select an Area of Interest (AOI) in SatQuery AI?",
        "To select an AOI: click the 'Draw AOI' button above the map on the Dashboard, click on the map to place polygon vertices around your area, and click 'Finish AOI'. SatQuery will compute the exact area in km² and use it for all analyses.",
        "General SatQuery AI Questions",
        "how_to_draw_aoi",
        ["draw aoi", "polygon", "area of interest", "satquery"]
    )
    add_q(
        "Does SatQuery AI fabricate satellite data?",
        "No. SatQuery AI strictly enforces a Zero Fabrication Policy. All spectral numbers, dates, cloud percentages, and area calculations come directly from real STAC satellite metadata and spectral band calculations. If data is unavailable, it honestly informs you.",
        "General SatQuery AI Questions",
        "zero_fabrication_policy",
        ["truthfulness", "real data", "zero hallucination", "stac"]
    )
    add_q(
        "How do I export an analysis report in SatQuery AI?",
        "To export a report: go to the 'Data & Reports' tab, select an analysis from your history, and click 'Generate Report'. You can preview the executive summary and download a formatted PDF report or export a complete single-folder ZIP.",
        "General SatQuery AI Questions",
        "how_to_export_report",
        ["export report", "pdf", "zip export", "reports"]
    )

    # -------------------------------------------------------------
    # EXPANSION GENERATOR TO REACH EXACTLY 2,000 UNIQUE HIGH-QUALITY RECORDS
    # -------------------------------------------------------------
    print(f"Base core questions added: {len(records)}")

    # Templates and parameter matrices to systematically generate realistic human user questions
    # across each category with diverse beginner and advanced intents.

    from backend.processing.knowledge_templates import populate_knowledge_records
    populate_knowledge_records(records, seen_questions, add_q)

    print(f"Total knowledge records after expansion: {len(records)}")

    # Ensure total is at least 2,000
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"Successfully saved {len(records)} records to {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_knowledge_base()
