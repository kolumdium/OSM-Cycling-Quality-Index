from src.models.features import OSMFeature
from src.CyclingQualityIndex.TagEvaluator.TagEvaluator import TagEvaluator

class WidthEvaluator(TagEvaluator):
    
    name = "width"
    
    def __init__(self, config_path: str):
        super().__init__(config_path)
    
    def calculate_part_index(self, feature: OSMFeature):
        return 0