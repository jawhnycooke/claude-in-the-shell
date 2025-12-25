"""Mock Reachy Daemon for development and testing.

Provides a FastAPI server that mimics the Reachy Daemon API,
allowing development without physical hardware.
"""

from __future__ import annotations

import asyncio
import io
import math
import random
import time
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel, Field

# Optional FastAPI import - only used when running the mock server
try:
    from fastapi import FastAPI, Query, Response
    from fastapi.middleware.cors import CORSMiddleware

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# Optional PIL for generating test images
try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class HeadMoveRequest(BaseModel):
    """Request model for head movement."""

    direction: str
    speed: str = "normal"
    degrees: float | None = None


class EmotionRequest(BaseModel):
    """Request model for emotion expression."""

    emotion: str
    intensity: float = Field(default=0.7, ge=0.1, le=1.0)


class SpeakRequest(BaseModel):
    """Request model for speech."""

    text: str
    voice: str = "default"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class CaptureRequest(BaseModel):
    """Request model for image capture."""

    analyze: bool = False
    save: bool = False


class AntennaRequest(BaseModel):
    """Request model for antenna control."""

    left_angle: float | None = None
    right_angle: float | None = None
    wiggle: bool = False
    duration_ms: int = 500


class LookAtSoundRequest(BaseModel):
    """Request model for sound localization."""

    timeout_ms: int = 2000


class DanceRequest(BaseModel):
    """Request model for dance routine."""

    routine: str
    duration_seconds: float = 5.0


class RotateRequest(BaseModel):
    """Request model for body rotation."""

    direction: str
    degrees: float = 90.0
    speed: str = "normal"


class LookAtRequest(BaseModel):
    """Request model for precise head positioning."""

    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    z: float = 0.0
    duration: float = 1.0


class ListenRequest(BaseModel):
    """Request model for audio capture."""

    duration_seconds: float = 3.0


class GestureRequest(BaseModel):
    """Request model for gestures (nod/shake)."""

    times: int = 2
    speed: str = "normal"


class CancelActionRequest(BaseModel):
    """Request model for canceling actions."""

    action_id: str | None = None
    all_actions: bool = False


class MockDaemonState:
    """Simulated state of the robot."""

    def __init__(self) -> None:
        self.head_position = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0, "z": 0.0}
        self.body_rotation = 0.0
        self.left_antenna_angle = 45.0
        self.right_antenna_angle = 45.0
        self.current_emotion: str | None = None
        self.is_speaking = False
        self.is_dancing = False
        self.is_awake = True
        self.is_listening = False
        # Animation state for enhanced visualization
        self.frame_counter: int = 0
        self.attention_state: str = "passive"  # passive, alert, engaged
        self.last_blink_time: float = time.time()
        self.blink_duration: float = 0.0  # Current blink progress (0 = open, 0.15 = closed)


# Global mock state
_mock_state = MockDaemonState()


