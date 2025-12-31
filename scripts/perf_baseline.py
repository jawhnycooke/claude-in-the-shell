#!/usr/bin/env python3
"""Performance baseline capture for Reachy voice pipeline.

Captures CPU, memory, and temperature metrics during voice pipeline operation
on Raspberry Pi 4. Run this script while the voice pipeline is active to
establish baseline resource usage.

Usage:
    # On the Pi, run alongside voice pipeline:
    python scripts/perf_baseline.py --duration 300 --output baseline.json

    # Quick check (60 seconds):
    python scripts/perf_baseline.py --duration 60 --output quick_check.json

    # Analyze existing baseline:
    python scripts/perf_baseline.py --analyze baseline.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TextIO


@dataclass
class Sample:
    """Single performance sample."""

    timestamp: str
    elapsed_seconds: float
    cpu_percent: float
    cpu_per_core: list[float]
    memory_percent: float
    memory_available_mb: float
    memory_used_mb: float
    cpu_temp_c: float | None = None
    # Optional markers for latency correlation
    event_marker: str | None = None


@dataclass
class BaselineReport:
    """Aggregated baseline statistics."""

    # Metadata
    start_time: str
    end_time: str
    duration_seconds: float
    sample_count: int
    platform: str
    python_version: str

    # CPU stats
    cpu_avg: float
    cpu_max: float
    cpu_min: float
    cpu_p95: float
    cpu_per_core_avg: list[float]

    # Memory stats
    memory_avg_percent: float
    memory_max_percent: float
    memory_avg_mb: float
    memory_max_mb: float

    # Temperature (Pi-specific)
    temp_avg_c: float | None = None
    temp_max_c: float | None = None

    # Event markers (for latency correlation)
    events: list[dict] = field(default_factory=list)


def get_cpu_temperature() -> float | None:
    """Get CPU temperature on Raspberry Pi.

    Reads from /sys/class/thermal/thermal_zone0/temp which is available
    on Raspberry Pi running Linux. Returns None on other platforms.
    """
    thermal_path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        if thermal_path.exists():
            temp_millic = int(thermal_path.read_text().strip())
            return temp_millic / 1000.0
    except (OSError, ValueError):
        pass
    return None


def capture_sample(start_time: float, event_marker: str | None = None) -> Sample:
    """Capture a single performance sample.

    Uses psutil for cross-platform resource monitoring.
    """
    import psutil

    elapsed = time.time() - start_time
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_per_core = psutil.cpu_percent(percpu=True)
    memory = psutil.virtual_memory()

    return Sample(
        timestamp=datetime.now().isoformat(),
        elapsed_seconds=round(elapsed, 2),
        cpu_percent=cpu_percent,
        cpu_per_core=cpu_per_core,
        memory_percent=memory.percent,
        memory_available_mb=round(memory.available / 1024 / 1024, 1),
        memory_used_mb=round(memory.used / 1024 / 1024, 1),
        cpu_temp_c=get_cpu_temperature(),
        event_marker=event_marker,
    )


def capture_baseline(
    duration_seconds: int = 300,
    interval_seconds: float = 1.0,
    output_stream: TextIO | None = None,
) -> list[Sample]:
    """Capture performance baseline over time.

    Args:
        duration_seconds: Total capture duration
        interval_seconds: Time between samples
        output_stream: Optional stream for live output

    Returns:
        List of performance samples
    """
    import psutil

    # Prime the CPU percent counter (first call returns 0)
    psutil.cpu_percent(interval=None)

    samples: list[Sample] = []
    start_time = time.time()
    end_time = start_time + duration_seconds

    if output_stream:
        output_stream.write(f"Capturing baseline for {duration_seconds}s...\n")
        output_stream.write("Time    | CPU%  | Mem%  | Temp°C | Cores\n")
        output_stream.write("-" * 60 + "\n")

    while time.time() < end_time:
        sample = capture_sample(start_time)
        samples.append(sample)

        if output_stream:
            temp_str = f"{sample.cpu_temp_c:.1f}" if sample.cpu_temp_c else "N/A"
            cores_str = " ".join(f"{c:.0f}" for c in sample.cpu_per_core[:4])
            output_stream.write(
                f"{sample.elapsed_seconds:6.1f}s | {sample.cpu_percent:5.1f} | "
                f"{sample.memory_percent:5.1f} | {temp_str:6} | {cores_str}\n"
            )
            output_stream.flush()

        time.sleep(interval_seconds)

    return samples


def calculate_percentile(values: list[float], percentile: float) -> float:
    """Calculate percentile from list of values."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(len(sorted_values) * percentile / 100)
    return sorted_values[min(index, len(sorted_values) - 1)]


