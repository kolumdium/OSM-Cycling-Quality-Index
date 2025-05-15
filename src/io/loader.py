import json
from typing import List, Dict, Optional, Tuple
from src.models.features import (
    OSMFeature, ProcessedFeature, FeatureCollection, 
    MatchedFeature, OSMFeatureCollection, ProcessedFeatureCollection
)

def parse_geojson(file_path: str) -> FeatureCollection:
    """Parse a GeoJSON file into a FeatureCollection"""
    # Use the from_file method which handles custom parsing
    return FeatureCollection.from_file(file_path)

def parse_osm_data(file_path: str) -> List[OSMFeature]:
    """Parse OSM data from a GeoJSON file"""
    collection = parse_geojson(file_path)
    if isinstance(collection, OSMFeatureCollection):
        return collection.features
    return []

def parse_processed_data(file_path: str) -> List[ProcessedFeature]:
    """Parse processed data from a GeoJSON file"""
    collection = parse_geojson(file_path)
    if isinstance(collection, ProcessedFeatureCollection):
        return collection.features
    return []

def match_features(osm_features: List[OSMFeature], 
                  processed_features: List[ProcessedFeature]) -> Tuple[Dict[str, MatchedFeature], List[OSMFeature], List[ProcessedFeature]]:
    """
    Match OSM features with their processed counterparts by ID
    
    Returns:
        Tuple containing:
        - Dictionary of matched features
        - List of unmatched OSM features
        - List of unmatched processed features
    """
    # Create a dictionary of processed features keyed by ID for quick lookup
    processed_dict = {feature.properties.id: feature for feature in processed_features}
    processed_ids = set(processed_dict.keys())
    
    # Create matched features
    matched_features = {}
    matched_ids = set()
    
    for osm_feature in osm_features:
        feature_id = osm_feature.properties.id
        processed_feature = processed_dict.get(feature_id)
        
        matched_feature = MatchedFeature(
            id=feature_id,
            name=osm_feature.properties.name,
            osm_feature=osm_feature,
            processed_feature=processed_feature
        )
        matched_features[feature_id] = matched_feature
        
        if processed_feature:
            matched_ids.add(feature_id)
    
    # Find unmatched features
    unmatched_osm = [f for f in osm_features if f.properties.id not in matched_ids]
    unmatched_processed = [f for f in processed_features if f.properties.id not in matched_ids]
    
    return matched_features, unmatched_osm, unmatched_processed

def load_and_match_features(osm_file_path: str, processed_file_path: str) -> Tuple[Dict[str, MatchedFeature], List[OSMFeature], List[ProcessedFeature]]:
    """
    Load both OSM and processed data and match features by ID
    
    Returns:
        Tuple containing:
        - Dictionary of matched features
        - List of unmatched OSM features
        - List of unmatched processed features
    """
    osm_features = parse_osm_data(osm_file_path)
    processed_features = parse_processed_data(processed_file_path)
    return match_features(osm_features, processed_features) 