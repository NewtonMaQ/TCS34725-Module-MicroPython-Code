# TCS34725 LED Color Scanner

A lightweight MicroPython script for identifying the color of an LED using the **TCS34725** RGB color sensor. It's built specifically for LEDs that **cycle through a sequence of colors on a button press** (blinking through each color once), rather than sitting on a single steady color — the scanner samples fast and confirms a color only once it's been read consistently, so it doesn't get fooled by the brief color blends that happen mid-transition between blinks.

## Features

- Direct I2C register access — no external sensor library required
- Fast sampling (~24ms integration time) tuned to catch short, sequential blinks
- Debounced color detection — reports each blink once, ignoring transitional color blends
- HSV-based color classification (more robust than raw RGB thresholding)
- Channel calibration to correct for the sensor's uneven R/G/B sensitivity
- Built-in diagnostic tools for tuning thresholds and calibration to your own hardware

## Hardware

- A microcontroller running MicroPython (tested with Raspberry Pi Pico, ESP32)
- Adafruit TCS34725 (or compatible) color sensor breakout
- An LED (or LED module) that cycles through colors, e.g. on a button press

### Wiring

| Board            | I2C Bus | SDA    | SCL    |
|-------------------|---------|--------|--------|
| Raspberry Pi Pico | 0       | GP4    | GP5    |
| ESP32             | 1       | GPIO21 | GPIO22 |

Update the pin assignments in the script if your wiring differs.

## Installation

1. Flash MicroPython onto your board if you haven't already.
2. Copy `color_scanner.py` onto the board (e.g. via `mpremote`, `ampy`, or the Thonny IDE).
3. Wire the TCS34725 sensor to the I2C pins listed above (plus power and ground).
4. Position the sensor so it points directly at the LED.
5. Run the script:
   ```bash
   mpremote run color_scanner.py
   ```
   or open it in Thonny and press Run.

## Usage

Trigger your LED's color cycle (e.g. press its button), and the scanner will print each detected color once as it blinks past:

```
Initializing TCS34725 sensor...
Scanner running. Waiting for LED blinks. Press Ctrl+C to stop.

Detected: RED
Ratio -> R: 68% | G: 18% | B: 14% | C: 812
--------------------------------------------------
Detected: GREEN
Ratio -> R: 15% | G: 70% | B: 15% | C: 790
--------------------------------------------------
Detected: BLUE
Ratio -> R: 12% | G: 20% | B: 68% | C: 745
--------------------------------------------------
```

Press `Ctrl+C` to stop the scanner cleanly.

## Calibration

The TCS34725's Red, Green, and Blue photodiodes have different spectral sensitivities, so raw readings under the same light are rarely balanced — this shows up as colors (especially white and magenta) reading with an incorrect hue. The script corrects for this with `CAL_R` / `CAL_G` / `CAL_B` multipliers near the top of the file.

**These have already been calibrated for this project's hardware:**

```python
CAL_R = 1.756
CAL_G = 1.025
CAL_B = 1.000
```

These were measured by pointing the sensor at this project's white LED and running the built-in `auto_calibrate_white()` helper, which samples the raw R/G/B channels and computes multipliers that balance them so white reads as (roughly) equal R, G, and B.

If you swap sensors, swap LEDs, or start seeing white/magenta misclassify again, re-calibrate:

1. Near the bottom of the script, replace `main()` with:
   ```python
   init_sensor()
   auto_calibrate_white()
   ```
2. Point the sensor at your white light source and run the script.
3. It will print something like:
   ```
   Raw averages -> R:410.2 G:590.5 B:602.1

   Copy these into the CAL_R / CAL_G / CAL_B constants above:
   CAL_R = 1.468
   CAL_G = 1.020
   CAL_B = 1.000
   ```
4. Copy the printed values into `CAL_R` / `CAL_G` / `CAL_B` at the top of the file, and switch back to `main()`.

## Configuration

Key tunable constants near the top of the script:

- **`CAL_R` / `CAL_G` / `CAL_B`** — channel calibration multipliers (see above).
- **`DARK_THRESHOLD`** — minimum clear-channel value before a reading counts as "off." Currently `40`, tuned for a fast 24ms integration time. Lower it if dim colors (e.g. red/green) are misread as off; raise it if ambient room light triggers false detections.
- **`WHITE_SATURATION_THRESHOLD`** — saturation below this is classified as white. Currently `35`, since real white LEDs are rarely perfectly neutral.
- **Hue windows** in `identify_led_color()` — adjust these if a specific color still misclassifies; run `calibrate_mode()` (see below) to see the real hue values your LEDs produce and match the windows to them.
- **Gain** (`REG_CONTROL` in `init_sensor()`) — currently 16x, chosen to compensate for the short integration time. Increase further (`0x03` = 60x) if colors are still too dim/noisy; decrease if readings saturate (e.g. very bright LEDs at close range).
- **`STABLE_SAMPLES`** / **`POLL_INTERVAL`** in `main()` — control how many consecutive matching samples are needed to confirm a blink, and how often the sensor is polled. If your LED's blinks are faster or slower than expected, tune these so `POLL_INTERVAL * STABLE_SAMPLES` stays comfortably shorter than one blink's duration.

## Diagnostic Modes

Two helper functions are included for troubleshooting (call `init_sensor()` first, then swap in place of `main()`):

- **`calibrate_mode()`** — continuously prints raw R/G/B/Clear values and the computed Hue/Saturation, so you can watch how a specific LED color actually reads on your hardware and adjust the hue windows accordingly.
- **`auto_calibrate_white()`** — one-shot routine that measures and prints new `CAL_R`/`CAL_G`/`CAL_B` values from a white light source (see Calibration above).

## How It Works

1. `init_sensor()` powers on the TCS34725 with a short integration time (fast sampling) and boosted gain (to compensate for the shorter integration time) over I2C.
2. `main()` samples the sensor roughly every 30ms. Each raw reading is classified via `identify_led_color()`, but a color is only "confirmed" and printed once it's been read the same way for `STABLE_SAMPLES` consecutive samples — filtering out the brief color blends that occur as the LED fades from one color to the next.
3. `calculate_hsv()` converts raw RGB into Hue and Saturation (after applying calibration), which is more reliable than raw RGB for classifying color under varying brightness.
4. `identify_led_color()` maps the Hue/Saturation values to a color label, using widened hue windows to tolerate real-world LEDs that don't sit at textbook-perfect hue angles.

## License

MIT — feel free to use, modify, and share.