def generate_report(samples: list[Sample]) -> BaselineReport:
    """Generate aggregated statistics from samples."""
    import platform

    if not samples:
        raise ValueError("No samples to analyze")

    cpu_values = [s.cpu_percent for s in samples]
    memory_percent_values = [s.memory_percent for s in samples]
    memory_mb_values = [s.memory_used_mb for s in samples]
    temp_values = [s.cpu_temp_c for s in samples if s.cpu_temp_c is not None]

    # Per-core averages
    num_cores = len(samples[0].cpu_per_core)
    cpu_per_core_avg = []
    for core_idx in range(num_cores):
        core_values = [s.cpu_per_core[core_idx] for s in samples]
        cpu_per_core_avg.append(round(statistics.mean(core_values), 1))

    # Collect event markers
    events = [
        {"timestamp": s.timestamp, "elapsed": s.elapsed_seconds, "event": s.event_marker}
        for s in samples
        if s.event_marker
    ]

    return BaselineReport(
        start_time=samples[0].timestamp,
        end_time=samples[-1].timestamp,
        duration_seconds=samples[-1].elapsed_seconds,
        sample_count=len(samples),
        platform=platform.platform(),
        python_version=platform.python_version(),
        # CPU
        cpu_avg=round(statistics.mean(cpu_values), 1),
        cpu_max=round(max(cpu_values), 1),
        cpu_min=round(min(cpu_values), 1),
        cpu_p95=round(calculate_percentile(cpu_values, 95), 1),
        cpu_per_core_avg=cpu_per_core_avg,
        # Memory
        memory_avg_percent=round(statistics.mean(memory_percent_values), 1),
        memory_max_percent=round(max(memory_percent_values), 1),
        memory_avg_mb=round(statistics.mean(memory_mb_values), 1),
        memory_max_mb=round(max(memory_mb_values), 1),
        # Temperature
        temp_avg_c=round(statistics.mean(temp_values), 1) if temp_values else None,
        temp_max_c=round(max(temp_values), 1) if temp_values else None,
        events=events,
    )


def print_report(report: BaselineReport, output_stream: TextIO) -> None:
    """Print formatted baseline report."""
    output_stream.write("\n" + "=" * 60 + "\n")
    output_stream.write("PERFORMANCE BASELINE REPORT\n")
    output_stream.write("=" * 60 + "\n\n")

    output_stream.write(f"Duration: {report.duration_seconds:.0f}s ({report.sample_count} samples)\n")
    output_stream.write(f"Platform: {report.platform}\n")
    output_stream.write(f"Python: {report.python_version}\n")
    output_stream.write(f"Period: {report.start_time} to {report.end_time}\n\n")

    output_stream.write("CPU Usage:\n")
    output_stream.write(f"  Average: {report.cpu_avg}%\n")
    output_stream.write(f"  Max:     {report.cpu_max}%\n")
    output_stream.write(f"  Min:     {report.cpu_min}%\n")
    output_stream.write(f"  P95:     {report.cpu_p95}%\n")
    if report.cpu_per_core_avg:
        cores_str = ", ".join(f"{c}%" for c in report.cpu_per_core_avg)
        output_stream.write(f"  Per-core avg: [{cores_str}]\n")
    output_stream.write("\n")

    output_stream.write("Memory Usage:\n")
    output_stream.write(f"  Average: {report.memory_avg_percent}% ({report.memory_avg_mb:.0f} MB)\n")
    output_stream.write(f"  Max:     {report.memory_max_percent}% ({report.memory_max_mb:.0f} MB)\n")
    output_stream.write("\n")

    if report.temp_avg_c is not None:
        output_stream.write("CPU Temperature:\n")
        output_stream.write(f"  Average: {report.temp_avg_c}°C\n")
        output_stream.write(f"  Max:     {report.temp_max_c}°C\n")
        output_stream.write("\n")

    # Baseline targets from plan
    output_stream.write("Target Thresholds (from plan):\n")
    output_stream.write("  Idle CPU:        < 15% (current baseline)\n")
    output_stream.write("  Wake word CPU:   < 25%\n")
    output_stream.write("  Active conv CPU: < 50%\n")
    output_stream.write("  Memory (RSS):    < 500 MB\n")
    output_stream.write("  CPU Temp:        < 60°C\n")
    output_stream.write("=" * 60 + "\n")


def save_baseline(samples: list[Sample], report: BaselineReport, filepath: Path) -> None:
    """Save baseline data to JSON file."""
    data = {
        "report": asdict(report),
        "samples": [asdict(s) for s in samples],
    }

    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def load_baseline(filepath: Path) -> tuple[list[Sample], BaselineReport]:
    """Load baseline data from JSON file."""
    with open(filepath) as f:
        data = json.load(f)

    samples = [Sample(**s) for s in data["samples"]]

    # Reconstruct report
    report_data = data["report"]
    report = BaselineReport(**report_data)

    return samples, report


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Capture performance baseline for Reachy voice pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Capture duration in seconds (default: 300)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Sample interval in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON file path",
    )
    parser.add_argument(
        "--analyze",
        type=Path,
        default=None,
        help="Analyze existing baseline file instead of capturing",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress live output during capture",
    )

    args = parser.parse_args()

    # Check for psutil
    try:
        import psutil  # noqa: F401
    except ImportError:
        print("Error: psutil is required. Install with: pip install psutil", file=sys.stderr)
        return 1

    # Analyze mode
    if args.analyze:
        if not args.analyze.exists():
            print(f"Error: File not found: {args.analyze}", file=sys.stderr)
            return 1
        samples, report = load_baseline(args.analyze)
        print_report(report, sys.stdout)
        return 0

    # Capture mode
    output_stream = None if args.quiet else sys.stdout
    samples = capture_baseline(args.duration, args.interval, output_stream)

    if not samples:
        print("Error: No samples captured", file=sys.stderr)
        return 1

    report = generate_report(samples)
    print_report(report, sys.stdout)

    # Save to file if specified
    if args.output:
        save_baseline(samples, report, args.output)
        print(f"\nBaseline saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
