from typing import List, Dict, Any, Optional, Union, Tuple, Literal
from pydantic import BaseModel
import re
import logging
import json
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Geometry(BaseModel):
    type: str
    coordinates: List[List[float]]

class OSMProperties(BaseModel):
    id: str
    name: str
    highway: str
    bicycle: Optional[str] = None
    
    # Optional fields that might be present in the data
    width: Optional[float] = None
    maxspeed: Optional[float] = None
    surface: Optional[str] = None
    smoothness: Optional[str] = None
    oneway: Optional[str] = None
    lit: Optional[str] = None
    
    # Allow for any additional properties that might be in the data
    class Config:
        extra = "allow"
    
    @classmethod
    def from_geojson(cls, data: Dict[str, Any]) -> 'OSMProperties':
        # No need to copy the data since we're not modifying the original dictionary
        processed_data = data
        
        # Handle missing highway field
        if "highway" not in processed_data:
            logger.warning(f"Missing highway field in feature with id: {processed_data.get('id', 'unknown')}")
            processed_data = dict(processed_data)  # Only create a copy if we need to modify
            processed_data["highway"] = "unknown"
            
        # Handle width field with units or text descriptions
        if "width" in processed_data and processed_data["width"] is not None:
            width_str = str(processed_data["width"])
            # Try to extract numeric part (e.g., "6.5 m" -> 6.5)
            match = re.match(r"(\d+\.?\d*)", width_str)
            if match:
                processed_data["width"] = float(match.group(1))
            else:
                logger.warning(f"Could not parse width value: {width_str}")
                processed_data["width"] = None
                
        # Handle maxspeed field
        if "maxspeed" in processed_data and processed_data["maxspeed"] is not None:
            maxspeed_str = str(processed_data["maxspeed"]).lower()
            
            # Handle special cases
            if maxspeed_str in ["none", "no", "walk"]:
                processed_data["maxspeed"] = None
            elif maxspeed_str == "de:rural":
                processed_data["maxspeed"] = 50.0  # DE:rural is 50km/h
            elif ";" in maxspeed_str or "," in maxspeed_str:
                # Take first value when multiple speeds are provided
                first_value = re.split(r"[;,]", maxspeed_str)[0]
                try:
                    processed_data["maxspeed"] = float(first_value)
                except ValueError:
                    logger.warning(f"Could not parse first maxspeed value: {first_value}")
                    processed_data["maxspeed"] = None
            else:
                # Try to extract numeric part
                match = re.match(r"(\d+\.?\d*)", maxspeed_str)
                if match:
                    processed_data["maxspeed"] = float(match.group(1))
                else:
                    logger.warning(f"Could not parse maxspeed value: {maxspeed_str}")
                    processed_data["maxspeed"] = None
                    
        return cls.model_validate(processed_data)

class OSMFeature(BaseModel):
    type: Literal["Feature"]
    properties: OSMProperties
    geometry: Geometry
    
    @classmethod
    def from_geojson(cls, data: Dict[str, Any]) -> 'OSMFeature':
        # No need to copy since we're not modifying the original
        return cls.model_validate({
            "type": data["type"],
            "properties": OSMProperties.from_geojson(data["properties"]),
            "geometry": data["geometry"]
        })
    
