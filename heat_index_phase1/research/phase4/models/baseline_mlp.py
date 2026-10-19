from torch import nn


class WindowMLP(nn.Module):
    """Flatten the same historical input window provided to the recurrent models."""
    def __init__(self, input_size: int, hidden_size: int, sequence_length: int):
        super().__init__()
        self.network = nn.Sequential(nn.Flatten(), nn.Linear(input_size*sequence_length, hidden_size),
                                     nn.Tanh(), nn.Linear(hidden_size, 1))

    def forward(self, values):
        return self.network(values).squeeze(-1)
