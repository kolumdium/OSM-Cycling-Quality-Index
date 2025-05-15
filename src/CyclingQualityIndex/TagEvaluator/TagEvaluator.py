from src.models.features import OSMFeature


class TagEvaluator:
    
    config_path: str
    
    def __init__(self, config_path: str):
        self.config_path = config_path
    
    def calculate_part_index(self, feature: OSMFeature) -> float:
        return 0