from dataclasses import dataclass


@dataclass
class Metrics:
    metrics = dict()

    def __post_init__(self):
        self.metrics["_total"] = {
            "files": 0,
            "lines": 0
        }
