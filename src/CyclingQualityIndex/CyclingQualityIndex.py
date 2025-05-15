from src.CyclingQualityIndex.FeatureEvaluator import FeatureEvaluator
from src.CyclingQualityIndex.SurfaceEvaluator.SurfaceEvaluator import SurfaceEvaluator
from src.CyclingQualityIndex.SmoothnessEvaluator.SmoothnessEvaluator import SmoothnessEvaluator
from src.CyclingQualityIndex.WidthEvaluator.WidthEvaluator import WidthEvaluator
from src.models.features import OSMFeature, ProcessedFeature

class CyclingQualityIndex:
    
    feature_evaluator: FeatureEvaluator.FeatureEvaluator
    
    def __init__(self):
        self.feature_evaluator = FeatureEvaluator.FeatureEvaluator()
        self.add_evaluators({"surface": "CyclingQualityIndex/SurfaceEvaluator/surface_config.yaml",
                             "smoothness": "CyclingQualityIndex/SmoothnessEvaluator/smoothness_config.yaml",
                             "width": "CyclingQualityIndex/WidthEvaluator/width_config.yaml"})

    def add_evaluators(self, config_paths: dict):
        
        config_path_surface = config_paths.get("surface", "CyclingQualityIndex/SurfaceEvaluator/surface_config.yaml")
        config_path_smoothness = config_paths.get("smoothness", "CyclingQualityIndex/SmoothnessEvaluator/smoothness_config.yaml")
        config_path_width = config_paths.get("width", "CyclingQualityIndex/WidthEvaluator/width_config.yaml")
        
        self.feature_evaluator.add_evaluator(SurfaceEvaluator(config_path_surface))
        self.feature_evaluator.add_evaluator(SmoothnessEvaluator(config_path_smoothness))
        self.feature_evaluator.add_evaluator(WidthEvaluator(config_path_width))
    
    def calculate_index(self, feature: OSMFeature) -> ProcessedFeature:
        return self.feature_evaluator.calculate_index(feature)