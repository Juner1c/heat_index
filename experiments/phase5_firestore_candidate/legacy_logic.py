"""Copied original class and scientific functions; boundary defects deliberately retained."""
import torch
from torch import nn
from ncps.torch import CfC

class HeatIndexLNN(nn.Module):
    def __init__(self, input_size, hidden_units):
        super().__init__()
        self.lnn = CfC(input_size, hidden_units, batch_first=True)
        self.fc = nn.Linear(hidden_units, 1)
        
    def forward(self, x):
        out, _ = self.lnn(x)
        return self.fc(out[:, -1, :])


def calculate_heat_index(temp_c, rh):
    T = temp_c * 1.8 + 32
    hi = 0.5 * (T + 61.0 + ((T - 68.0) * 1.2) + (rh * 0.094))
    if hi >= 80:
        hi = (-42.379 + 2.04901523 * T + 10.14333127 * rh - 0.22475541 * T * rh 
              - 0.00683783 * T**2 - 0.05481717 * rh**2 + 0.00122874 * (T**2) * rh 
              + 0.00085282 * T * (rh**2) - 0.00000199 * (T**2) * (rh**2))
    return (hi - 32) / 1.8

def get_pagasa_advisory(hi_val):
    if hi_val < 27:
        return "NOT HAZARDOUS", "Conditions normal. Stay hydrated.", "#28a745"
    elif 27 <= hi_val <= 32:
        return "CAUTION", "Fatigue possible with prolonged exposure.", "#ffc107"
    elif 33 <= hi_val <= 41:
        return "EXTREME CAUTION", "Heat cramps and heat exhaustion possible.", "#fd7e14"
    elif 42 <= hi_val <= 51:
        return "DANGER", "Heat stroke likely with continued activity.", "#dc3545"
    else:
        return "EXTREME DANGER", "Heat stroke highly imminent!", "#721c24"
