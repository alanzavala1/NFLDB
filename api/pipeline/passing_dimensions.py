"""Passing names for the same verified play-context partitions as receiving."""
from pipeline.receiving_dimensions import DIMENSIONS as RECEIVING_DIMENSIONS
from pipeline.receiving_dimensions import context_split_values as receiving_values


RECEIVING_NAMES = {"pass_depth": "target_depth", "pass_location": "target_direction"}
DIMENSIONS = {next((p for p, r in RECEIVING_NAMES.items() if r == name), name): values
              for name, values in RECEIVING_DIMENSIONS.items()}


def context_split_values(context, dimension, season):
    if dimension not in DIMENSIONS:
        raise ValueError(f"Unsupported passing dimension: {dimension}")
    return receiving_values(context, RECEIVING_NAMES.get(dimension, dimension), season)
