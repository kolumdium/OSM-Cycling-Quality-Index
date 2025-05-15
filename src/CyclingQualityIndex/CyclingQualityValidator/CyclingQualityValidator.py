from src.models.features import ProcessedFeature


class CyclingQualityValidator:
    
    def __init__(self):
        pass
    
    def validate(self, feature: ProcessedFeature, new_feature: ProcessedFeature):
        return False, {}