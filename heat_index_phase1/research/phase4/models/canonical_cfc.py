from ncps.torch import CfC
from torch import nn


class CanonicalCfC(nn.Module):
    """Optional ncps closed-form continuous-time model; no custom-cell relabeling.

    Paper: https://arxiv.org/abs/2106.13898
    """
    def __init__(self, input_size: int, hidden_size: int):
        super().__init__()
        self.recurrent = CfC(input_size=input_size, units=hidden_size, return_sequences=False,
                             batch_first=True, mixed_memory=False, backbone_units=hidden_size,
                             backbone_layers=1, backbone_dropout=0.0)
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, values):
        encoded, _ = self.recurrent(values)
        return self.head(encoded).squeeze(-1)
