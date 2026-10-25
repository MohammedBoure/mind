"""Screen capture and calibrated numbered coordinate grid overlay for Vision LLMs.

This module provides high-performance screen capture tools tailored specifically
for Vision-Language Models (e.g. Gemini Vision, Claude 3.5 Sonnet, GPT-4o) and
autonomous mouse-interaction agents (e.g. NaturaleMouseEvent, mind automation).

Key capabilities:
1. Cross-platform screen capture using `mss` with graceful fallback to `PIL.ImageGrab`
   and a headless mock canvas when running without a physical display server (CI/Docker).
2. Calibrated numbered coordinate grid overlay:
   - Numeric coordinate labels along top (X-axis ruler) and left (Y-axis ruler).
   - Configurable grid lines (minor and major lines with visual hierarchy).
   - High-contrast intersection crosshairs and coordinate badges.
   - 1:1 pixel coordinate calibration matching physical screen geometry.
3. Flexible output encoding: base64 Data URLs, raw base64 strings, or cached image files.
4. Comprehensive display geometry and monitor layout inspection.
"""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import io
import logging
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("mind.mcp.vision_capture")

# Cache for loaded TrueType fonts keyed by size to avoid disk I/O on every frame
_FONT_CACHE: dict[int, ImageFont.ImageFont | ImageFont.FreeTypeFont] = {}

# Candidate system font paths across Linux, macOS, and Windows
_FONT_CANDIDATES: list[str] = [
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/UbuntuMono-B.ttf",
    # macOS
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/Library/Fonts/Arial.ttf",
    # Windows
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]


@dataclass
class MonitorGeometry:
    """Information regarding an individual monitor or display viewport."""

    index: int
    left: int
    top: int
    width: int
    height: int
    is_primary: bool
    name: str = ""


@dataclass
class ScreenGeometry:
    """Overall virtual screen layout and display subsystem state."""

    width: int
    height: int
    monitors: list[dict[str, Any]]
    primary_monitor: int
    is_headless: bool
    display: str | None
    scale_factor: float = 1.0


@dataclass
class GridCalibration:
    """Mathematical mapping and calibration parameters for the visual grid."""

    origin_x: int
    origin_y: int
    step_x: int
    step_y: int
    width: int
    height: int
    scale_factor: float = 1.0
    axes_offset_x: int = 0
    axes_offset_y: int = 0


def _ensure_display_environment() -> str | None:
    """Ensure Linux display environment variables are configured if an X11 socket exists."""
    if not sys.platform.startswith("linux"):
        return os.environ.get("DISPLAY")

    display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    if display:
        return display

    # Auto-detect common local X11 sockets if DISPLAY was omitted in the shell
    for display_num in range(4):
        socket_path = f"/tmp/.X11-unix/X{display_num}"
        if os.path.exists(socket_path):
            auto_display = f":{display_num}"
            os.environ["DISPLAY"] = auto_display
            logger.debug("Auto-configured Linux DISPLAY to %s", auto_display)
            return auto_display

    return None


