from dataclasses import dataclass


@dataclass
class Metric:
    count: int = 0
    failures: int = 0
    total_duration_ms: float = 0
    maximum_duration_ms: float = 0


class MetricsRegistry:
    """Small dependency-free registry; replace with an exporter in deployed environments."""

    def __init__(self) -> None:
        self._metrics: dict[str, Metric] = {}

    def observe(self, name: str, duration_ms: float, *, failed: bool = False) -> None:
        metric = self._metrics.setdefault(name, Metric())
        metric.count += 1
        metric.failures += int(failed)
        metric.total_duration_ms += duration_ms
        metric.maximum_duration_ms = max(metric.maximum_duration_ms, duration_ms)

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        return {
            name: {
                "count": metric.count,
                "failures": metric.failures,
                "average_duration_ms": round(metric.total_duration_ms / metric.count, 2),
                "maximum_duration_ms": round(metric.maximum_duration_ms, 2),
            }
            for name, metric in sorted(self._metrics.items())
            if metric.count
        }
