from src.CyclingQualityIndex.TagEvaluator.TagEvaluator import TagEvaluator
from src.models.features import OSMFeature

class SmoothnessEvaluator(TagEvaluator):

    name = "smoothness"
    
    def __init__(self, config_path: str):
        super().__init__(config_path)
    
    def calculate_part_index(self, feature: OSMFeature) -> float:
        return 0
    