def get_font(size: int = 12) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Retrieve a cached high-contrast font of the specified pixel size."""
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]

    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                font = ImageFont.truetype(path, size)
                _FONT_CACHE[size] = font
                return font
            except Exception:
                continue

    # Fallback to PIL built-in bitmap font
    fallback = ImageFont.load_default()
    _FONT_CACHE[size] = fallback
    return fallback


def is_display_available() -> bool:
    """Check whether a physical or virtual display server is actively reachable."""
    _ensure_display_environment()
    try:
        import mss

        with mss.MSS() as sct:
            return bool(sct.monitors and len(sct.monitors) > 0)
    except Exception:
        pass

    try:
        from PIL import ImageGrab

        test_img = ImageGrab.grab()
        return test_img is not None and test_img.width > 0
    except Exception:
        return False


def get_screen_geometry() -> dict[str, Any]:
    """Inspect and return current screen dimensions, active monitors, and headless state.

    Returns:
        A dictionary containing overall virtual screen width, height, monitor list,
        primary monitor index, display name, and is_headless flag.
    """
    _ensure_display_environment()
    monitors: list[dict[str, Any]] = []
    width = 1920
    height = 1080
    primary_idx = 1
    is_headless = True
    display_name = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")

    try:
        import mss

        with mss.MSS() as sct:
            all_mons = sct.monitors
            if all_mons:
                is_headless = False
                # Monitor 0 in MSS is the virtual bounding box for all monitors
                total = all_mons[0]
                width = total["width"]
                height = total["height"]

                for idx, m in enumerate(all_mons[1:], start=1):
                    is_prim = bool(m.get("is_primary", idx == 1))
                    if is_prim:
                        primary_idx = idx
                    monitors.append({
                        "index": idx,
                        "left": m["left"],
                        "top": m["top"],
                        "width": m["width"],
                        "height": m["height"],
                        "is_primary": is_prim,
                        "name": m.get("output", f"Monitor-{idx}"),
                    })
    except Exception as exc:
        logger.debug("MSS screen geometry detection failed: %s", exc)

    if not monitors:
        # Fallback to PIL ImageGrab if MSS was unavailable
        try:
            from PIL import ImageGrab

            img = ImageGrab.grab()
            if img:
                is_headless = False
                width, height = img.size
                monitors.append({
                    "index": 1,
                    "left": 0,
                    "top": 0,
                    "width": width,
                    "height": height,
                    "is_primary": True,
                    "name": "Primary Display",
                })
        except Exception:
            pass

    if is_headless or not monitors:
        # Headless virtual display fallback
        is_headless = True
        monitors = [{
            "index": 1,
            "left": 0,
            "top": 0,
            "width": width,
            "height": height,
            "is_primary": True,
            "name": "Headless-Virtual-Display",
        }]

    return asdict(
        ScreenGeometry(
            width=width,
            height=height,
            monitors=monitors,
            primary_monitor=primary_idx,
            is_headless=is_headless,
            display=display_name,
            scale_factor=1.0,
        )
    )


def generate_mock_screen(width: int = 1920, height: int = 1080) -> Image.Image:
    """Generate a realistic simulated desktop canvas for headless testing environments."""
    img = Image.new("RGB", (width, height), color=(15, 23, 42))  # Deep slate (#0f172a)
    draw = ImageDraw.Draw(img)

    title_font = get_font(18)
    body_font = get_font(12)
    small_font = get_font(10)

    # 1. Subtle desktop wallpaper background gradient / accents
    for y in range(0, height, 4):
        ratio = y / max(1, height)
        r = int(15 + ratio * 10)
        g = int(23 + ratio * 12)
        b = int(42 + ratio * 18)
        draw.line([(0, y), (width, y)], fill=(r, g, b), width=4)

    # 2. Simulated Bottom Taskbar
    taskbar_h = 42
    taskbar_top = height - taskbar_h
    draw.rectangle([(0, taskbar_top), (width, height)], fill=(11, 15, 25))
    draw.line([(0, taskbar_top), (width, taskbar_top)], fill=(30, 41, 59), width=1)

    # Start Button & Taskbar Items
    draw.rectangle([(8, taskbar_top + 6), (90, height - 6)], fill=(30, 58, 138))
    draw.text((18, taskbar_top + 13), "⊞ Mind OS", fill=(255, 255, 255), font=body_font)

    draw.rectangle([(100, taskbar_top + 6), (190, height - 6)], fill=(30, 41, 59))
    draw.text((112, taskbar_top + 13), "🖥 Terminal", fill=(203, 213, 225), font=body_font)

    draw.rectangle([(200, taskbar_top + 6), (280, height - 6)], fill=(30, 41, 59))
    draw.text((212, taskbar_top + 13), "🌐 Browser", fill=(203, 213, 225), font=body_font)

    # System Tray
    time_str = time.strftime("%H:%M:%S")
    draw.text((width - 90, taskbar_top + 13), time_str, fill=(226, 232, 240), font=body_font)
    draw.text((width - 230, taskbar_top + 14), "HEADLESS DISPLAY", fill=(56, 189, 248), font=small_font)

    # 3. Simulated Active Application Window
    win_x1 = max(40, int(width * 0.10))
    win_y1 = max(40, int(height * 0.08))
    win_x2 = min(width - 40, int(width * 0.90))
    win_y2 = min(taskbar_top - 30, int(height * 0.88))

    # Window Shadow & Body
    draw.rectangle([(win_x1, win_y1), (win_x2, win_y2)], fill=(17, 24, 39))  # Dark gray (#111827)
    draw.rectangle([(win_x1, win_y1), (win_x2, win_y2)], outline=(51, 65, 85), width=2)

    # Window Titlebar
    titlebar_h = 36
    draw.rectangle([(win_x1, win_y1), (win_x2, win_y1 + titlebar_h)], fill=(30, 41, 59))
    draw.line([(win_x1, win_y1 + titlebar_h), (win_x2, win_y1 + titlebar_h)], fill=(51, 65, 85), width=1)

    # Window Control Buttons (Red, Yellow, Green dots)
    draw.ellipse([(win_x1 + 12, win_y1 + 11), (win_x1 + 24, win_y1 + 23)], fill=(239, 68, 68))
    draw.ellipse([(win_x1 + 30, win_y1 + 11), (win_x1 + 42, win_y1 + 23)], fill=(234, 179, 8))
    draw.ellipse([(win_x1 + 48, win_y1 + 11), (win_x1 + 60, win_y1 + 23)], fill=(34, 197, 94))

    # Window Title Text
    draw.text((win_x1 + 72, win_y1 + 9), "Mind Vision Headless Workspace [Emulated Canvas]", fill=(241, 245, 249), font=title_font)

    # 4. Interactive Target Elements for Vision Agent Testing
    content_y = win_y1 + titlebar_h + 20

    # Search Bar Target
    sb_x1 = win_x1 + 30
    sb_y1 = content_y
    sb_x2 = sb_x1 + 400
    sb_y2 = sb_y1 + 36
    draw.rectangle([(sb_x1, sb_y1), (sb_x2, sb_y2)], fill=(30, 41, 59), outline=(71, 85, 105), width=1)
    draw.text((sb_x1 + 12, sb_y1 + 10), "🔍 Search coordinates or commands...", fill=(148, 163, 184), font=body_font)

    # Action Buttons Targets
    btn1_x1 = sb_x2 + 20
    btn1_y1 = sb_y1
    btn1_x2 = btn1_x1 + 130
    btn1_y2 = sb_y2
    draw.rectangle([(btn1_x1, btn1_y1), (btn1_x2, btn1_y2)], fill=(16, 185, 129))  # Emerald
    draw.text((btn1_x1 + 16, btn1_y1 + 10), "▶ Start Task", fill=(255, 255, 255), font=body_font)

    btn2_x1 = btn1_x2 + 12
    btn2_y1 = sb_y1
    btn2_x2 = btn2_x1 + 110
    btn2_y2 = sb_y2
    draw.rectangle([(btn2_x1, btn2_y1), (btn2_x2, btn2_y2)], fill=(217, 119, 6))  # Amber
    draw.text((btn2_x1 + 16, btn2_y1 + 10), "⚙ Settings", fill=(255, 255, 255), font=body_font)

    # Simulated Terminal Display Area inside window
    term_x1 = win_x1 + 30
    term_y1 = sb_y2 + 24
    term_x2 = win_x2 - 30
    term_y2 = win_y2 - 24
    draw.rectangle([(term_x1, term_y1), (term_x2, term_y2)], fill=(10, 15, 26), outline=(30, 41, 59), width=1)

    term_lines = [
        "[INFO] Virtual headless display server operational.",
        "[INFO] Resolution: 1920x1080, Color depth: 24-bit TrueColor.",
        "[MIND-MCP] Screen vision capture and coordinate grid overlay ready.",
        "[VISION-AGENT] Locate elements by referencing the numbered axes and intersection tags.",
        "[STATUS] Ready for automated mouse actions (natural_mouse_move, natural_mouse_click).",
    ]
    cur_y = term_y1 + 16
    for line in term_lines:
        color = (56, 189, 248) if "INFO" in line else ((163, 230, 53) if "MIND-MCP" in line else (203, 213, 225))
        draw.text((term_x1 + 16, cur_y), line, fill=color, font=body_font)
        cur_y += 24

    # Notice Watermark Badge
    banner_w = 460
    banner_h = 28
    bx1 = (width - banner_w) // 2
    by1 = 10
    draw.rectangle([(bx1, by1), (bx1 + banner_w, by1 + banner_h)], fill=(220, 38, 38))
    draw.text((bx1 + 14, by1 + 6), "⚠ HEADLESS DISPLAY FALLBACK — NO PHYSICAL MONITOR ATTACHED", fill=(255, 255, 255), font=body_font)

    return img


def capture_raw_screen(
    monitor_index: int = 0,
    bbox: tuple[int, int, int, int] | None = None,
) -> tuple[Image.Image, bool, dict[str, Any]]:
    """Capture raw frame buffer from screen or generate headless fallback.

    Args:
        monitor_index: Monitor index (0 = virtual desktop / all screens, 1 = primary, etc.).
        bbox: Optional crop region (left, top, right, bottom).

    Returns:
        A tuple of (PIL RGB Image, is_headless boolean, monitor_metadata dictionary).
    """
    _ensure_display_environment()

    # Strategy 1: Fast cross-platform capture with mss
    try:
        import mss

        with mss.MSS() as sct:
            monitors = sct.monitors
            if monitors:
                target_mon = monitors[0]  # default all monitors
                if 0 <= monitor_index < len(monitors):
                    target_mon = monitors[monitor_index]

                raw = sct.grab(target_mon)
                # Convert raw MSS BGRA bytes to PIL RGB Image
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                if bbox:
                    img = img.crop(bbox)

                meta = {
                    "monitor_index": monitor_index,
                    "width": img.width,
                    "height": img.height,
                    "left": target_mon.get("left", 0),
                    "top": target_mon.get("top", 0),
                    "backend": "mss",
                }
                return img, False, meta
    except Exception as exc:
        logger.debug("mss screen capture failed or unavailable: %s", exc)

    # Strategy 2: Fallback to PIL ImageGrab
    try:
        from PIL import ImageGrab

        all_screens = monitor_index == 0
        img = ImageGrab.grab(bbox=bbox, all_screens=all_screens)
        if img:
            meta = {
                "monitor_index": monitor_index,
                "width": img.width,
                "height": img.height,
                "left": 0,
                "top": 0,
                "backend": "PIL.ImageGrab",
            }
            return img.convert("RGB"), False, meta
    except Exception as exc:
        logger.debug("PIL.ImageGrab failed or unavailable: %s", exc)

    # Strategy 3: Headless mock canvas fallback
    logger.info("Using headless virtual canvas fallback for screen capture.")
    fallback_w = 1920
    fallback_h = 1080
    if bbox:
        fallback_w = max(100, bbox[2] - bbox[0])
        fallback_h = max(100, bbox[3] - bbox[1])

    mock_img = generate_mock_screen(width=fallback_w, height=fallback_h)
    meta = {
        "monitor_index": monitor_index,
        "width": fallback_w,
        "height": fallback_h,
        "left": 0,
        "top": 0,
        "backend": "headless_mock",
    }
    return mock_img, True, meta


def draw_coordinate_grid(
    image: Image.Image,
    grid_step: int = 100,
    show_axes: bool = True,
    show_labels: bool = True,
    show_intersections: bool = True,
    show_badges: bool = True,
    badge_interval_factor: int = 2,
) -> tuple[Image.Image, dict[str, Any]]:
    """Draw a calibrated numbered coordinate grid overlay across the image.

    The coordinate grid is rendered directly on top of the screen capture with 1:1 pixel
    precision, allowing Vision-Language Models to reliably extract exact (x, y) coordinates.

    Args:
        image: Base PIL Image.
        grid_step: Distance in pixels between grid lines (clamped to 20 <= step <= 500).
        show_axes: Render coordinate rulers with numeric labels along top and left borders.
        show_labels: Whether to render coordinate numeric labels.
        show_intersections: Render subtle crosshair marks (+) at grid intersections.
        show_badges: Render readable (x, y) coordinate pill badges at major intersections.
        badge_interval_factor: Interval multiplier for badge placement (e.g. 2 = every 2*grid_step).

    Returns:
        A tuple of (gridded PIL Image in RGB mode, calibration_metadata dictionary).
    """
    width, height = image.size

    # Validate and clamp grid_step
    step = max(20, min(grid_step, max(width, height) // 2))

    # Create RGBA overlay for alpha-blended rendering
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    # Fonts
    axis_font = get_font(12)
    badge_font = get_font(10)
    origin_font = get_font(11)

    # Visual style configuration
    minor_line_color = (0, 220, 255, 55)       # Cyan semi-transparent (1px)
    major_line_color = (0, 245, 255, 120)      # Bright cyan (2px)
    crosshair_color = (255, 255, 255, 130)     # White subtle crosshair
    badge_bg = (15, 23, 42, 205)               # Dark navy translucent pill
    badge_text = (255, 235, 59, 240)           # Bright yellow text
    axis_bg = (15, 23, 42, 230)                # Dark navy axis ribbon
    axis_border = (0, 220, 255, 220)           # Cyan ruler edge
    axis_text = (255, 255, 255, 245)           # White ruler text

    # Dimensions for axis rulers
    top_ruler_h = 26 if show_axes else 0
    left_ruler_w = 44 if show_axes else 0

    # 1. Subtle Grid Lines (Minor and Major)
    # Vertical lines (X coordinates)
    for x in range(step, width, step):
        is_major = (x % (step * 5) == 0) or (x % 500 == 0)
        line_color = major_line_color if is_major else minor_line_color
        line_w = 2 if is_major else 1
        draw.line([(x, top_ruler_h), (x, height)], fill=line_color, width=line_w)

    # Horizontal lines (Y coordinates)
    for y in range(step, height, step):
        is_major = (y % (step * 5) == 0) or (y % 500 == 0)
        line_color = major_line_color if is_major else minor_line_color
        line_w = 2 if is_major else 1
        draw.line([(left_ruler_w, y), (width, y)], fill=line_color, width=line_w)

    # 2. Intersection Crosshairs (+)
    if show_intersections:
        cross_len = 4
        for x in range(step, width, step):
            for y in range(step, height, step):
                draw.line([(x - cross_len, y), (x + cross_len, y)], fill=crosshair_color, width=1)
                draw.line([(x, y - cross_len), (x, y + cross_len)], fill=crosshair_color, width=1)

    # 3. Intersection Coordinate Badges
    if show_badges and show_labels:
        badge_step = step * max(1, badge_interval_factor)
        for x in range(badge_step, width - 40, badge_step):
            for y in range(badge_step, height - 30, badge_step):
                label = f"{x},{y}"
                bbox = draw.textbbox((0, 0), label, font=badge_font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]

                # Position badge slightly offset from intersection point
                bx1 = x + 4
                by1 = y + 4
                bx2 = bx1 + tw + 6
                by2 = by1 + th + 4

                # Ensure within canvas boundaries
                if bx2 < width and by2 < height:
                    draw.rectangle([(bx1, by1), (bx2, by2)], fill=badge_bg)
                    draw.text((bx1 + 3, by1 + 1), label, fill=badge_text, font=badge_font)

    # 4. Numbered Axes Rulers (Top X-Axis, Left Y-Axis)
    if show_axes:
        # Top Ruler Background Ribbon
        draw.rectangle([(0, 0), (width, top_ruler_h)], fill=axis_bg)
        draw.line([(0, top_ruler_h), (width, top_ruler_h)], fill=axis_border, width=1)

        # Left Ruler Background Ribbon
        draw.rectangle([(0, 0), (left_ruler_w, height)], fill=axis_bg)
        draw.line([(left_ruler_w, 0), (left_ruler_w, height)], fill=axis_border, width=1)

        # Origin Box (0,0)
        draw.rectangle([(0, 0), (left_ruler_w, top_ruler_h)], fill=(11, 15, 25, 245))
        draw.text((6, 6), "(0,0)", fill=(0, 240, 255, 255), font=origin_font)

        # X-Axis Ticks & Coordinate Labels
        for x in range(step, width, step):
            # Full tick at grid line
            draw.line([(x, 0), (x, top_ruler_h)], fill=axis_border, width=1)

            # Half-step minor tick
            half_x = x - (step // 2)
            if half_x > left_ruler_w:
                draw.line([(half_x, top_ruler_h - 7), (half_x, top_ruler_h)], fill=axis_border, width=1)

            if show_labels:
                label = str(x)
                bbox = draw.textbbox((0, 0), label, font=axis_font)
                tw = bbox[2] - bbox[0]
                tx = max(left_ruler_w + 2, x - (tw // 2))
                if tx + tw < width:
                    draw.text((tx, 6), label, fill=axis_text, font=axis_font)

        # Y-Axis Ticks & Coordinate Labels
        for y in range(step, height, step):
            # Full tick at grid line
            draw.line([(0, y), (left_ruler_w, y)], fill=axis_border, width=1)

            # Half-step minor tick
            half_y = y - (step // 2)
            if half_y > top_ruler_h:
                draw.line([(left_ruler_w - 7, half_y), (left_ruler_w, half_y)], fill=axis_border, width=1)

            if show_labels:
                label = str(y)
                bbox = draw.textbbox((0, 0), label, font=axis_font)
                tw = bbox[2] - bbox[0]
                ty = max(top_ruler_h + 2, y - 7)
                tx = max(2, left_ruler_w - tw - 4)
                if ty + 12 < height:
                    draw.text((tx, ty), label, fill=axis_text, font=axis_font)

    # Composite alpha overlay onto base image
    base_rgba = image.convert("RGBA")
    composite = Image.alpha_composite(base_rgba, overlay)
    result_image = composite.convert("RGB")

    calibration = asdict(
        GridCalibration(
            origin_x=0,
            origin_y=0,
            step_x=step,
            step_y=step,
            width=width,
            height=height,
            scale_factor=1.0,
            axes_offset_x=0,
            axes_offset_y=0,
        )
    )

    return result_image, calibration


def encode_vision_capture(
    image: Image.Image,
    calibration: dict[str, Any],
    output_format: str = "base64",
    image_format: str = "jpeg",
    quality: int = 85,
    output_path: str | None = None,
    is_headless: bool = False,
    monitor_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Encode the captured gridded image into base64 or save to a cached file.

    Args:
        image: Gridded PIL Image.
        calibration: Coordinate calibration dictionary.
        output_format: Desired output type ('base64', 'file', 'path', or 'both').
        image_format: Image file format ('jpeg' or 'png').
        quality: Compression quality (1-100, applied to JPEG).
        output_path: Custom file path for saving when output_format involves file output.
        is_headless: Whether headless emulation was used.
        monitor_meta: Hardware monitor metadata.

    Returns:
        Structured result dictionary for MCP tool response.
    """
    fmt = image_format.lower()
    if fmt in ("jpg", "jpeg"):
        pil_format = "JPEG"
        mime_type = "image/jpeg"
    else:
        pil_format = "PNG"
        mime_type = "image/png"

    q = max(10, min(100, quality))
    width, height = image.size

    result: dict[str, Any] = {
        "success": True,
        "width": width,
        "height": height,
        "grid_step": calibration.get("step_x", 100),
        "format": pil_format.lower(),
        "mime_type": mime_type,
        "calibration": calibration,
        "is_headless": is_headless,
        "timestamp": time.time(),
    }
    if monitor_meta:
        result["monitor"] = monitor_meta

    norm_output = output_format.lower().strip()

    # 1. Handle File Output
    saved_path: str | None = None
    if norm_output in ("file", "path", "both"):
        if output_path:
            target_path = Path(output_path).expanduser().resolve()
            target_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            cache_dir = Path(tempfile.gettempdir()) / "mind_captures"
            cache_dir.mkdir(parents=True, exist_ok=True)
            filename = f"screen_grid_{int(time.time() * 1000)}.{pil_format.lower()}"
            target_path = cache_dir / filename

        save_kwargs: dict[str, Any] = {}
        if pil_format == "JPEG":
            save_kwargs["quality"] = q
            save_kwargs["optimize"] = True

        image.save(target_path, format=pil_format, **save_kwargs)
        saved_path = str(target_path)
        result["file_path"] = saved_path
        result["file_size_bytes"] = target_path.stat().st_size

    # 2. Handle Base64 Output
    if norm_output in ("base64", "both") or saved_path is None:
        buffer = io.BytesIO()
        save_kwargs = {}
        if pil_format == "JPEG":
            save_kwargs["quality"] = q
            save_kwargs["optimize"] = True

        image.save(buffer, format=pil_format, **save_kwargs)
        image_bytes = buffer.getvalue()
        b64_str = base64.b64encode(image_bytes).decode("ascii")

        result["base64"] = b64_str
        result["data_url"] = f"data:{mime_type};base64,{b64_str}"
        result["byte_size"] = len(image_bytes)

    return result


