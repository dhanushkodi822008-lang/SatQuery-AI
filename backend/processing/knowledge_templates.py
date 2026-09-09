"""
Comprehensive generator templates and real-world Q&A dataset builder
to produce 2,000 unique remote-sensing questions across 14 categories.
"""
from typing import Callable, List, Set, Dict, Any

def populate_knowledge_records(
    records: List[Dict[str, Any]],
    seen_questions: Set[str],
    add_q: Callable[[str, str, str, str, List[str], bool], bool]
):
    # -------------------------------------------------------------
    # 1. Very Basic Satellite & Remote Sensing (~300 target)
    # -------------------------------------------------------------
    sensors_missions = [
        ("Sentinel-2A", "Optical satellite launched by ESA in 2015 carrying the MSI (Multi-Spectral Instrument) with 13 bands from visible to SWIR.", "10m to 60m spatial resolution and high radiometric accuracy for land monitoring."),
        ("Sentinel-2B", "Twin satellite to Sentinel-2A launched by ESA in 2017, operating in the same orbit 180 degrees apart.", "Together with 2A, it achieves a rapid 5-day global revisit time."),
        ("Sentinel-1A", "C-band Synthetic Aperture Radar (SAR) satellite launched by ESA.", "Provides all-weather, day-and-night radar imaging capable of seeing through cloud cover and smoke."),
        ("Sentinel-1B", "Twin SAR satellite in the Copernicus constellation.", "Complements Sentinel-1A for interferometric SAR, flood mapping, and ground deformation."),
        ("Sentinel-3", "Copernicus mission measuring sea surface topography, sea and land surface temperature, and ocean color.", "Carries instruments like OLCI and SLSTR for broad environmental monitoring."),
        ("Sentinel-5P", "Copernicus atmospheric monitoring satellite carrying the TROPOMI spectrometer.", "Maps air pollutants including nitrogen dioxide (NO2), ozone, methane, formaldehyde, and carbon monoxide."),
        ("Landsat 8", "NASA/USGS Earth observation satellite launched in 2013 carrying the OLI (Operational Land Imager) and TIRS (Thermal Infrared Sensor).", "Provides 30m multispectral and 100m thermal data."),
        ("Landsat 9", "Modernized replacement for Landsat 7 launched in 2021 by NASA/USGS.", "Carries OLI-2 and TIRS-2 with improved 14-bit radiometric resolution."),
        ("Landsat 7", "Historic Landsat mission launched in 1999 carrying the ETM+ sensor.", "Famous for 30m multispectral data and 15m panchromatic sharpening, though impacted by the 2003 SLC-off anomaly."),
        ("Landsat 5", "Record-holding satellite operating from 1984 to 2013 with the TM (Thematic Mapper) sensor.", "Delivered nearly 30 years of continuous 30m historical Earth imagery."),
        ("MODIS", "Moderate Resolution Imaging Spectroradiometer aboard NASA's Terra and Aqua satellites.", "Provides daily global coverage in 36 spectral bands at 250m, 500m, and 1000m resolutions."),
        ("PROBA-V", "Miniaturized ESA satellite tracking global vegetation dynamics at 100m and 300m resolutions.", "Bridged the gap between SPOT-Vegetation and Sentinel-3."),
        ("Cartosat-1", "Indian stereoscopic Earth observation satellite launched by ISRO.", "Provides high-resolution stereo pairs for generating digital elevation models (DEM)."),
        ("Cartosat-2", "High-resolution optical satellite series by ISRO with sub-meter panchromatic imaging.", "Used for urban cartography, infrastructure planning, and coastal monitoring."),
        ("Resourcesat-2", "ISRO satellite carrying LISS-4, LISS-3, and AWiFS sensors.", "Provides multi-resolution optical imagery for Indian agricultural and natural resource management."),
        ("RISAT-1", "Active C-band Synthetic Aperture Radar satellite built by ISRO.", "Designed for all-weather flood mapping, rice crop acreage estimation, and forestry in monsoon conditions."),
        ("Oceansat-2", "ISRO satellite carrying an Ocean Colour Monitor (OCM) and scatterometer.", "Monitors chlorophyll concentrations, phytoplankton blooms, and sea surface winds."),
        ("PlanetScope", "Commercial satellite constellation of over 200 CubeSats by Planet Labs.", "Captures daily 3-meter to 4-meter spatial resolution imagery across the entire terrestrial Earth."),
        ("WorldView-3", "Ultra-high-resolution commercial satellite by Maxar.", "Delivers 31 cm panchromatic, 1.24 m multispectral, and 3.7 m shortwave infrared (SWIR) imagery."),
        ("SPOT-6/7", "High-resolution optical satellite constellation operated by Airbus.", "Provides 1.5 m panchromatic and 6 m multispectral imagery for large-area mapping.")
    ]

    for name, desc, detail in sensors_missions:
        add_q(
            f"What is {name}?",
            f"{name} is a {desc} {detail}",
            "Satellite Basics",
            "satellite_mission_info",
            [name.lower(), "satellite", "sensor", "remote sensing"],
            is_beginner=True
        )
        add_q(
            f"How does {name} collect satellite imagery?",
            f"{name} captures Earth observation data by recording reflected or emitted radiation across specific spectral bands. {desc} {detail}",
            "Satellite Basics",
            "satellite_collection_mechanism",
            [name.lower(), "imagery capture", "bands", "remote sensing"],
            is_beginner=True
        )
        add_q(
            f"What is the main purpose of {name}?",
            f"The primary purpose of {name} is Earth observation and environmental surveillance. {detail}",
            "Satellite Basics",
            "satellite_mission_purpose",
            [name.lower(), "purpose", "applications", "earth observation"],
            is_beginner=True
        )

    basic_concepts = [
        ("electromagnetic spectrum", "The entire range of all types of electromagnetic radiation, from gamma rays and X-rays to ultraviolet, visible light, infrared, microwaves, and radio waves. Remote sensing uses visible, infrared, and microwave bands.", "Understanding the spectrum helps scientists choose the right bands to identify water, vegetation, minerals, and urban materials."),
        ("passive sensor", "A remote-sensing instrument that detects natural energy (sunlight or heat) reflected or emitted by Earth's surface without generating its own radiation.", "Examples include optical satellite cameras on Sentinel-2 and Landsat."),
        ("active sensor", "A remote-sensing instrument that emits its own energy pulses toward Earth and measures the radiation backscattered to the sensor.", "Examples include Synthetic Aperture Radar (SAR) on Sentinel-1 and LiDAR altimeters."),
        ("swath width", "The width of the strip of Earth's surface imaged by a satellite sensor during a single orbital pass.", "A wider swath provides faster global revisit, while a narrower swath often yields higher spatial resolution."),
        ("radiometric resolution", "The sensor's sensitivity to subtle differences in the magnitude of detected electromagnetic energy, measured in bit depth (e.g. 8-bit = 256 levels, 12-bit = 4096 levels).", "Higher bit depth allows distinguishing subtle differences in crop vigor or water clarity."),
        ("nadir", "The point on Earth's surface directly beneath an orbiting satellite or sensor at any given moment.", "Nadir imagery has the least geometric distortion compared to off-nadir angled views."),
        ("off-nadir angle", "The angle at which a satellite sensor points away from the vertical nadir line to capture targets to the side of its orbital track.", "Off-nadir pointing increases target revisit flexibility but introduces geometric perspective distortion."),
        ("sun-synchronous orbit", "A near-polar orbit in which a satellite passes over any given point on Earth's surface at the same local solar time every day.", "This ensures consistent sun illumination angles for comparing images across dates."),
        ("geostationary orbit", "A circular orbit at an altitude of approximately 35,786 km directly above Earth's equator, where the satellite's orbital period matches Earth's rotation.", "The satellite stays permanently over the same spot, making it ideal for continuous weather tracking (e.g. GOES, INSAT)."),
        ("panchromatic band", "A wide spectral band capturing light across the entire visible spectrum into a single grayscale image, typically at higher spatial resolution than multispectral bands.", "It is often fused with color bands in a process called pan-sharpening."),
        ("hyperspectral imagery", "Satellite or aerial imagery that records hundreds of very narrow, contiguous spectral bands (e.g. 10 nm wide) across the electromagnetic spectrum.", "It produces complete reflectance curves enabling precise mineral and plant chemical identification."),
        ("true color composite", "A satellite image composite created by displaying the Red band through the red channel, Green through green, and Blue through blue.", "It reproduces the scene as it would appear to a human passenger looking from space."),
        ("false color composite", "A satellite image composite where non-visible bands (such as Near-Infrared) are assigned to visible display channels (e.g. NIR to Red, Red to Green, Green to Blue).", "Healthy vegetation appears bright red because leaves reflect NIR radiation very strongly."),
        ("atmospheric correction", "The process of removing atmospheric scattering and absorption effects (from water vapor, aerosols, and dust) to convert raw Top-of-Atmosphere (TOA) radiance into true Bottom-of-Atmosphere (BOA) Surface Reflectance.", "Essential for scientific comparisons of spectral indices over time."),
        ("top of atmosphere reflectance", "The reflectance measured at the satellite sensor before removing atmospheric distortion caused by air molecules, clouds, and aerosols.", "Referred to as Level-1C (L1C) in Sentinel-2 products."),
        ("surface reflectance", "The fraction of incoming solar radiation reflected by Earth's surface after correcting for atmospheric haze, aerosols, and absorption.", "Referred to as Level-2A (L2A) in Sentinel-2 and Collection 2 Level-2 in Landsat."),
        ("cloud masking", "The algorithmic identification and flagging of cloud and cloud-shadow pixels in satellite scenes using quality assessment (QA) bands.", "Ensures calculations like NDVI and NDWI are computed only from clear, unobscured ground pixels."),
        ("STAC catalog", "SpatioTemporal Asset Catalog (STAC), a standardized JSON specification for indexing, describing, and searching geospatial data and satellite scenes across the web.", "SatQuery AI uses STAC to query Microsoft Planetary Computer for Sentinel and Landsat imagery."),
        ("Cloud-Optimized GeoTIFF", "A standard TIFF file format with internal tiling and overviews, allowing HTTP range requests to stream only the needed pixels without downloading gigabyte-sized full satellite scenes.", "Commonly abbreviated as COG, enabling ultra-fast web-based satellite processing."),
        ("digital elevation model", "A 3D digital raster representation of Earth's topographic surface terrain elevations above a vertical datum.", "Abbreviated as DEM, used for terrain slope correction, watershed modeling, and flood simulation.")
    ]

    for concept, defn, extra in basic_concepts:
        add_q(
            f"What is {concept}?",
            f"{concept.capitalize()} is {defn} {extra}",
            "Satellite Basics",
            f"{concept.replace(' ', '_')}_def",
            [concept.lower(), "satellite basics", "remote sensing", "definition"],
            is_beginner=True
        )
        add_q(
            f"Why is {concept} important in remote sensing?",
            f"{concept.capitalize()} is important because {extra} In practical remote sensing, {defn}",
            "Satellite Basics",
            f"{concept.replace(' ', '_')}_importance",
            [concept.lower(), "importance", "remote sensing", "analysis"],
            is_beginner=True
        )
        add_q(
            f"How does {concept} affect satellite image analysis?",
            f"{concept.capitalize()} affects satellite image analysis by influencing how data is collected, calibrated, or displayed. {defn} {extra}",
            "Satellite Basics",
            f"{concept.replace(' ', '_')}_impact",
            [concept.lower(), "image analysis", "influence", "satellite data"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 2. GIS, Maps & Coordinates (~200 target)
    # -------------------------------------------------------------
    gis_topics = [
        ("vector data", "Geospatial data represented as discrete geometric primitives: points (locations/trees), lines (roads/rivers), and polygons (field boundaries/lakes) with associated attribute tables.", "Ideal for administrative boundaries and road networks."),
        ("raster data", "Geospatial data stored as a grid matrix of square pixels, where each pixel has a specific row, column, and numeric value representing measured radiation or elevation.", "Ideal for continuous surfaces like satellite imagery and elevation models."),
        ("shapefile", "A legacy geospatial vector data format developed by Esri composed of multiple files (.shp, .shx, .dbf, .prj).", "Widely supported in desktop GIS like QGIS and ArcGIS."),
        ("GeoJSON", "An open, lightweight, human-readable JSON format for encoding geographic data structures including Points, LineStrings, and Polygons with properties.", "Standard format used by Leaflet maps and SatQuery AI for AOI boundaries."),
        ("map projection", "A mathematical transformation used to project the curved 3D surface of Earth onto a flat 2D map surface.", "Every projection introduces some distortion in area, shape, distance, or direction."),
        ("EPSG code", "A standardized numerical identifier for coordinate reference systems established by the European Petroleum Survey Group (e.g. EPSG:4326 for WGS84, EPSG:3857 for Web Mercator).", "Ensures software knows exactly how to position geographic coordinates."),
        ("buffer zone", "A polygon zone of a specified distance drawn around a geographic point, line, or polygon feature (e.g. a 500-meter buffer around a river).", "Used for environmental setback analysis and impact zones."),
        ("spatial overlay", "A GIS operation that combines the geometries and attributes of two or more overlapping map layers (such as intersecting farm parcels with a flood extent mask).", "Fundamental for spatial decision making and risk assessment."),
        ("centroid", "The geometric center or center of mass of a geographic polygon or shape.", "Often used to label polygons or calculate central geographic coordinates."),
        ("geocoding", "The process of converting a human-readable text address or place name (e.g. 'Nandanur, Karur') into precise geographic latitude and longitude coordinates.", "SatQuery AI uses OpenStreetMap Nominatim for geocoding."),
        ("reverse geocoding", "The process of converting geographic latitude and longitude coordinates back into a human-readable place name, city, or address.", "Allows clicking on a map to look up the location name."),
        ("spatial resolution vs map scale", "Spatial resolution refers to the pixel ground size (e.g. 10m), while map scale is the ratio of map distance to ground distance (e.g. 1:50,000).", "Higher resolution allows mapping at larger, more detailed scales."),
        ("attribute table", "A tabular database linked to vector spatial data where each row corresponds to a geographic feature and columns store descriptive properties.", "Allows querying features by non-spatial criteria like crop type or population."),
        ("spatial query", "A database query that filters features based on their spatial location or topological relationship (e.g. 'find all schools within 1 km of a river').", "Powered by spatial databases like PostGIS."),
        ("topography", "The detailed arrangement of the natural and artificial physical features of an area, including elevation, slope, and aspect.", "Determines water runoff flow and agricultural terracing suitability."),
        ("contour line", "An isoline on a map connecting points of equal elevation above a reference datum.", "Close contour lines indicate steep slopes; wide spacing indicates flat plains."),
        ("OpenStreetMap", "A free, collaborative, community-driven editable geographic database of the world providing road, building, and land data.", "Often abbreviated as OSM, used for basemaps and water feature extraction in SatQuery AI."),
        ("Leaflet", "A popular, lightweight open-source JavaScript library for mobile-friendly interactive maps.", "Powers the interactive mapping widgets and AOI drawing tools in SatQuery AI.")
    ]

    for topic, defn, extra in gis_topics:
        add_q(
            f"What is {topic} in GIS?",
            f"{topic.capitalize()} in GIS refers to {defn} {extra}",
            "GIS, Maps & Coordinates",
            f"{topic.replace(' ', '_')}_def",
            [topic.lower(), "gis", "mapping", "coordinates"],
            is_beginner=True
        )
        add_q(
            f"How is {topic} used in map analysis?",
            f"{topic.capitalize()} is used in map analysis because {extra} Specifically, {defn}",
            "GIS, Maps & Coordinates",
            f"{topic.replace(' ', '_')}_usage",
            [topic.lower(), "map analysis", "spatial analysis", "gis"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 3. NDVI & Vegetation (~250 target)
    # -------------------------------------------------------------
    veg_indices = [
        ("NDVI (Normalized Difference Vegetation Index)", "(NIR − Red) / (NIR + Red)", "Ranges from -1 to +1; measures overall green biomass and canopy chlorophyll vigor."),
        ("EVI (Enhanced Vegetation Index)", "2.5 × ((NIR − Red) / (NIR + 6 × Red − 7.5 × Blue + 1))", "Improves sensitivity in high biomass rainforests and reduces atmospheric aerosols."),
        ("SAVI (Soil-Adjusted Vegetation Index)", "((NIR − Red) / (NIR + Red + L)) × (1 + L)", "Uses correction factor L (usually 0.5) to minimize soil brightness background in sparse arid crops."),
        ("NDRE (Normalized Difference Red Edge)", "(NIR − RedEdge) / (NIR + RedEdge)", "Uses the narrow Red Edge band (Sentinel-2 Band 5/6/7) to detect early nitrogen deficiency and dense canopy health before NDVI saturates."),
        ("GNDVI (Green Normalized Difference Vegetation Index)", "(NIR − Green) / (NIR + Green)", "More sensitive to chlorophyll concentration than standard NDVI in mature crops."),
        ("MSAVI (Modified Soil-Adjusted Vegetation Index)", "(2 × NIR + 1 − sqrt((2 × NIR + 1)² − 8 × (NIR − Red))) / 2", "Automates soil background adjustment without needing an empirical L parameter."),
        ("NDMI (Normalized Difference Moisture Index)", "(NIR − SWIR) / (NIR + SWIR)", "Measures water content inside plant canopies and crop drought stress levels."),
        ("NBR (Normalized Burn Ratio)", "(NIR − SWIR2) / (NIR + SWIR2)", "Used to highlight burned areas and estimate wildfire severity.")
    ]

    for idx_name, formula, desc in veg_indices:
        add_q(
            f"What is {idx_name}?",
            f"{idx_name} is a remote-sensing vegetation index. Formula: {formula}. {desc}",
            "NDVI & Vegetation",
            "index_definition",
            [idx_name.lower().split()[0], "formula", "vegetation index", "bands"],
            is_beginner=True
        )
        add_q(
            f"How do I calculate {idx_name} from satellite bands?",
            f"To calculate {idx_name}, use the formula: {formula}. In Sentinel-2 or Landsat imagery, replace the band names with their corresponding reflectance pixel arrays. {desc}",
            "NDVI & Vegetation",
            "index_calculation",
            [idx_name.lower().split()[0], "calculate", "formula", "bands"],
            is_beginner=False
        )
        add_q(
            f"When should I use {idx_name} instead of standard NDVI?",
            f"You should use {idx_name} when {desc} For example, {formula} provides specialized sensitivity that standard NDVI lacks.",
            "NDVI & Vegetation",
            "index_comparison",
            [idx_name.lower().split()[0], "ndvi comparison", "advantages", "applications"],
            is_beginner=False
        )

    ndvi_value_scenarios = [
        (-0.3, "deep clear open water body like an ocean, lake, or deep reservoir, because water absorbs NIR light completely."),
        (-0.05, "shallow turbid water, cloud cover, wet soil, or snow surfaces."),
        (0.05, "bare exposed dry soil, sand dunes, gravel, or asphalt pavement with no living vegetation."),
        (0.18, "sparse dry grassland, desert scrub, or urban residential buildings with scattered small lawns."),
        (0.35, "emerging crops in early vegetative stage, open shrubland, or stressed agricultural fields."),
        (0.52, "moderately dense growing crops, healthy pastures, or open deciduous woodland."),
        (0.72, "dense healthy agricultural crops at peak vegetative growth, productive tea/coffee plantations, or closed canopy forest."),
        (0.88, "ultra-dense rainforest canopy, lush sugarcane at full maturity, or intensive irrigated agriculture with multiple canopy layers.")
    ]

    for val, interpretation in ndvi_value_scenarios:
        add_q(
            f"What does an NDVI value of {val} indicate?",
            f"An NDVI value of {val} typically indicates a {interpretation}",
            "NDVI & Vegetation",
            "ndvi_value_interpretation",
            [f"ndvi {val}", "ndvi value", "interpretation", "vegetation health"],
            is_beginner=True
        )
        add_q(
            f"Is an NDVI of {val} considered healthy vegetation?",
            f"{'Yes, an NDVI of ' + str(val) + ' is considered healthy and dense vegetation.' if val >= 0.5 else 'No, an NDVI of ' + str(val) + ' represents ' + interpretation}",
            "NDVI & Vegetation",
            "ndvi_health_check",
            [f"ndvi {val}", "healthy vegetation", "ndvi assessment"],
            is_beginner=True
        )

    # -------------------------------------------------------------
    # 4. Agriculture & Crops (~250 target)
    # -------------------------------------------------------------
    crops = [
        ("paddy rice", "flooded fields during transplanting (low NDVI, high NDWI), rapid vegetative rise (NDVI > 0.7), and sharp decline during grain maturity and harvest.", "Sentinel-1 SAR radar is ideal for tracking rice because flooded paddies have low radar backscatter."),
        ("wheat", "winter sowing with slow emergence (NDVI 0.2–0.3), peak spring tillering/heading (NDVI 0.75–0.85), and golden drying before harvest (NDVI dropping to 0.2).", "NDRE index helps detect early nitrogen deficiency in wheat."),
        ("cotton", "slow early canopy closure, peak squaring/boll formation in mid-season with moderate-high NDVI (0.65–0.75), and defoliation before harvest.", "Thermal and moisture indices help optimize irrigation timing."),
        ("sugarcane", "long 10–14 month crop cycle with persistent high biomass (NDVI 0.75–0.88) across multiple seasons.", "High biomass causes NDVI saturation, making EVI preferable."),
        ("maize (corn)", "rapid canopy growth reaching peak NDVI (0.80–0.85) at silking/tasseling, highly sensitive to drought stress during pollination.", "Early NDWI drops indicate irrigation deficit before yield loss occurs."),
        ("soybean", "dense green canopy reaching high peak NDVI (0.80+) within 60–75 days after planting, turning yellow/brown at pod maturity.", "Multispectral imagery tracks row spacing and weed competition."),
        ("tea plantations", "perennial evergreen bushes showing stable high NDVI (0.70–0.80) year-round with periodic dips following pruning and plucking rounds.", "Elevation models and slope aspect are key factors in tea quality mapping."),
        ("coffee plantations", "perennial agroforestry systems often grown under shade trees, presenting mixed spectral signatures of trees and coffee shrubs.", "High-resolution imagery separates shade canopy from coffee understory."),
        ("mustard / rapeseed", "vibrant yellow flowering phase that temporarily decreases visible red absorption, followed by green pod filling and dry harvest.", "Spectral yellow band anomalies can detect exact flowering dates.")
    ]

    for crop, pheno, tips in crops:
        add_q(
            f"How can satellite imagery monitor {crop}?",
            f"Satellite imagery monitors {crop} by tracking its unique phenological curve: {pheno} {tips}",
            "Agriculture & Crops",
            f"monitor_{crop.split()[0]}",
            [crop.lower(), "crop monitoring", "agriculture", "ndvi curve"],
            is_beginner=True
        )
        add_q(
            f"What does the NDVI curve of {crop} look like?",
            f"The NDVI curve of {crop} is characterized by {pheno}",
            "Agriculture & Crops",
            f"{crop.split()[0]}_ndvi_curve",
            [crop.lower(), "ndvi curve", "phenology", "growth stages"],
            is_beginner=False
        )
        add_q(
            f"How do I detect stress in {crop} using satellites?",
            f"To detect stress in {crop}, monitor deviations from the expected seasonal NDVI and NDWI baselines. {tips}",
            "Agriculture & Crops",
            f"{crop.split()[0]}_stress_detection",
            [crop.lower(), "crop stress", "irrigation", "yield"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 5. Water & Water Bodies (~150 target)
    # -------------------------------------------------------------
    water_phenomena = [
        ("algal blooms", "Dense proliferation of microscopic algae or cyanobacteria in freshwater or marine environments, producing bright green swirls with elevated NIR reflectance and high chlorophyll-a signals.", "Detected using Cyanobacteria Index (CI) and Sentinel-3 OLCI."),
        ("turbidity and suspended sediment", "Cloudiness of water caused by large numbers of individual particles (silt, clay, organic matter), which increases visible red and green reflectance compared to clear water.", "Calculated using Red/NIR band ratios to monitor reservoir siltation."),
        ("reservoir depletion", "The shrinking of surface water extent in dams and reservoirs caused by prolonged drought, high agricultural withdrawal, or low monsoon inflow.", "Quantified in SatQuery AI by comparing multi-year NDWI water masks and calculating lost water surface area in hectares."),
        ("wetland degradation", "The conversion or drying of natural wetlands due to urban encroachment, drainage, or climate change, marked by loss of permanent water and replacement by invasive dry vegetation.", "Monitored using combined SAR and optical seasonal water frequency maps."),
        ("glacial lake outburst flood (GLOF)", "A sudden release of water from a glacial lake dammed by unstable moraine or ice, posing severe downstream flood hazards in mountainous regions.", "Monitored by tracking glacial lake area expansion over decades using Landsat and Sentinel-2."),
        ("groundwater depletion indicators", "Indirect surface manifestations of falling groundwater tables, such as dying deep-rooted trees, shrinking baseflow in perennial streams, and reduced dry-season crop acreage.", "Can be integrated with GRACE satellite gravity anomalies for regional aquifer tracking.")
    ]

    for phenom, defn, tech in water_phenomena:
        add_q(
            f"What is {phenom} in satellite remote sensing?",
            f"{phenom.capitalize()} refers to {defn} {tech}",
            "Water & Water Bodies",
            f"{phenom.replace(' ', '_')}_def",
            [phenom.lower(), "water bodies", "hydrology", "remote sensing"],
            is_beginner=True
        )
        add_q(
            f"How do satellites detect {phenom}?",
            f"Satellites detect {phenom} because {defn} In practice, {tech}",
            "Water & Water Bodies",
            f"{phenom.replace(' ', '_')}_detection",
            [phenom.lower(), "detection method", "water index", "monitoring"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 6. Land Use & Land Cover (~200 target)
    # -------------------------------------------------------------
    lulc_classes = [
        ("Dense Urban / High Density Built-up", "Continuous commercial and residential buildings with high impervious surface fraction (>80%), asphalt roads, and minimal tree cover.", "Shows high NDBI (>0.1), high surface temperature, and low NDVI (<0.15)."),
        ("Suburban / Low Density Built-up", "Residential neighborhoods with detached houses, gardens, trees, and paved access roads.", "Shows mixed NDBI and moderate NDVI (0.25–0.40)."),
        ("Industrial and Commercial Zones", "Large metal-roofed warehouses, factories, parking lots, and logistics hubs.", "Characterized by very high SWIR and NIR roof reflections and distinct geometric shapes."),
        ("Irrigated Cropland", "Intensively managed agricultural fields receiving canal, groundwater, or sprinkler irrigation.", "Displays prominent seasonal greenness cycles reaching high NDVI (0.70+) even in dry seasons."),
        ("Rainfed Cropland", "Agricultural fields dependent entirely on seasonal monsoon rainfall.", "Shows high NDVI only during monsoon months and bare dry soil during winter/summer."),
        ("Dense Evergreen Forest", "Multi-layered tree canopy that retains green leaves throughout the year (e.g. Western Ghats, rainforests).", "Maintains consistently high NDVI (0.75–0.88) with minimal seasonal fluctuation."),
        ("Deciduous Forest", "Tree stands that shed their leaves during the dry or winter season to conserve water.", "Shows dramatic seasonal shifts from high greenness (monsoon) to low NDVI during leaf-drop."),
        ("Mangrove Forest", "Tolerant halophyte tree communities growing in coastal intertidal saline zones.", "Distinctive low NIR reflectance due to tidal water background combined with high canopy greenness."),
        ("Scrub and Shrubland", "Woody vegetation under 5 meters in height mixed with grasses and exposed rocky soil in semi-arid zones.", "Displays moderate NDVI (0.20–0.40) that surges quickly after sudden rains."),
        ("Barren Land / Bare Rock", "Exposed bedrock, mining quarries, sand dunes, or sterile soil incapable of sustaining vegetation.", "Displays high Red and SWIR reflectance with flat spectral curves and near-zero NDVI.")
    ]

    for cls_name, desc, spectral in lulc_classes:
        add_q(
            f"What is {cls_name} in land-cover maps?",
            f"{cls_name} is a land-cover classification category describing {desc} {spectral}",
            "Land Use & Land Cover",
            "lulc_class_definition",
            [cls_name.lower().split()[0], "land cover", "classification", "lulc"],
            is_beginner=True
        )
        add_q(
            f"How is {cls_name} identified in satellite imagery?",
            f"{cls_name} is identified by its distinctive spectral signature: {spectral} {desc}",
            "Land Use & Land Cover",
            "lulc_class_identification",
            [cls_name.lower().split()[0], "spectral signature", "identification", "indices"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 7. Forest & Environment (~150 target)
    # -------------------------------------------------------------
    env_topics = [
        ("wildfire burn scar", "An area where forest or grassland vegetation has been consumed by fire, leaving blackened charcoal, ash, and exposed soil.", "Mapped using Normalized Burn Ratio (NBR) and delta NBR (dNBR)."),
        ("canopy density", "The percentage of ground area covered by the vertical projection of tree crowns in a forest stand.", "Classified into Very Dense Forest (>70%), Moderately Dense (40–70%), and Open Forest (10–40%)."),
        ("carbon sequestration monitoring", "The estimation of atmospheric carbon dioxide captured and stored in living forest biomass and soils over time.", "Calculated by combining satellite canopy height models (LiDAR/GEDI) with optical vegetation indices."),
        ("illegal logging detection", "The near-real-time identification of unauthorized tree felling, logging roads, and canopy perforations in protected reserves.", "Automated alert systems detect pixel-level drops in optical/SAR reflectance within days."),
        ("urban heat island effect", "The phenomenon where urban metropolitan areas experience significantly warmer temperatures than surrounding rural areas due to concrete, asphalt, and lack of vegetation.", "Measured using satellite thermal infrared sensors (Landsat TIRS, MODIS Land Surface Temperature)."),
        ("mangrove loss", "The destruction of coastal mangrove forests caused by aquaculture pond conversion, coastal development, or sea level rise.", "Monitored using time-series NDVI and water masks along tropical coastlines.")
    ]

    for topic, defn, tech in env_topics:
        add_q(
            f"What is {topic}?",
            f"{topic.capitalize()} refers to {defn} {tech}",
            "Forest & Environment",
            f"{topic.replace(' ', '_')}_def",
            [topic.lower(), "forest", "environment", "monitoring"],
            is_beginner=True
        )
        add_q(
            f"How do satellites track {topic}?",
            f"Satellites track {topic} because {defn} Remote-sensing workflows use {tech}",
            "Forest & Environment",
            f"{topic.replace(' ', '_')}_tracking",
            [topic.lower(), "satellite tracking", "methods", "conservation"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 8. Disaster & Floods (~150 target)
    # -------------------------------------------------------------
    disaster_topics = [
        ("urban flash flood", "Sudden localized flooding in municipal areas caused by extreme rainfall overwhelming storm drainage systems.", "Optical imagery and high-resolution SAR delineate submerged streets and damaged residential zones."),
        ("riverine flood", "Widespread inundation occurring when river discharge exceeds bank capacity, flooding adjacent floodplains for days or weeks.", "Mapped by intersecting pre-flood and post-flood water extents against digital elevation models."),
        ("cyclone damage assessment", "The evaluation of destructive winds, storm surges, and torrential rains following a tropical cyclone.", "Compares pre-storm and post-storm imagery to quantify crop lodging, uprooted trees, and flooded settlements."),
        ("landslide mapping", "The identification of downhill slope failures where rock, debris, or soil has collapsed following heavy rains or earthquakes.", "Appears in satellite imagery as bright linear scars where topsoil and green vegetation have been stripped away."),
        ("drought risk indicator", "A composite score reflecting prolonged moisture deficiency, high temperature anomalies, and declining vegetation vigor.", "SatQuery AI integrates rainfall deficit, weather data, and NDVI anomalies to evaluate drought vulnerability."),
        ("post-disaster recovery tracking", "The long-term monitoring of reconstruction, crop replanting, and infrastructure repair in disaster-hit zones.", "Monitored through multi-month time series tracking vegetation regrowth and building reconstruction.")
    ]

    for topic, defn, tech in disaster_topics:
        add_q(
            f"What is a {topic}?",
            f"A {topic} is {defn} {tech}",
            "Disaster & Floods",
            f"{topic.replace(' ', '_')}_def",
            [topic.lower(), "disaster", "emergency", "flood"],
            is_beginner=True
        )
        add_q(
            f"How does SatQuery AI assist in {topic}?",
            f"SatQuery AI assists in {topic} by querying multi-temporal STAC satellite scenes, calculating affected area in km² and square feet, and providing evidence-based summaries without fabricating unverified numbers.",
            "Disaster & Floods",
            f"{topic.replace(' ', '_')}_satquery",
            [topic.lower(), "satquery ai", "disaster management", "rapid mapping"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 9. Satellite Image Analysis (~150 target)
    # -------------------------------------------------------------
    analysis_techniques = [
        ("pan-sharpening", "Fusing a high-resolution panchromatic (grayscale) band with lower-resolution multispectral color bands to produce a high-resolution color image.", "For example, fusing Landsat 15m panchromatic with 30m multispectral to create a 15m true-color composite."),
        ("band math", "Performing mathematical operations (addition, subtraction, division, ratios) across corresponding pixels in different spectral bands.", "All spectral indices (NDVI, NDWI, NDBI) are created using band math."),
        ("image co-registration", "The precise geometric alignment of two or more satellite images of the same area so that corresponding pixels represent the exact same physical ground location.", "A critical prerequisite for accurate change detection."),
        ("radiometric calibration", "Converting raw digital numbers (DN) recorded by satellite detectors into physical units of spectral radiance or reflectance.", "Ensures consistent measurements across different dates and sensors."),
        ("confusion matrix", "A cross-tabulation table comparing satellite classification results against ground-truth validation points to measure classification accuracy.", "Calculates Producer Accuracy, User Accuracy, Overall Accuracy, and the Kappa Coefficient."),
        ("spectral signature", "The unique pattern of electromagnetic radiation reflected or emitted by a specific material across different wavelengths.", "Like a human fingerprint, it allows algorithms to tell water, healthy crops, asphalt, and dry soil apart.")
    ]

    for tech, defn, extra in analysis_techniques:
        add_q(
            f"What is {tech}?",
            f"{tech.capitalize()} is {defn} {extra}",
            "Satellite Image Analysis",
            f"{tech.replace(' ', '_')}_def",
            [tech.lower(), "image analysis", "remote sensing", "processing"],
            is_beginner=True
        )
        add_q(
            f"How is {tech} performed in satellite image processing?",
            f"{tech.capitalize()} is performed by {defn} In satellite data workflows, {extra}",
            "Satellite Image Analysis",
            f"{tech.replace(' ', '_')}_workflow",
            [tech.lower(), "workflow", "image processing", "steps"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 10. Historical & Date-Based Analysis (~75 target)
    # -------------------------------------------------------------
    hist_topics = [
        ("decadal change detection", "Analyzing satellite imagery over 10, 20, or 30 years to track long-term transformations in land cover, such as forest depletion, urban mega-growth, or coastline retreat.", "Landsat's 50-year archive is the primary global data source."),
        ("seasonal phenological comparison", "Comparing satellite observations of the exact same month across multiple years to detect whether planting seasons or monsoon arrivals are shifting due to climate change.", "Normalizes for seasonal variation to isolate true long-term trends."),
        ("baseline reference image", "A clean, cloud-free satellite image from a known normal or historical period used as a standard benchmark to measure subsequent anomalies.", "Used in SatQuery AI to compare current conditions against past observations."),
        ("trend decomposition", "Separating a satellite time-series signal into long-term secular trend, seasonal cyclical variations, and short-term irregular anomaly spikes.", "Helps distinguish permanent land degradation from temporary seasonal dry spells.")
    ]

    for topic, defn, tech in hist_topics:
        add_q(
            f"What is {topic}?",
            f"{topic.capitalize()} is {defn} {tech}",
            "Historical & Date-Based Analysis",
            f"{topic.replace(' ', '_')}_def",
            [topic.lower(), "historical analysis", "time series", "comparison"],
            is_beginner=True
        )
        add_q(
            f"How do I use {topic} in satellite studies?",
            f"To use {topic} in satellite studies: select multi-temporal scenes from matching seasons across target years, co-register the imagery, compute spectral difference indices, and summarize area changes. {tech}",
            "Historical & Date-Based Analysis",
            f"{topic.replace(' ', '_')}_usage",
            [topic.lower(), "methodology", "historical study", "trends"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 11. Prediction & Forecasting (~75 target)
    # -------------------------------------------------------------
    pred_topics = [
        ("crop yield forecasting", "Estimating total agricultural production (e.g. tons per hectare) weeks before harvest using satellite vegetation trajectories and weather variables.", "Integrates peak NDVI, growing degree days, and soil moisture models."),
        ("drought forecast modeling", "Predicting the onset, severity, and geographical extent of agricultural drought based on precipitation deficits and vegetation stress indicators.", "Provides early warnings to agricultural departments and farmers."),
        ("urban sprawl simulation", "Modeling future urban land expansion using Cellular Automata (CA) or machine learning based on historical growth patterns and road network proximity.", "Informs city planning, infrastructure zoning, and greenbelt protection."),
        ("flood risk forecasting", "Simulating flood inundation probabilities before heavy storms hit by combining weather precipitation forecasts with river basin hydrology and elevation models.", "Enables proactive evacuation planning and emergency reservoir management.")
    ]

    for topic, defn, tech in pred_topics:
        add_q(
            f"What is {topic}?",
            f"{topic.capitalize()} is {defn} {tech}",
            "Prediction & Forecasting",
            f"{topic.replace(' ', '_')}_def",
            [topic.lower(), "prediction", "forecasting", "modeling"],
            is_beginner=True
        )
        add_q(
            f"How reliable is {topic} based on satellite data?",
            f"The reliability of {topic} depends on input data quality, satellite revisit frequency, weather forecast accuracy, and model calibration against historical ground truth. Predictions should always be treated as probabilistic estimates rather than absolute certainty.",
            "Prediction & Forecasting",
            f"{topic.replace(' ', '_')}_reliability",
            [topic.lower(), "reliability", "accuracy", "uncertainty"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 12. AI, ML & Remote Sensing (~100 target)
    # -------------------------------------------------------------
    ai_ml_topics = [
        ("Convolutional Neural Network (CNN)", "A deep learning neural network architecture designed for processing grid-structured data like images by applying spatial convolutional filters to detect hierarchical features.", "Standard architecture for land cover classification and satellite object detection."),
        ("Vision Transformer (ViT)", "A modern neural network architecture that applies self-attention mechanisms to sequence of image patches, capturing long-range spatial relationships across large satellite scenes.", "Shows state-of-the-art performance in Earth observation foundation models."),
        ("U-Net architecture", "An encoder-decoder neural network with skip connections originally developed for biomedical segmentation, widely adopted in remote sensing for pixel-level semantic segmentation of roads, water, and buildings.", "Preserves fine spatial boundary details accurately."),
        ("Random Forest in remote sensing", "An ensemble machine learning algorithm that constructs multiple decision trees during training and outputs the mode class of individual trees.", "Highly effective for multi-spectral land cover classification due to its speed and resistance to overfitting."),
        ("Support Vector Machine (SVM)", "A supervised machine learning algorithm that finds the optimal hyperplane that maximizes the margin between different land cover classes in high-dimensional spectral space.", "Works well even with small amounts of training ground truth data."),
        ("Vision-Language Model (VLM)", "A multimodal AI model that understands both satellite imagery and natural language text queries simultaneously, enabling visual question answering (VQA) and conversational exploration of geospatial data.", "SatQuery AI leverages Groq-hosted VLM technology to explain satellite observations naturally."),
        ("ground truthing", "The process of collecting direct physical field observations and measurements on the ground to train, calibrate, and validate satellite classification models.", "The gold standard for evaluating satellite analysis accuracy.")
    ]

    for topic, defn, tech in ai_ml_topics:
        add_q(
            f"What is {topic} in remote sensing?",
            f"{topic.capitalize()} in remote sensing refers to {defn} {tech}",
            "AI, ML & Remote Sensing",
            f"{topic.replace(' ', '_')}_def",
            [topic.lower(), "ai", "machine learning", "neural network"],
            is_beginner=True
        )
        add_q(
            f"How does {topic} improve satellite data processing?",
            f"{topic.capitalize()} improves satellite data processing because {defn} In operational pipelines, {tech}",
            "AI, ML & Remote Sensing",
            f"{topic.replace(' ', '_')}_benefit",
            [topic.lower(), "benefits", "machine learning", "remote sensing"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 13. Statistics & Interpretation (~50 target)
    # -------------------------------------------------------------
    stat_topics = [
        ("pixel count to area conversion", "The calculation of total physical ground area by multiplying the total count of classified pixels by the square of the spatial resolution (e.g. 1,000 pixels × (10m × 10m) = 100,000 m² = 0.1 km² = 10 hectares).", "Used in SatQuery AI to convert raster classification masks into precise km², hectares, and square feet."),
        ("standard deviation of NDVI", "A statistical measure indicating the variability of vegetation health within an Area of Interest (AOI). A low standard deviation means uniform crop health; a high standard deviation indicates patchy or uneven growth.", "Helps farmers pinpoint variable rate fertilizer needs."),
        ("Kappa coefficient", "A statistical measure used in remote sensing accuracy assessment that measures agreement between classification maps and ground truth while accounting for chance agreement.", "Values > 0.8 indicate strong classification agreement."),
        ("false positive in change detection", "An error where an algorithm incorrectly detects a land change that did not actually occur on the ground, often caused by cloud shadows, seasonal sun angle variations, or registration errors.", "Minimized by rigorous cloud masking and atmospheric correction.")
    ]

    for topic, defn, tech in stat_topics:
        add_q(
            f"What is {topic}?",
            f"{topic.capitalize()} is {defn} {tech}",
            "Statistics & Interpretation",
            f"{topic.replace(' ', '_')}_def",
            [topic.lower(), "statistics", "accuracy", "interpretation"],
            is_beginner=True
        )
        add_q(
            f"Why does {topic} matter when interpreting satellite results?",
            f"{topic.capitalize()} matters because {defn} Understanding this prevents misinterpretation of satellite analytics. {tech}",
            "Statistics & Interpretation",
            f"{topic.replace(' ', '_')}_importance",
            [topic.lower(), "interpretation", "statistics", "reliability"],
            is_beginner=False
        )

    # -------------------------------------------------------------
    # 14. General SatQuery AI Questions (~50 target)
    # -------------------------------------------------------------
    satquery_features = [
        ("Satellite Scene Search", "Search for real optical (Sentinel-2, Landsat) or radar (Sentinel-1) scenes by date, cloud cover threshold, and location via Planetary Computer STAC.", "Displays real acquisition dates, cloud percentages, and sensor metadata."),
        ("Area Overview Dashboard", "Runs simultaneous spectral land-cover evaluations for Water Bodies, Agricultural Land, Built-up Area, and Forest cover.", "Outputs real areas in square feet and km² with overlay maps."),
        ("Change Prediction & Comparison", "Compares satellite imagery between two dates, two years, or two uploaded image files.", "Calculates percentage change, affected area in km² and sq ft, and change classification."),
        ("Monitoring & Automated Alerts", "Allows setting custom notification rules (e.g. water expansion, vegetation drop) with in-app notifications, email, and SMS alerts.", "Continuously evaluates new observations against defined thresholds."),
        ("Multi-source Data Fusion", "Combines satellite multispectral data with Open-Meteo real-time weather observations, Nominatim geocoding, and OpenStreetMap water infrastructure.", "Provides a holistic environmental context for any query."),
        ("Data & Executive Reports", "Generates comprehensive downloadable PDF analysis reports and single-folder ZIP exports containing structured data, metrics, and summaries.", "Formats evidence into professional executive summaries for officers and researchers.")
    ]

    for feat, desc, detail in satquery_features:
        add_q(
            f"How does the {feat} feature work in SatQuery AI?",
            f"The {feat} feature in SatQuery AI allows users to {desc} {detail}",
            "General SatQuery AI Questions",
            f"satquery_{feat.lower().replace(' ', '_')}",
            ["satquery ai", feat.lower(), "feature", "how it works"],
            is_beginner=True
        )
        add_q(
            f"What can I do with {feat} in SatQuery AI?",
            f"With {feat}, you can {desc} It leverages {detail}",
            "General SatQuery AI Questions",
            f"satquery_use_{feat.lower().replace(' ', '_')}",
            ["satquery ai", feat.lower(), "capabilities", "guide"],
            is_beginner=True
        )

    # -------------------------------------------------------------
    # EXPANDING WITH REALISTIC BEGINNER & ADVANCED USER QUESTIONS
    # TO REACH EXACTLY 2,000 UNIQUE RECORDS ACROSS ALL 14 CATEGORIES
    # -------------------------------------------------------------
    from backend.processing.knowledge_expander import expand_all_categories
    expand_all_categories(records, seen_questions, add_q)
