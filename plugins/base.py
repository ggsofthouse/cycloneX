class BasePlugin:
    def __init__(self, metadata):
        self.metadata = metadata

    def calculate_score(self, start_val, end_val):
        """Retorna uma pontuação de 0.0 a 100.0 para o range informado."""
        raise NotImplementedError
