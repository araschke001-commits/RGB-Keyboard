# Firmware for Raspberry Pi Pico 2 SC1631

from machine import Pin
import neopixel
import time
import math

# Pin assignmentes on pico
COL_PINS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]
ROW_PINS = [19, 20, 21, 22, 26, 27]
LED_PIN = 28

NUM_LEDS = 104
BRIGHTNESS = 0.18

WAVE_SPEED = 0.010       # seconds between animation frames
WAVE_WIDTH = 1.35        # larger = wider, softer ring
WAVE_RADIUS_STEP = 0.75  # grid units per frame
HOLD_AT_PEAK = 0.10      # seconds to hold each LED at full white
FADE_STEPS = 7

rows = [Pin(p, Pin.OPEN_DRAIN, value=1) for p in ROW_PINS]
cols = [Pin(p, Pin.IN, Pin.PULL_UP) for p in COL_PINS]

def scanKeys():
    # return (row index, column index) positions being read
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


pixels = neopixel.NeoPixel(Pin(LED_PIN, Pin.OUT), NUM_LEDS)

def makeMap():
    # Default = matrix position -> LED index (-1 = no LED assigned) (I'll change this later to teh actual order)
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

KEY_LED = makeMap()

def makeCoords():
    # Asigns each LED a keyboard-grid coordinate (allows wave to work)
    coords = {}
    for (r, c), led in KEY_LED.items():
        if led >= 0:
            coords[led] = (float(c), float(r))
    return coords

LED_COORDS = makeCoords()

def setAll(rgb):
    color = tuple(int(max(0, min(255, channel * BRIGHTNESS))) for channel in rgb)
    for i in range(NUM_LEDS):
        pixels[i] = color
    pixels.write()

def clear():
    setAll((0, 0, 0))

def showColors(colors):
    for i in range(NUM_LEDS):
        rgb = colors.get(i, (0, 0, 0))
        pixels[i] = tuple(int(max(0, min(255, channel * BRIGHTNESS))) for channel in rgb)
    pixels.write()


def whiteWave(keyPos):
    # Make a wave outward from the pressed key.
    led_index = KEY_LED.get(keyPos, -1)
    if led_index < 0 or led_index not in LED_COORDS:
        return

    origin = LED_COORDS[led_index]
    distances = {}
    max_distance = 0.0

    for i, (x, y) in LED_COORDS.items():
        # Compress x distance for keyboard aspect diff.
        distance = math.sqrt(((x - origin[0]) * 0.85) ** 2 + (y - origin[1]) ** 2)
        distances[i] = distance
        if distance > max_distance:
            max_distance = distance

    radius = 0.0
    while radius <= max_distance + WAVE_WIDTH:
        frame = {}
        for i, distance in distances.items():
            delta = abs(distance - radius)
            # Bright ring with a soft fall afterwards
            intensity = max(0.0, 1.0 - delta / WAVE_WIDTH)
            intensity = intensity * intensity
            value = int(255 * intensity)
            frame[i] = (value, value, value)

        # Keep the pressed key bright during start of wave
        if radius < WAVE_WIDTH:
            frame[led_index] = (255, 255, 255)

        showColors(frame)
        time.sleep(WAVE_SPEED)
        radius += WAVE_RADIUS_STEP

    # Short white hold, then fade everything to black.
    showColors({i: (255, 255, 255) for i in distances})
    time.sleep(HOLD_AT_PEAK)

    for step in range(FADE_STEPS, -1, -1):
        level = int(255 * step / FADE_STEPS)
        showColors({i: (level, level, level) for i in distances})
        time.sleep(0.025)

    clear()


### Debouncing & main loop ###

DEBOUNCE_MS = 22
lastSeen = set()
lastMSChange = {}
stableState = set()

clear()

while True:
    now = time.ticks_ms()
    current = scanKeys()

    # Debounce each key
    allPositions = last_seen | current | stableState
    for pos in allPositions:
        if (pos in current) != (pos in last_seen):
            lastMSChange[pos] = now

        if time.ticks_diff(now, lastMSChange.get(pos, now)) >= DEBOUNCE_MS:
            if pos in current:
                stableState.add(pos)
            else:
                stableState.discard(pos)

    # Trigger only on new press (don't keep triggereing when preseed)
    new_presses = stableState - getattr(scanKeys, "_previous_stable", set())
    scanKeys._previous_stable = set(stableState)

    last_seen = current

    # If multiple keys pressed together, wave each in sequence.
    for key in sorted(new_presses):
        whiteWave(key)

    time.sleep_ms(2)