class ProcessedProperties(BaseModel):
    # Required fields
    id: str
    name: str
    way_type: Optional[str] = None
    index: Optional[int] = None
    index_10: Optional[int] = None
    stress_level: Optional[int] = None
    
    # Optional fields that might be null
    offset: Optional[float] = None
    side: Optional[str] = None
    
    # Processed fields
    proc_width: Optional[float] = None
    proc_surface: Optional[str] = None
    proc_smoothness: Optional[str] = None
    proc_oneway: Optional[str] = None
    proc_sidepath: Optional[str] = None
    proc_highway: Optional[str] = None
    proc_maxspeed: Optional[int] = None
    proc_traffic_mode_left: Optional[str] = None
    proc_traffic_mode_right: Optional[str] = None
    proc_separation_left: Optional[str] = None
    proc_separation_right: Optional[str] = None
    proc_buffer_left: Optional[float] = None
    proc_buffer_right: Optional[float] = None
    proc_mandatory: Optional[str] = None
    proc_traffic_sign: Optional[str] = None
    
    # Factor fields
    fac_width: Optional[float] = None
    fac_surface: Optional[float] = None
    fac_smoothness: Optional[float] = None
    fac_highway: Optional[float] = None
    fac_maxspeed: Optional[float] = None
    base_index: Optional[int] = None
    fac_1: Optional[float] = None
    fac_2: Optional[float] = None
    fac_3: Optional[float] = None
    fac_4: Optional[float] = None
    
    # Data quality fields
    data_bonus: Optional[str] = None
    data_malus: Optional[str] = None
    data_incompleteness: Optional[float] = None
    data_missing: Optional[str] = None
    
    # Filter fields
    filter_usable: Optional[int] = None
    filter_way_type: Optional[str] = None
    
    # Allow for any additional properties that might be in the data
    class Config:
        extra = "allow"
        
    @classmethod
    def from_geojson(cls, data: Dict[str, Any]) -> 'ProcessedProperties':
        processed_data = data.copy()
        
        # Handle numeric fields that might be None
        numeric_fields = [
            "fac_width", "fac_surface", "fac_highway", "fac_maxspeed",
            "fac_1", "fac_2", "fac_3", "fac_4", "data_incompleteness"
        ]
        
        for field in numeric_fields:
            if field in processed_data and processed_data.get(field) is None:
                logger.warning(f"Field {field} is None in feature with id: {processed_data.get('id', 'unknown')}. Setting to 0.")
                processed_data[field] = 0.0
                
        # Handle integer fields that might be None
        int_fields = ["base_index", "index", "index_10", "stress_level", "filter_usable"]
        for field in int_fields:
            if field in processed_data and processed_data.get(field) is None:
                logger.warning(f"Field {field} is None in feature with id: {processed_data.get('id', 'unknown')}. Setting to 0.")
                processed_data[field] = 0
                
        # Handle string fields that might be None
        return cls.model_validate(processed_data)
    
    @classmethod
    def from_osm_properties(cls, properties: OSMProperties) -> 'ProcessedProperties':
        return cls.from_geojson(properties.model_dump())

class ProcessedFeature(BaseModel):
    type: Literal["Feature"]
    properties: ProcessedProperties
    geometry: Geometry
    
    @classmethod
    def from_geojson(cls, data: Dict[str, Any]) -> 'ProcessedFeature':
        # For processed features, we assume the data is already in the correct format
        return cls.model_validate({
            "type": data["type"],
            "properties": ProcessedProperties.from_geojson(data["properties"]),
            "geometry": data["geometry"]
        })


class OSMFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"]
    name: Optional[str] = None
    crs: Optional[Dict[str, Any]] = None
    features: List[OSMFeature]
    
    @classmethod
    def from_geojson(cls, data: Dict[str, Any]) -> 'OSMFeatureCollection':
        processed_data = data.copy()
        processed_data["features"] = [OSMFeature.from_geojson(feature) for feature in data["features"]]
        return cls.model_validate(processed_data)


class ProcessedFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"]
    name: Optional[str] = None
    crs: Optional[Dict[str, Any]] = None
    features: List[ProcessedFeature]
    
    @classmethod
    def from_geojson(cls, data: Dict[str, Any]) -> 'ProcessedFeatureCollection':
        processed_data = data.copy()
        processed_data["features"] = [ProcessedFeature.from_geojson(feature) for feature in data["features"]]
        return cls.model_validate(processed_data)


class FeatureCollection(BaseModel):
    """A class that can represent either an OSM or processed feature collection"""
    type: Literal["FeatureCollection"]
    name: Optional[str] = None
    crs: Optional[Dict[str, Any]] = None
    features: List[Union[OSMFeature, ProcessedFeature]]
    
    @classmethod
    def from_geojson(cls, data: Dict[str, Any]) -> Union['OSMFeatureCollection', 'ProcessedFeatureCollection']:
        """Parse GeoJSON data with custom handling for edge cases"""
        if "features" in data and len(data["features"]) > 0:
            # Check the first feature to determine the type
            first_feature = data["features"][0]
            if "properties" in first_feature and "way_type" in first_feature["properties"]:
                return ProcessedFeatureCollection.from_geojson(data)
            else:
                return OSMFeatureCollection.from_geojson(data)
        # Default to OSM if we can't determine
        return OSMFeatureCollection.from_geojson(data)
    
    @classmethod
    def from_file(cls, file_path: Union[str, Path]) -> Union['OSMFeatureCollection', 'ProcessedFeatureCollection']:
        """Load GeoJSON from a file and parse it with custom handling"""
        with open(file_path, 'r') as f:
            data = json.load(f)
        return cls.from_geojson(data)


class MatchedFeature(BaseModel):
    """A class that holds both the original OSM feature and its processed counterpart"""
    id: str
    name: str
    osm_feature: OSMFeature
    processed_feature: Optional[ProcessedFeature] = None
    new_processed_feature: Optional[ProcessedFeature] = None