def capture_screen_with_grid(
    grid_step: int = 100,
    show_axes: bool = True,
    output_format: str = "base64",
    quality: int = 85,
    monitor: int = 0,
    image_format: str = "jpeg",
    show_badges: bool = True,
    show_intersections: bool = True,
    output_path: str | None = None,
    bbox: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    """Capture screen frame, render calibrated numbered coordinate grid, and return encoded result.

    High-level entrypoint used by the MCP server and external agents.

    Args:
        grid_step: Pixel distance between grid lines (default: 100).
        show_axes: Render coordinate rulers along top (X) and left (Y) borders (default: True).
        output_format: 'base64', 'file', or 'both' (default: 'base64').
        quality: JPEG compression quality (1-100, default: 85).
        monitor: Monitor index (0 = entire virtual desktop, 1 = primary monitor, 2 = secondary).
        image_format: Image file format ('jpeg' or 'png', default: 'jpeg').
        show_badges: Place readable (x, y) coordinate badges at major intersections (default: True).
        show_intersections: Render crosshair marks (+) at grid intersections (default: True).
        output_path: Optional destination file path when saving to disk.
        bbox: Optional crop region (left, top, right, bottom).

    Returns:
        Structured dictionary containing encoded image, calibration metadata, and screen geometry.
    """
    raw_img, is_headless, monitor_meta = capture_raw_screen(monitor_index=monitor, bbox=bbox)

    gridded_img, calibration = draw_coordinate_grid(
        image=raw_img,
        grid_step=grid_step,
        show_axes=show_axes,
        show_labels=True,
        show_intersections=show_intersections,
        show_badges=show_badges,
    )

    return encode_vision_capture(
        image=gridded_img,
        calibration=calibration,
        output_format=output_format,
        image_format=image_format,
        quality=quality,
        output_path=output_path,
        is_headless=is_headless,
        monitor_meta=monitor_meta,
    )