def create_mock_daemon_app() -> Any:
    """Create the mock daemon FastAPI application.

    Returns:
        FastAPI application instance.

    Raises:
        ImportError: If FastAPI is not installed.
    """
    if not FASTAPI_AVAILABLE:
        raise ImportError(
            "FastAPI is required for the mock daemon. "
            "Install with: pip install fastapi uvicorn"
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Reset state on startup."""
        global _mock_state
        _mock_state = MockDaemonState()
        yield

    app = FastAPI(
        title="Reachy Mock Daemon",
        description="Mock daemon for development without hardware",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware for cross-origin video feed requests
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def generate_test_frame() -> bytes:
        """Generate an enhanced test frame image for video streaming.

        Creates a detailed robot visualization with:
        - Body and neck below head
        - Expressive face with emotion-based eyes/mouth
        - Animated antennas with tips
        - Activity indicators (speaking waves, dancing motion)
        - Comprehensive status overlay panel
        - Blink animation

        Falls back to a minimal JPEG if PIL is not available.
        """
        if PIL_AVAILABLE:
            # Dashboard color scheme
            BG_PRIMARY = (26, 26, 46)       # #1a1a2e
            BG_SECONDARY = (22, 33, 62)     # #16213e
            BG_CARD = (15, 52, 96)          # #0f3460
            TEXT_PRIMARY = (234, 234, 234)  # #eaeaea
            TEXT_SECONDARY = (160, 160, 160)  # #a0a0a0
            ACCENT_CYAN = (0, 217, 255)     # #00d9ff
            ACCENT_GREEN = (0, 255, 136)    # #00ff88
            ACCENT_YELLOW = (255, 204, 0)   # #ffcc00
            ACCENT_RED = (255, 71, 87)      # #ff4757
            BORDER_COLOR = (45, 58, 74)     # #2d3a4a

            # Create 800x600 image (increased resolution)
            WIDTH, HEIGHT = 800, 600
            img = Image.new("RGB", (WIDTH, HEIGHT), color=BG_PRIMARY)
            draw = ImageDraw.Draw(img)

            # Update frame counter and handle blink animation
            _mock_state.frame_counter += 1
            current_time = time.time()

            # Blink every 3-5 seconds for 0.15 seconds
            if current_time - _mock_state.last_blink_time > random.uniform(3, 5):
                _mock_state.last_blink_time = current_time
                _mock_state.blink_duration = 0.15

            is_blinking = (current_time - _mock_state.last_blink_time) < _mock_state.blink_duration

            # Robot center position (moved up to make room for status panel)
            center_x, center_y = WIDTH // 2, 220

            # ===== BODY (no neck - small gap between head and body) =====
            # Body is more vertically rectangular
            body_width, body_height = 80, 110  # Taller than wide
            body_y = center_y + 50  # Position with small gap from head (head bottom is at center_y + 35)
            rotation_offset = int(_mock_state.body_rotation / 5)  # Visual hint of rotation

            # Draw body shadow/depth
            draw.rounded_rectangle(
                [center_x - body_width // 2 + 3, body_y + 3,
                 center_x + body_width // 2 + 3, body_y + body_height + 3],
                radius=20,
                fill=(10, 30, 50),
            )
            # Draw body
            draw.rounded_rectangle(
                [center_x - body_width // 2, body_y,
                 center_x + body_width // 2, body_y + body_height],
                radius=20,
                fill=BG_CARD,
                outline=ACCENT_CYAN,
                width=2,
            )

            # Rotation indicator on body
            if abs(_mock_state.body_rotation) > 5:
                rot_text = f"{_mock_state.body_rotation:.0f}°"
                draw.text((center_x - 15, body_y + 45), rot_text, fill=ACCENT_YELLOW)

            # NOTE: No neck - small gap left between head and body for Reachy Mini style

            # ===== HEAD =====
            # Apply head position offsets for visualization
            yaw = _mock_state.head_position.get("yaw", 0)
            pitch = _mock_state.head_position.get("pitch", 0)
            roll = _mock_state.head_position.get("roll", 0)

            head_offset_x = int(yaw / 4)
            head_offset_y = int(pitch / 4)

            head_x = center_x + head_offset_x
            head_y = center_y + head_offset_y

            # Head shape - rounded rectangle matching body style
            # Wider than tall, same corner radius style as body
            head_width = 120   # Wide
            head_height = 70   # Not too tall
            head_radius_corner = 20  # Same corner radius as body

            # Head shadow
            draw.rounded_rectangle(
                [head_x - head_width // 2 + 4, head_y - head_height // 2 + 4,
                 head_x + head_width // 2 + 4, head_y + head_height // 2 + 4],
                radius=head_radius_corner,
                fill=(10, 30, 50),
            )

            # Head fill - matching body style
            draw.rounded_rectangle(
                [head_x - head_width // 2, head_y - head_height // 2,
                 head_x + head_width // 2, head_y + head_height // 2],
                fill=BG_CARD,
                outline=ACCENT_CYAN,
                width=2,
            )

            # Inner head highlight (top portion - subtle visor effect)
            draw.rounded_rectangle(
                [head_x - head_width // 2 + 8, head_y - head_height // 2 + 6,
                 head_x + head_width // 2 - 8, head_y - 5],
                radius=15,
                fill=(20, 60, 100),
            )

            # ===== EYES (Reachy Mini goggle-style) =====
            # Reachy has large circular goggle eyes with BLACK frames and dark lenses
            # No mouth - expression is purely through eyes and antennas
            eye_base_y = head_y
            eye_spacing = 28  # Distance from center to each eye
            eye_outer_radius = 24   # Black goggle frame (outer)
            eye_inner_radius = 20   # Dark lens inside

            # Eye position shifts with head movement
            eye_shift_x = int(yaw / 6)
            eye_shift_y = int(pitch / 6)

            # Emotion affects eye appearance
            emotion = _mock_state.current_emotion or "neutral"

            # Draw both goggle eyes
            for side in [-1, 1]:  # Left and right
                ex = head_x + (side * eye_spacing) + eye_shift_x
                ey = eye_base_y + eye_shift_y

                if is_blinking:
                    # Closed eyes - horizontal lines (black frames still visible)
                    draw.ellipse(
                        [ex - eye_outer_radius, ey - 4,
                         ex + eye_outer_radius, ey + 4],
                        fill=(20, 20, 30),  # Dark frame
                        outline=ACCENT_CYAN,
                        width=1,
                    )
                else:
                    # Black goggle frame (like real Reachy)
                    draw.ellipse(
                        [ex - eye_outer_radius, ey - eye_outer_radius,
                         ex + eye_outer_radius, ey + eye_outer_radius],
                        fill=(20, 20, 30),  # Very dark frame
                        outline=ACCENT_CYAN,
                        width=2,
                    )

                    # Dark lens inside
                    draw.ellipse(
                        [ex - eye_inner_radius, ey - eye_inner_radius,
                         ex + eye_inner_radius, ey + eye_inner_radius],
                        fill=(8, 10, 18),  # Nearly black lens
                    )

                    # Lens reflection/highlight (subtle)
                    highlight_x = ex - 6
                    highlight_y = ey - 6
                    draw.ellipse(
                        [highlight_x - 4, highlight_y - 4,
                         highlight_x + 4, highlight_y + 4],
                        fill=(40, 50, 70),  # Subtle reflection
                    )

                    # Emotion-based eye glow/details inside lens
                    if emotion == "happy":
                        # Happy: upward arc like ^_^
                        draw.arc(
                            [ex - 12, ey - 8, ex + 12, ey + 12],
                            start=200, end=340,
                            fill=ACCENT_CYAN,
                            width=2,
                        )
                    elif emotion == "sad":
                        # Sad: downward droopy arc
                        draw.arc(
                            [ex - 12, ey - 4, ex + 12, ey + 14],
                            start=20, end=160,
                            fill=ACCENT_CYAN,
                            width=2,
                        )
                    elif emotion == "surprised":
                        # Surprised: bright ring inside
                        draw.ellipse(
                            [ex - 10, ey - 10, ex + 10, ey + 10],
                            outline=ACCENT_CYAN,
                            width=2,
                        )
                    elif emotion == "angry":
                        # Angry: diagonal slash
                        slant = -1 if side == -1 else 1
                        draw.line(
                            [(ex - 10, ey - 8 * slant),
                             (ex + 10, ey + 8 * slant)],
                            fill=ACCENT_RED,
                            width=3,
                        )
                    elif emotion == "curious":
                        # Curious: asymmetric - one brighter
                        brightness = 10 if side == 1 else 6
                        draw.ellipse(
                            [ex - brightness, ey - brightness,
                             ex + brightness, ey + brightness],
                            outline=ACCENT_CYAN,
                            width=2,
                        )
                    # Neutral: just the dark lens with highlight (no extra glow)

            # Camera/sensor bar between eyes (like real Reachy - small dark strip)
            sensor_width = 16
            sensor_height = 5
            draw.rounded_rectangle(
                [head_x - sensor_width // 2, eye_base_y - sensor_height // 2 - 2,
                 head_x + sensor_width // 2, eye_base_y + sensor_height // 2 - 2],
                radius=2,
                fill=(15, 15, 25),
                outline=(40, 50, 70),
                width=1,
            )

            # NOTE: Reachy Mini has NO mouth - expression is through eyes and antennas only

            # ===== ANTENNAS (Reachy Mini style - thin wire with spring coil base) =====
            left_ant = int(_mock_state.left_antenna_angle)
            right_ant = int(_mock_state.right_antenna_angle)

            # Antenna base points (on top of pill-shaped head)
            ant_base_y = head_y - head_height // 2 - 5

            for side, angle in [(-1, left_ant), (1, right_ant)]:
                base_x = head_x + (side * 35)  # Closer together like real Reachy

                # Calculate antenna tip position using angle
                ant_length = 60  # Taller antennas
                tip_x = base_x + int(side * 20 * math.cos(math.radians(90 - angle)))
                tip_y = ant_base_y - int(ant_length * math.sin(math.radians(angle)))

                # Spring coil at base (like real Reachy)
                coil_height = 12
                coil_segments = 4
                for i in range(coil_segments):
                    coil_y = ant_base_y - (i * coil_height // coil_segments)
                    coil_offset = 4 * (1 if i % 2 == 0 else -1)
                    draw.ellipse(
                        [base_x + coil_offset - 3, coil_y - 2,
                         base_x + coil_offset + 3, coil_y + 2],
                        outline=ACCENT_GREEN,
                        width=1,
                    )

                # Thin wire antenna line (thinner than before)
                wire_start_y = ant_base_y - coil_height
                draw.line(
                    [(base_x, wire_start_y), (tip_x, tip_y)],
                    fill=ACCENT_GREEN,
                    width=2,  # Thinner wire
                )

                # Antenna tip (small ball)
                draw.ellipse(
                    [tip_x - 5, tip_y - 5, tip_x + 5, tip_y + 5],
                    fill=ACCENT_GREEN,
                )

                # Antenna glow when awake
                if _mock_state.is_awake:
                    pulse = abs(math.sin(_mock_state.frame_counter * 0.1)) * 0.5 + 0.5
                    glow_size = int(7 + pulse * 3)
                    glow_color = (0, int(255 * pulse), int(136 * pulse))
                    draw.ellipse(
                        [tip_x - glow_size, tip_y - glow_size,
                         tip_x + glow_size, tip_y + glow_size],
                        outline=glow_color,
                        width=2,
                    )

            # ===== ACTIVITY INDICATORS =====
            # Speaking: sound waves near head (no mouth, so waves come from side)
            if _mock_state.is_speaking:
                wave_x = head_x + head_width // 2 + 15
                wave_y = head_y + 10  # Near center of head
                for i in range(3):
                    offset = (_mock_state.frame_counter + i * 5) % 20
                    alpha = 1.0 - (offset / 20)
                    wave_color = (int(255 * alpha), int(204 * alpha), 0)
                    draw.arc(
                        [wave_x + offset, wave_y - 10 - offset,
                         wave_x + offset + 15, wave_y + 10 + offset],
                        start=-60, end=60,
                        fill=wave_color,
                        width=2,
                    )

            # Dancing: motion lines around body
            if _mock_state.is_dancing:
                dance_phase = _mock_state.frame_counter % 20
                for i in range(4):
                    angle = (i * 90 + dance_phase * 18) % 360
                    mx = center_x + int(80 * math.cos(math.radians(angle)))
                    my = body_y + 40 + int(30 * math.sin(math.radians(angle)))
                    line_len = 15
                    draw.line(
                        [(mx, my), (mx + int(line_len * math.cos(math.radians(angle))),
                                    my + int(line_len * math.sin(math.radians(angle))))],
                        fill=ACCENT_YELLOW,
                        width=3,
                    )

            # Sleeping: Zzz
            if not _mock_state.is_awake:
                z_x = head_x + head_width // 2 + 10
                z_y = head_y - head_height // 2
                for i, size in enumerate([12, 16, 20]):
                    offset = (_mock_state.frame_counter // 10 + i) % 3
                    draw.text(
                        (z_x + i * 20, z_y - i * 15 - offset * 3),
                        "Z",
                        fill=TEXT_SECONDARY,
                    )

            # ===== STATUS OVERLAY PANEL =====
            panel_height = 100
            panel_y = HEIGHT - panel_height - 10
            panel_margin = 20

            # Panel background with border
            draw.rounded_rectangle(
                [panel_margin, panel_y,
                 WIDTH - panel_margin, HEIGHT - 10],
                radius=10,
                fill=BG_SECONDARY,
                outline=BORDER_COLOR,
                width=2,
            )

            # Status text layout
            timestamp = time.strftime("%H:%M:%S")
            line_y = panel_y + 12
            line_height = 18

            # Row 1: Title and timestamp
            draw.text((panel_margin + 15, line_y), "REACHY MOCK DAEMON", fill=ACCENT_CYAN)
            draw.text((WIDTH - panel_margin - 80, line_y), timestamp, fill=TEXT_SECONDARY)
            line_y += line_height + 5

            # Separator line
            draw.line(
                [(panel_margin + 10, line_y), (WIDTH - panel_margin - 10, line_y)],
                fill=BORDER_COLOR,
                width=1,
            )
            line_y += 8

            # Row 2: Mode and status
            mode_text = "Mode: Simulator"
            status_text = "AWAKE" if _mock_state.is_awake else "SLEEPING"
            status_color = ACCENT_GREEN if _mock_state.is_awake else TEXT_SECONDARY
            draw.text((panel_margin + 15, line_y), mode_text, fill=TEXT_PRIMARY)
            draw.text((panel_margin + 180, line_y), f"Status: ", fill=TEXT_SECONDARY)
            draw.text((panel_margin + 245, line_y), status_text, fill=status_color)
            line_y += line_height

            # Row 3: Head position and body rotation
            roll = _mock_state.head_position.get('roll', 0)
            pitch = _mock_state.head_position.get('pitch', 0)
            yaw = _mock_state.head_position.get('yaw', 0)
            head_text = f"Head: R:{roll:.1f} P:{pitch:.1f} Y:{yaw:.1f}"
            body_text = f"Body: {_mock_state.body_rotation:.1f}°"
            draw.text((panel_margin + 15, line_y), head_text, fill=TEXT_PRIMARY)
            draw.text((panel_margin + 280, line_y), body_text, fill=TEXT_PRIMARY)
            line_y += line_height

            # Row 4: Antennas and emotion
            ant_text = f"Antennas: L:{_mock_state.left_antenna_angle:.0f}° R:{_mock_state.right_antenna_angle:.0f}°"
            draw.text((panel_margin + 15, line_y), ant_text, fill=TEXT_PRIMARY)

            if _mock_state.current_emotion:
                draw.text((panel_margin + 280, line_y), f"Emotion: {_mock_state.current_emotion}", fill=ACCENT_GREEN)

            # Activity badges on right side
            badge_x = WIDTH - panel_margin - 100
            badge_y = panel_y + 45
            if _mock_state.is_speaking:
                draw.rounded_rectangle(
                    [badge_x, badge_y, badge_x + 80, badge_y + 22],
                    radius=11,
                    fill=ACCENT_YELLOW,
                )
                draw.text((badge_x + 8, badge_y + 3), "Speaking", fill=BG_PRIMARY)
            elif _mock_state.is_dancing:
                draw.rounded_rectangle(
                    [badge_x, badge_y, badge_x + 80, badge_y + 22],
                    radius=11,
                    fill=ACCENT_YELLOW,
                )
                draw.text((badge_x + 12, badge_y + 3), "Dancing", fill=BG_PRIMARY)
            elif _mock_state.is_listening:
                draw.rounded_rectangle(
                    [badge_x, badge_y, badge_x + 80, badge_y + 22],
                    radius=11,
                    fill=ACCENT_CYAN,
                )
                draw.text((badge_x + 10, badge_y + 3), "Listening", fill=BG_PRIMARY)

            # ===== STATUS INDICATOR DOT =====
            # Top right corner
            dot_x, dot_y = WIDTH - 35, 25
            if _mock_state.is_awake:
                dot_color = ACCENT_GREEN
            else:
                dot_color = TEXT_SECONDARY

            # Pulsing effect when active
            if _mock_state.is_awake and (_mock_state.is_speaking or _mock_state.is_dancing):
                pulse = abs(math.sin(_mock_state.frame_counter * 0.15))
                dot_size = int(8 + pulse * 4)
            else:
                dot_size = 8

            draw.ellipse(
                [dot_x - dot_size, dot_y - dot_size,
                 dot_x + dot_size, dot_y + dot_size],
                fill=dot_color,
            )

            # Convert to JPEG
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue()

        else:
            # Minimal 1x1 JPEG if PIL not available
            # This is a valid minimal JPEG
            return bytes([
                0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
                0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
                0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
                0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
                0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
                0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
                0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
                0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
                0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
                0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
                0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
                0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
                0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
                0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
                0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
                0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
                0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
                0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
                0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
                0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
                0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
                0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
                0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
                0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
                0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
                0x00, 0x00, 0x3F, 0x00, 0xFD, 0xFC, 0xA3, 0x1E, 0xB4, 0x00, 0xFF, 0xD9,
            ])

    @app.get("/camera/capture")
    async def get_camera_frame() -> Response:
        """Return a camera frame as JPEG for video streaming."""
        frame_data = generate_test_frame()
        return Response(
            content=frame_data,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Check daemon health."""
        return {"status": "healthy", "mode": "mock"}

    @app.get("/api/daemon/status")
    async def daemon_status() -> dict[str, Any]:
        """Get detailed daemon status for web dashboard."""
        return {
            "status": "connected",
            "mode": "mock",
            "connection_type": "Simulator",
            "version": "1.0.0",
            "head": _mock_state.head_position,
            "body_rotation": _mock_state.body_rotation,
            "left_antenna": _mock_state.left_antenna_angle,
            "right_antenna": _mock_state.right_antenna_angle,
            "current_emotion": _mock_state.current_emotion,
            "is_awake": _mock_state.is_awake,
            "is_speaking": _mock_state.is_speaking,
            "is_dancing": _mock_state.is_dancing,
        }

    @app.post("/head/move")
    async def move_head(request: HeadMoveRequest) -> dict[str, Any]:
        """Simulate head movement."""
        # Simulate movement delay based on speed
        delay_map = {"slow": 0.5, "normal": 0.3, "fast": 0.1}
        await asyncio.sleep(delay_map.get(request.speed, 0.3))

        # Update simulated position
        degrees = request.degrees or 20.0
        direction_map = {
            "left": ("yaw", -degrees),
            "right": ("yaw", degrees),
            "up": ("pitch", -degrees),
            "down": ("pitch", degrees),
            "front": ("yaw", 0.0),
        }

        if request.direction in direction_map:
            axis, value = direction_map[request.direction]
            if request.direction == "front":
                _mock_state.head_position = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
            else:
                _mock_state.head_position[axis] = value

        return {
            "status": "success",
            "position": _mock_state.head_position,
            "message": f"Head moved {request.direction}",
        }

    @app.post("/expression/emotion")
    async def play_emotion(request: EmotionRequest) -> dict[str, Any]:
        """Simulate emotional expression."""
        # Simulate expression duration
        await asyncio.sleep(0.5 * request.intensity)

        _mock_state.current_emotion = request.emotion

        return {
            "status": "success",
            "emotion": request.emotion,
            "intensity": request.intensity,
            "message": f"Expressing {request.emotion}",
        }

    @app.post("/audio/speak")
    async def speak(request: SpeakRequest) -> dict[str, Any]:
        """Simulate speech output."""
        # Estimate speech duration (rough: 5 chars per second)
        base_duration = len(request.text) / 5.0
        duration = base_duration / request.speed

        _mock_state.is_speaking = True
        await asyncio.sleep(min(duration, 2.0))  # Cap at 2s for testing
        _mock_state.is_speaking = False

        return {
            "status": "success",
            "text": request.text,
            "duration_seconds": duration,
            "message": "Speech completed",
        }

    @app.post("/camera/capture")
    async def capture_image(request: CaptureRequest) -> dict[str, Any]:
        """Simulate image capture."""
        await asyncio.sleep(0.1)  # Simulate capture delay

        result: dict[str, Any] = {
            "status": "success",
            "width": 640,
            "height": 480,
            "format": "jpeg",
        }

        if request.analyze:
            # Simulate vision analysis
            await asyncio.sleep(0.5)
            result["analysis"] = {
                "objects_detected": ["desk", "computer", "person"],
                "faces_detected": 1,
                "description": "A person sitting at a desk with a computer",
            }

        if request.save:
            result["saved_path"] = "/tmp/reachy_capture_mock.jpg"

        return result

    @app.post("/antenna/state")
    async def set_antenna_state(request: AntennaRequest) -> dict[str, Any]:
        """Simulate antenna control."""
        await asyncio.sleep(request.duration_ms / 1000.0)

        if request.left_angle is not None:
            _mock_state.left_antenna_angle = request.left_angle
        if request.right_angle is not None:
            _mock_state.right_antenna_angle = request.right_angle

        return {
            "status": "success",
            "left_angle": _mock_state.left_antenna_angle,
            "right_angle": _mock_state.right_antenna_angle,
            "wiggle": request.wiggle,
        }

    @app.get("/sensors")
    async def get_sensors(
        sensors: str = Query(default="all"),
    ) -> dict[str, Any]:
        """Simulate sensor readings."""
        sensor_list = sensors.split(",")

        result: dict[str, Any] = {"status": "success"}

        if "all" in sensor_list or "imu" in sensor_list:
            result["imu"] = {
                "acceleration": {
                    "x": random.uniform(-0.1, 0.1),
                    "y": random.uniform(-0.1, 0.1),
                    "z": 9.8 + random.uniform(-0.1, 0.1),
                },
                "gyroscope": {
                    "x": random.uniform(-1, 1),
                    "y": random.uniform(-1, 1),
                    "z": random.uniform(-1, 1),
                },
            }

        if "all" in sensor_list or "audio_level" in sensor_list:
            result["audio_level"] = {
                "level_db": random.uniform(-60, -20),
                "is_speech_detected": random.random() > 0.7,
            }

        if "all" in sensor_list or "temperature" in sensor_list:
            result["temperature"] = {
                "cpu_celsius": 45.0 + random.uniform(-5, 10),
                "ambient_celsius": 22.0 + random.uniform(-2, 2),
            }

        return result

    @app.post("/audio/look_at_sound")
    async def look_at_sound(request: LookAtSoundRequest) -> dict[str, Any]:
        """Simulate sound localization."""
        # Simulate listening period
        await asyncio.sleep(min(request.timeout_ms / 1000.0, 1.0))

        # Randomly determine if sound was detected
        if random.random() > 0.3:
            direction = random.choice(["left", "right", "front"])
            angle = random.uniform(10, 45) * (1 if direction == "right" else -1)

            return {
                "status": "success",
                "sound_detected": True,
                "direction": direction,
                "angle_degrees": angle,
                "confidence": random.uniform(0.7, 0.95),
            }
        else:
            return {
                "status": "success",
                "sound_detected": False,
                "message": "No significant sound detected",
            }

    @app.post("/expression/dance")
    async def dance(request: DanceRequest) -> dict[str, Any]:
        """Simulate dance routine."""
        _mock_state.is_dancing = True

        # Simulate dance duration (capped for testing)
        await asyncio.sleep(min(request.duration_seconds, 2.0))

        _mock_state.is_dancing = False

        return {
            "status": "success",
            "routine": request.routine,
            "duration_seconds": request.duration_seconds,
            "message": f"Completed {request.routine} dance",
        }

    # ========== NEW ENDPOINTS FOR FULL SDK SUPPORT ==========

    @app.post("/body/rotate")
    async def rotate(request: RotateRequest) -> dict[str, Any]:
        """Simulate body rotation."""
        delay_map = {"slow": 0.5, "normal": 0.3, "fast": 0.1}
        await asyncio.sleep(delay_map.get(request.speed, 0.3))

        # Update rotation (accumulate, wrap at 360)
        delta = request.degrees if request.direction == "right" else -request.degrees
        _mock_state.body_rotation = (_mock_state.body_rotation + delta) % 360

        return {
            "status": "success",
            "direction": request.direction,
            "degrees": request.degrees,
            "current_rotation": _mock_state.body_rotation,
            "message": f"Rotated {request.direction} by {request.degrees} degrees",
        }

    @app.post("/head/look_at")
    async def look_at(request: LookAtRequest) -> dict[str, Any]:
        """Simulate precise head positioning."""
        await asyncio.sleep(request.duration)

        _mock_state.head_position = {
            "pitch": request.pitch,
            "yaw": request.yaw,
            "roll": request.roll,
            "z": request.z,
        }

        return {
            "status": "success",
            "position": _mock_state.head_position,
            "duration": request.duration,
            "message": "Head positioned",
        }

    @app.post("/audio/listen")
    async def listen(request: ListenRequest) -> dict[str, Any]:
        """Simulate audio capture."""
        _mock_state.is_listening = True

        # Simulate recording (capped for testing)
        await asyncio.sleep(min(request.duration_seconds, 1.0))

        _mock_state.is_listening = False

        # Return mock audio data (base64-encoded silence)
        import base64

        # Generate mock audio header (WAV format indicator)
        mock_audio = base64.b64encode(b"RIFF" + b"\x00" * 100).decode("utf-8")

        return {
            "status": "success",
            "duration_seconds": request.duration_seconds,
            "format": "wav",
            "sample_rate": 16000,
            "channels": 4,
            "audio_base64": mock_audio,
            "message": f"Recorded {request.duration_seconds}s of audio",
        }

    @app.post("/lifecycle/wake_up")
    async def wake_up() -> dict[str, Any]:
        """Simulate motor initialization."""
        await asyncio.sleep(0.5)  # Simulate startup time

        _mock_state.is_awake = True
        # Reset to neutral position
        _mock_state.head_position = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0, "z": 0.0}
        _mock_state.left_antenna_angle = 45.0
        _mock_state.right_antenna_angle = 45.0

        return {
            "status": "success",
            "is_awake": True,
            "message": "Robot motors initialized and ready",
        }

    @app.post("/lifecycle/sleep")
    async def sleep() -> dict[str, Any]:
        """Simulate motor shutdown."""
        await asyncio.sleep(0.3)  # Simulate shutdown time

        _mock_state.is_awake = False
        _mock_state.is_dancing = False
        _mock_state.is_speaking = False

        return {
            "status": "success",
            "is_awake": False,
            "message": "Robot motors powered down",
        }

    @app.post("/gesture/nod")
    async def nod(request: GestureRequest) -> dict[str, Any]:
        """Simulate nodding gesture."""
        delay_map = {"slow": 0.4, "normal": 0.25, "fast": 0.15}
        nod_delay = delay_map.get(request.speed, 0.25)

        # Simulate nodding motion
        for _ in range(request.times):
            await asyncio.sleep(nod_delay)

        return {
            "status": "success",
            "gesture": "nod",
            "times": request.times,
            "speed": request.speed,
            "message": f"Nodded {request.times} time(s)",
        }

    @app.post("/gesture/shake")
    async def shake(request: GestureRequest) -> dict[str, Any]:
        """Simulate head shake gesture."""
        delay_map = {"slow": 0.4, "normal": 0.25, "fast": 0.15}
        shake_delay = delay_map.get(request.speed, 0.25)

        # Simulate shaking motion
        for _ in range(request.times):
            await asyncio.sleep(shake_delay)

        return {
            "status": "success",
            "gesture": "shake",
            "times": request.times,
            "speed": request.speed,
            "message": f"Shook head {request.times} time(s)",
        }

    @app.post("/gesture/rest")
    async def rest() -> dict[str, Any]:
        """Simulate returning to rest pose."""
        await asyncio.sleep(0.3)

        # Reset to neutral
        _mock_state.head_position = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0, "z": 0.0}
        _mock_state.left_antenna_angle = 45.0
        _mock_state.right_antenna_angle = 45.0
        _mock_state.current_emotion = None

        return {
            "status": "success",
            "position": _mock_state.head_position,
            "left_antenna": _mock_state.left_antenna_angle,
            "right_antenna": _mock_state.right_antenna_angle,
            "message": "Returned to rest pose",
        }

    @app.post("/actions/cancel")
    async def cancel_action(request: CancelActionRequest) -> dict[str, Any]:
        """Simulate canceling an action."""
        return {
            "status": "success",
            "action_id": request.action_id or "all",
            "message": "Action cancelled (mock)",
        }

    @app.get("/pose")
    async def get_pose() -> dict[str, Any]:
        """Get current robot pose."""
        return {
            "status": "success",
            "head": {
                "roll": _mock_state.head_position.get("roll", 0.0),
                "pitch": _mock_state.head_position.get("pitch", 0.0),
                "yaw": _mock_state.head_position.get("yaw", 0.0),
            },
            "body_yaw": 0.0,
            "antennas": {
                "left": _mock_state.left_antenna_angle,
                "right": _mock_state.right_antenna_angle,
            },
            "timestamp": "mock",
        }

    return app


def run_mock_daemon(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the mock daemon server.

    Args:
        host: Host to bind to.
        port: Port to listen on.
    """
    try:
        import uvicorn
    except ImportError as err:
        raise ImportError(
            "uvicorn is required to run the mock daemon. "
            "Install with: pip install uvicorn"
        ) from err

    app = create_mock_daemon_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_mock_daemon()
