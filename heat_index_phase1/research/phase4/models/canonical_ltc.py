from ncps.torch import LTC
from torch import nn


class CanonicalLTC(nn.Module):
    """ncps fully connected LTC, not the original custom time-constant cell.

    Integer units selects fully-connected wiring. Default hidden state is zero
    for each independent sequence; one numerical time unit represents one hour.
    Source: https://ncps.readthedocs.io/en/latest/_modules/ncps/torch/ltc.html
    Paper: https://arxiv.org/abs/2006.04439
    """
    def __init__(self, input_size: int, hidden_size: int, ode_unfolds: int = 6):
        super().__init__()
        self.recurrent = LTC(input_size=input_size, units=hidden_size, return_sequences=False,
                             batch_first=True, mixed_memory=False, ode_unfolds=ode_unfolds)
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, values):
        encoded, _ = self.recurrent(values)
        return self.head(encoded).squeeze(-1)
