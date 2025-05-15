from typing import List, Dict
from src.CyclingQualityIndex.TagEvaluator.TagEvaluator import TagEvaluator
from src.models.features import OSMFeature, ProcessedFeature, ProcessedProperties

class FeatureEvaluator:
    
    evaluators: List[TagEvaluator]
    results: Dict[str, float]
    
    def __init__(self):
        self.evaluators = []
        self.results = {}
        
    def add_evaluator(self, evaluator: TagEvaluator):
        self.evaluators.append(evaluator)
    
    def calculate_index(self, feature: OSMFeature) -> ProcessedFeature:
        
        new_processed_properties = ProcessedProperties.from_osm_properties(feature.properties)
        
        # For each Feature calculate the index and add it to the new_processed_feature
        for evaluator in self.evaluators:
            part_index = evaluator.calculate_part_index(feature)
            # Dynamically set the attribute using setattr()
            setattr(new_processed_properties, f"proc_{evaluator.name}", part_index)
        
        return ProcessedFeature(
            type="Feature",
            properties=new_processed_properties,
            geometry=feature.geometry
        )