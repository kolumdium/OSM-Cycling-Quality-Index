from src.CyclingQualityIndex import CyclingQualityIndex
from src.io.loader import load_and_match_features
from src.utils.log_utils import logger
from src.CyclingQualityIndex.CyclingQualityValidator import CyclingQualityValidator

def test_import():
    # Example usage
    matched_features, unmatched_osm, unmatched_processed = load_and_match_features(
        "data/test_ways/test_ways.geojson", 
        "data/test_ways/test_ways_alex.geojson"
    )
    
    # Print some statistics
    total_features = len(matched_features)
    matched_count = sum(1 for f in matched_features.values() if f.processed_feature is not None)
    
    logger.info(f"Total features: {total_features}")
    logger.info(f"Matched features: {matched_count}")
    logger.info(f"Unmatched features: {total_features - matched_count}")
    
    # Print unmatched features information
    print(f"\nUnmatched OSM features: {len(unmatched_osm)}")
    for feature in unmatched_osm[:5]:  # Show first 5 only to avoid clutter
        logger.info(f"  - ID: {feature.properties.id}, Name: {feature.properties.name}")
    if len(unmatched_osm) > 5:
        logger.info(f"  ... and {len(unmatched_osm) - 5} more")
        
    logger.info(f"\nUnmatched processed features: {len(unmatched_processed)}")
    for feature in unmatched_processed[:5]:  # Show first 5 only to avoid clutter
        logger.info(f"  - ID: {feature.properties.id}")
    if len(unmatched_processed) > 5:
        logger.info(f"  ... and {len(unmatched_processed) - 5} more")
    
    # Example: Print details of a specific feature
    if "fw01_yes" in matched_features:
        feature = matched_features["fw01_yes"]
        logger.info(f"\nFeature ID: {feature.id}")
        logger.info(f"Name: {feature.name}")
        logger.info(f"OSM Highway: {feature.osm_feature.properties.highway}")
        logger.info(f"OSM Bicycle: {feature.osm_feature.properties.bicycle}")
        
        if feature.processed_feature:
            logger.info(f"Processed Way Type: {feature.processed_feature.properties.way_type}")
            logger.info(f"Processed Index: {feature.processed_feature.properties.index}")
            logger.info(f"Stress Level: {feature.processed_feature.properties.stress_level}")

def test_cycling_quality_validator():
    matched_features, unmatched_osm, unmatched_processed = load_and_match_features(
        "data/test_ways/test_ways.geojson", 
        "data/test_ways/test_ways_alex.geojson"
    )
    
    cycling_quality_index = CyclingQualityIndex.CyclingQualityIndex()
    cycling_quality_validator = CyclingQualityValidator.CyclingQualityValidator()
    
    first_feature = list(matched_features.values())[0]
    first_raw_feature = first_feature.osm_feature
    first_processed_feature = first_feature.processed_feature
    
    results = {}
    
    for feature in matched_features.values():
        new_processed_feature = cycling_quality_index.calculate_index(feature.osm_feature)
        feature.new_processed_feature = new_processed_feature
        valid, validation_mismatches = cycling_quality_validator.validate(feature.processed_feature, feature.new_processed_feature)
        result = {
            "id": feature.id,
            "valid": valid,
            "validation_mismatches": validation_mismatches
        }
        results[feature.id] = result
    
    # Number of valid features
    valid_count = sum(1 for result in results.values() if result["valid"])
    logger.info(f"Number of valid features: {valid_count}")

if __name__ == "__main__":
    test_cycling_quality_validator()