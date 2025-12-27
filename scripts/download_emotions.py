#!/usr/bin/env python3
"""Download and convert HuggingFace emotions library to local JSON files.

This script downloads the pollen-robotics/reachy-mini-emotions-library dataset
from HuggingFace using snapshot_download (like the SDK does) to get the original
JSON files with proper emotion names like "curious1.json".

Usage:
    python scripts/download_emotions.py

The script will:
1. Download the raw dataset files from HuggingFace
2. Convert 4x4 transformation matrices to roll/pitch/yaw
3. Save processed JSON files to data/emotions/
4. Create a manifest.json index file
"""

from __future__ import annotations

import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path


class MatrixConversionError(ValueError):
    """Raised when matrix conversion fails due to invalid input."""

    pass


def matrix_to_rpy(matrix: list[list[float]]) -> dict[str, float]:
    """Convert a 4x4 transformation matrix to roll, pitch, yaw.

    The matrix is a homogeneous transformation matrix where the upper-left
    3x3 submatrix is the rotation matrix.

    Args:
        matrix: 4x4 transformation matrix as nested lists.

    Returns:
        Dictionary with roll, pitch, yaw in radians.

    Raises:
        MatrixConversionError: If matrix is not 4x4 or has invalid values.
    """
    # Validate matrix dimensions
    if not isinstance(matrix, list) or len(matrix) < 3:
        raise MatrixConversionError(
            f"Matrix must have at least 3 rows, got: {len(matrix) if isinstance(matrix, list) else type(matrix)}"
        )
    for i, row in enumerate(matrix[:3]):
        if not isinstance(row, list) or len(row) < 3:
            raise MatrixConversionError(
                f"Matrix row {i} must have at least 3 columns, got: {len(row) if isinstance(row, list) else type(row)}"
            )

    # Extract rotation matrix elements
    r00, r01, r02 = matrix[0][0], matrix[0][1], matrix[0][2]
    r10, _, _ = matrix[1][0], matrix[1][1], matrix[1][2]
    r20, r21, r22 = matrix[2][0], matrix[2][1], matrix[2][2]

    # Calculate Euler angles (ZYX convention, commonly used in robotics)
    # This gives us yaw (Z), pitch (Y), roll (X)

    # Check for gimbal lock
    if abs(r20) >= 1.0:
        # Gimbal lock case
        yaw = 0.0
        if r20 < 0:
            pitch = math.pi / 2
            roll = math.atan2(r01, r02)
        else:
            pitch = -math.pi / 2
            roll = math.atan2(-r01, -r02)
    else:
        pitch = math.asin(-r20)
        roll = math.atan2(r21, r22)
        yaw = math.atan2(r10, r00)

    return {
        "roll": roll,
        "pitch": pitch,
        "yaw": yaw,
    }


