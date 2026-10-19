"""Original CfC calculation, isolated from storage and never randomly activated."""
import math
from pathlib import Path


class ForecastEngine:
    def __init__(self,path: Path,loader=None):
        self.path=Path(path)
        self.loader=loader
        self.model=None
        self.attempted=False
        self.history=[]

    def load(self):
        if self.attempted: return
        self.attempted=True
        try:
            import torch
            from legacy_logic import HeatIndexLNN
            torch.set_num_threads(1)
            candidate=HeatIndexLNN(input_size=3,hidden_units=32)
            weights=self.loader(self.path) if self.loader else torch.load(self.path,map_location="cpu",weights_only=True)
            candidate.load_state_dict(weights,strict=True)
            if not all(torch.isfinite(value).all() for value in candidate.state_dict().values()):
                raise ValueError("Non-finite weights.")
            candidate.eval()
            self.model=candidate  # publish only after every load check succeeds
        except Exception:
            self.model=None

    def preview(self,temp,humidity):
        import torch
        from legacy_logic import calculate_heat_index
        current=calculate_heat_index(temp,humidity)
        sample=[temp,humidity,current]
        history=(self.history+[sample])[-24:]
        padded=history.copy()
        while len(padded)<24:
            padded.insert(0,sample)
        self.load()
        prediction=None
        if self.model is not None:
            try:
                with torch.inference_mode():
                    raw=self.model(torch.tensor([padded],dtype=torch.float32)).item()
                value=current+raw*.2
                prediction=value if math.isfinite(value) else None
            except Exception:
                prediction=None
        return current,prediction,sample

    def commit(self,sample):
        self.history=(self.history+[sample])[-24:]
