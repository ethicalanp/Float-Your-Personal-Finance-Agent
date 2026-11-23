import threading
from collections import defaultdict
from typing import Any


class AssistantMetricsRegistry:
    """Thread-safe in-memory Prometheus-compatible metrics registry for the AI subsystem."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Counters: (name, tuple(sorted_labels)) -> value
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        # Latency buckets (stage -> list of observations)
        self._stage_latencies: dict[str, list[float]] = defaultdict(list)

    def inc(self, name: str, value: float = 1.0, **labels: Any) -> None:
        """Increment a counter with optional label dimensions."""
        label_tuple = tuple(sorted((k, str(v)) for k, v in labels.items()))
        with self._lock:
            self._counters[(name, label_tuple)] += value

    def observe_stage_latency(self, stage: str, seconds: float) -> None:
        """Record stage execution latency in seconds."""
        with self._lock:
            self._stage_latencies[stage].append(seconds)
            # Keep memory bounded
            if len(self._stage_latencies[stage]) > 1000:
                self._stage_latencies[stage] = self._stage_latencies[stage][-1000:]

    def format_prometheus_text(self) -> str:
        """Generate Prometheus exposition text format (version=0.0.4)."""
        lines: list[str] = []
        lines.append("# HELP pfa_assistant_requests_total Total number of assistant requests.")
        lines.append("# TYPE pfa_assistant_requests_total counter")

        with self._lock:
            for (name, label_tuple), val in self._counters.items():
                label_str = ""
                if label_tuple:
                    label_str = "{" + ",".join(f'{k}="{v}"' for k, v in label_tuple) + "}"
                lines.append(f"{name}{label_str} {val}")

            lines.append("\n# HELP pfa_assistant_stage_latency_seconds Execution duration per processing stage.")
            lines.append("# TYPE pfa_assistant_stage_latency_seconds summary")
            for stage, lats in self._stage_latencies.items():
                if not lats:
                    continue
                count = len(lats)
                total = sum(lats)
                sorted_lats = sorted(lats)
                p50 = sorted_lats[int(count * 0.5)]
                p95 = sorted_lats[int(count * 0.95)] if count >= 20 else sorted_lats[-1]
                lines.append(f'pfa_assistant_stage_latency_seconds{{stage="{stage}",quantile="0.5"}} {p50:.4f}')
                lines.append(f'pfa_assistant_stage_latency_seconds{{stage="{stage}",quantile="0.95"}} {p95:.4f}')
                lines.append(f'pfa_assistant_stage_latency_seconds_sum{{stage="{stage}"}} {total:.4f}')
                lines.append(f'pfa_assistant_stage_latency_seconds_count{{stage="{stage}"}} {count}')

        lines.append("")
        return "\n".join(lines)


# Global singleton instance
assistant_metrics = AssistantMetricsRegistry()