def download_and_convert() -> None:
    """Download the HuggingFace dataset and convert to local JSON files."""
    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub.utils import (
            EntryNotFoundError,
            HfHubHTTPError,
            RepositoryNotFoundError,
        )
    except ImportError:
        print("Error: 'huggingface_hub' package not installed.")
        print("Install it with: pip install huggingface_hub")
        return

    dataset_name = "pollen-robotics/reachy-mini-emotions-library"
    print(f"Downloading {dataset_name} from HuggingFace...")

    try:
        # Download the raw dataset files (like the SDK does)
        cache_dir = snapshot_download(dataset_name, repo_type="dataset")
        print(f"Downloaded to cache: {cache_dir}")
    except RepositoryNotFoundError:
        print(f"Error: Dataset '{dataset_name}' not found on HuggingFace")
        return
    except EntryNotFoundError as e:
        print(f"Error: Required file not found in dataset: {e}")
        return
    except HfHubHTTPError as e:
        print(f"Error: HuggingFace API error: {e}")
        return
    except OSError as e:
        print(f"Error: Disk/network error during download: {e}")
        return

    # Find all JSON files in the downloaded directory
    cache_path = Path(cache_dir)
    json_files = list(cache_path.glob("**/*.json"))

    print(f"Found {len(json_files)} JSON files")

    # Create output directory
    output_dir = Path(__file__).parent.parent / "data" / "emotions"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process each JSON file
    manifest = {
        "version": "1.0",
        "source_dataset": dataset_name,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "emotions": {},
        "dances": {},
    }

    processed_count = 0
    skipped_count = 0

    for json_file in sorted(json_files):
        move_name = json_file.stem

        # Skip metadata files
        if move_name.startswith(".") or move_name == "dataset_info":
            continue

        print(f"  Processing: {move_name}")

        try:
            with open(json_file) as f:
                raw_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"    Error: Invalid JSON in {json_file}: {e}")
            skipped_count += 1
            continue
        except OSError as e:
            print(f"    Error: Cannot read {json_file}: {e}")
            skipped_count += 1
            continue

        # Extract fields from raw data
        # The raw format has: description, time, set_target_data
        description = raw_data.get("description", move_name)
        times = raw_data.get("time", [])
        targets = raw_data.get("set_target_data", [])

        if not times or not targets:
            print(f"    Skipping {move_name}: no keyframe data")
            skipped_count += 1
            continue

        # Convert keyframes
        keyframes = []
        for i, (t, target) in enumerate(zip(times, targets, strict=True)):
            try:
                # Extract head matrix and convert to RPY
                head_matrix = target.get("head", [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
                head_rpy = matrix_to_rpy(head_matrix)

                # Extract antennas (in radians)
                antennas = target.get("antennas", [0.785, 0.785])  # Default ~45 degrees

                # Extract body yaw
                body_yaw = target.get("body_yaw", 0.0)

                keyframes.append({
                    "time_ms": t * 1000,  # Convert seconds to milliseconds
                    "head": head_rpy,
                    "antennas": antennas,
                    "body_yaw": body_yaw,
                })
            except MatrixConversionError as e:
                print(f"    Warning: Invalid head matrix in keyframe {i}: {e}")
                continue
            except (KeyError, TypeError, IndexError) as e:
                print(f"    Warning: Invalid keyframe {i} structure: {e}")
                continue

        if not keyframes:
            print(f"    Skipping {move_name}: no valid keyframes")
            skipped_count += 1
            continue

        # Calculate duration
        duration_ms = keyframes[-1]["time_ms"] if keyframes else 0

        # Create emotion data
        emotion_data = {
            "name": move_name,
            "description": description,
            "duration_ms": duration_ms,
            "keyframe_count": len(keyframes),
            "keyframes": keyframes,
        }

        # Save to JSON file
        output_file = output_dir / f"{move_name}.json"
        with open(output_file, "w") as f:
            json.dump(emotion_data, f, indent=2)

        # Check for corresponding audio file
        audio_file = json_file.with_suffix(".wav")
        if audio_file.exists():
            # Copy audio file too
            audio_output = output_dir / f"{move_name}.wav"
            shutil.copy2(audio_file, audio_output)
            manifest_entry = {
                "file": f"{move_name}.json",
                "audio": f"{move_name}.wav",
                "duration_ms": duration_ms,
                "keyframe_count": len(keyframes),
            }
        else:
            manifest_entry = {
                "file": f"{move_name}.json",
                "duration_ms": duration_ms,
                "keyframe_count": len(keyframes),
            }

        # Add to manifest
        is_dance = "dance" in move_name.lower()
        category = "dances" if is_dance else "emotions"
        manifest[category][move_name] = manifest_entry

        processed_count += 1

    # Save manifest
    manifest_file = output_dir / "manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)

    print("\nDone!")
    print(f"  Processed: {processed_count} emotions/dances")
    print(f"  Skipped: {skipped_count}")
    print(f"  Output directory: {output_dir}")
    print(f"  Manifest: {manifest_file}")

    # Summary
    print(f"\nEmotions ({len(manifest['emotions'])}):")
    for name in sorted(manifest["emotions"].keys()):
        entry = manifest["emotions"][name]
        audio = " (with audio)" if "audio" in entry else ""
        print(f"  - {name}{audio}")

    print(f"\nDances ({len(manifest['dances'])}):")
    for name in sorted(manifest["dances"].keys()):
        entry = manifest["dances"][name]
        audio = " (with audio)" if "audio" in entry else ""
        print(f"  - {name}{audio}")


if __name__ == "__main__":
    download_and_convert()
