# RGB Keyboard firmware for Raspberry Pi Pico 2 (SC1631)
# Runtime: MicroPython
#
# Hardware pins taken from the EasyEDA Pro schematic:
#   Matrix columns: GP0-GP15, GP16-GP18 (COL-1 through COL-19)
#   Matrix rows:    GP19, GP20, GP21, GP22, GP26, GP27 (ROW-1 through ROW-6)
#   WS2812B data:   GP28 (LED_DIN)
#
# IMPORTANT:
# The matrix GPIO assignments above come from the schematic. The LED count and
# physical WS2812B chain order should be verified against the finished PCB before
# relying on the animation. The default LED map below assumes a simple row-major
# LED order; if the PCB daisy-chain order differs, update KEY_LED for the wave
# to appear at the correct physical keys.
#
# Install/save this as main.py on the Pico 2.
# Uses the built-in MicroPython machine/neopixel modules.

from machine import Pin
import neopixel
import time
import math

# ---------------- Hardware configuration ----------------

COL_PINS = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9,
    10, 11, 12, 13, 14, 15, 16, 17, 18
]  # COL-1 ... COL-19

ROW_PINS = [19, 20, 21, 22, 26, 27]  # ROW-1 ... ROW-6
LED_PIN = 28                           # LED_DIN

# Change this to the actual number of WS2812B LEDs on the PCB.
# The EasyEDA board image appears to have roughly a keyboard's worth, but the
# exact count should be confirmed from the PCB/component list.
NUM_LEDS = 104

# LED brightness, 0.0 to 1.0. Start low to limit current.
BRIGHTNESS = 0.18

# Wave tuning
WAVE_SPEED = 0.010       # seconds between animation frames
WAVE_WIDTH = 1.35        # larger = wider, softer ring
WAVE_RADIUS_STEP = 0.75  # grid units per frame
HOLD_AT_PEAK = 0.10      # seconds to hold each LED at full white
FADE_STEPS = 7

# ---------------- Keyboard matrix ----------------

# Assumes each switch/diode conducts when its selected row is driven LOW and
# the corresponding column is read LOW. If no keys register, diode orientation
# may require reversing the row/column scan logic.
rows = [Pin(p, Pin.OPEN_DRAIN, value=1) for p in ROW_PINS]
cols = [Pin(p, Pin.IN, Pin.PULL_UP) for p in COL_PINS]

def scan_keys():
    """Return a set of (row_index, col_index) positions currently held."""
    pressed = set()

    # Keep all rows inactive, then select one row at a time.
    for row in rows:
        row.value(1)

    for r, row in enumerate(rows):
        row.value(0)
        time.sleep_us(80)

        for c, col in enumerate(cols):
            if col.value() == 0:
                pressed.add((r, c))

        row.value(1)

    return pressed

# ---------------- LED layout / key mapping ----------------

pixels = neopixel.NeoPixel(Pin(LED_PIN, Pin.OUT), NUM_LEDS)

def make_default_key_led_map():
    """
    Default placeholder mapping: matrix position -> LED index, row-major.
    -1 means there is no LED assigned to that matrix position.
    Replace this function with the actual physical LED order for your PCB.
    """
    mapping = {}
    led = 0
    for r in range(len(ROW_PINS)):
        for c in range(len(COL_PINS)):
            if led < NUM_LEDS:
                mapping[(r, c)] = led
                led += 1
            else:
                mapping[(r, c)] = -1
    return mapping

KEY_LED = make_default_key_led_map()

def build_led_coordinates():
    """
    Assign each mapped LED a keyboard-grid coordinate. This lets the wave
    spread outward by physical key position rather than by LED-chain order.
    """
    coords = {}
    for (r, c), led in KEY_LED.items():
        if led >= 0:
            coords[led] = (float(c), float(r))
    return coords

LED_COORDS = build_led_coordinates()

def set_all(rgb):
    color = tuple(int(max(0, min(255, channel * BRIGHTNESS))) for channel in rgb)
    for i in range(NUM_LEDS):
        pixels[i] = color
    pixels.write()

def clear():
    set_all((0, 0, 0))

def show_colors(colors):
    for i in range(NUM_LEDS):
        rgb = colors.get(i, (0, 0, 0))
        pixels[i] = tuple(
            int(max(0, min(255, channel * BRIGHTNESS))) for channel in rgb
        )
    pixels.write()

def white_wave(key_position):
    """Animate a white wave outward from the pressed key."""
    led_index = KEY_LED.get(key_position, -1)
    if led_index < 0 or led_index not in LED_COORDS:
        return

    origin = LED_COORDS[led_index]
    distances = {}
    max_distance = 0.0

    for i, (x, y) in LED_COORDS.items():
        # Slightly compress horizontal distance to account for keyboard aspect.
        distance = math.sqrt(((x - origin[0]) * 0.85) ** 2 + (y - origin[1]) ** 2)
        distances[i] = distance
        if distance > max_distance:
            max_distance = distance

    radius = 0.0
    while radius <= max_distance + WAVE_WIDTH:
        frame = {}
        for i, distance in distances.items():
            delta = abs(distance - radius)
            # Bright ring with a soft falloff.
            intensity = max(0.0, 1.0 - delta / WAVE_WIDTH)
            intensity = intensity * intensity
            value = int(255 * intensity)
            frame[i] = (value, value, value)

        # Keep the pressed key itself bright as the wave begins.
        if radius < WAVE_WIDTH:
            frame[led_index] = (255, 255, 255)

        show_colors(frame)
        time.sleep(WAVE_SPEED)
        radius += WAVE_RADIUS_STEP

    # Short white hold, then fade everything to black.
    show_colors({i: (255, 255, 255) for i in distances})
    time.sleep(HOLD_AT_PEAK)

    for step in range(FADE_STEPS, -1, -1):
        level = int(255 * step / FADE_STEPS)
        show_colors({i: (level, level, level) for i in distances})
        time.sleep(0.025)

    clear()

# ---------------- Main loop / debounce ----------------

DEBOUNCE_MS = 22
last_seen = set()
last_change_ms = {}
stable_state = set()

clear()

while True:
    now = time.ticks_ms()
    current = scan_keys()

    # Debounce each key independently.
    all_positions = last_seen | current | stable_state
    for pos in all_positions:
        if (pos in current) != (pos in last_seen):
            last_change_ms[pos] = now

        if time.ticks_diff(now, last_change_ms.get(pos, now)) >= DEBOUNCE_MS:
            if pos in current:
                stable_state.add(pos)
            else:
                stable_state.discard(pos)

    # Trigger only on a new press, not continuously while held.
    new_presses = stable_state - getattr(scan_keys, "_previous_stable", set())
    scan_keys._previous_stable = set(stable_state)

    last_seen = current

    # If several keys are pressed together, animate each in sequence.
    for key in sorted(new_presses):
        white_wave(key)

    time.sleep_ms(2)
