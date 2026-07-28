import time
from machine import Pin, I2C

# 1. Initialize I2C (Adjust pins based on your specific micro-controller board)
# For Raspberry Pi Pico: Bus 0, SDA=GP4, SCL=GP5
# For ESP32: Bus 1, SDA=GPIO21, SCL=GPIO22
i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=100000)

# 2. TCS34725 Constants
TCS34725_ADDR = 0x29        # Standard I2C address
CMD_BIT = 0x80               # Required bit for command registers
REG_ENABLE = 0x00            # Enable register
REG_ATIME = 0x01             # Integration time register
REG_CONTROL = 0x0F           # Gain control register
REG_CDATAL = 0x14            # Clear data low byte register

# 3. Known LED Reference Library (R, G, B on a 0-255 scale)
COLOR_LIBRARY = {
    "Red": (255, 0, 0),
    "Green": (0, 255, 0),
    "Blue": (0, 0, 255),
    "Yellow": (255, 230, 0),
    "Cyan": (0, 255, 255),
    "Magenta": (255, 0, 255),
    "Orange": (255, 120, 0),
    "Purple": (128, 0, 128),
    "White": (255, 255, 255),
    "Off / Dark": (0, 0, 0)
}


# 4. Sensor Initialization Functions
def write_reg(reg, value):
    """Writes a byte to a specific sensor register."""
    i2c.writeto_mem(TCS34725_ADDR, CMD_BIT | reg, bytes([value]))


def read_reg_words(reg, count):
    """Reads multiple 16-bit words from registers."""
    data = i2c.readfrom_mem(TCS34725_ADDR, CMD_BIT | reg, count * 2)
    words = []
    for i in range(count):
        low = data[i * 2]
        high = data[i * 2 + 1]
        words.append((high << 8) | low)
    return words


def init_sensor():
    """Powers on the sensor and sets default gain and time configurations."""
    # Integration time: 0xF6 = ~24ms, kept short so sampling can keep up with
    # quick sequential blinks. A short integration time collects roughly 6x
    # fewer photons per reading than the original 154ms setting, though, so
    # gain is raised from 4x to 16x here to compensate -- otherwise dimmer
    # colors (commonly red and green) can fall below DARK_THRESHOLD or get
    # noisy enough that their hue never settles for STABLE_SAMPLES in a row.
    write_reg(REG_ATIME, 0xF6)
    write_reg(REG_CONTROL, 0x02)  # Gain: 16x (was 4x)
    write_reg(REG_ENABLE, 0x01)   # Power ON
    time.sleep(0.003)
    write_reg(REG_ENABLE, 0x01 | 0x02)  # Power ON + RGBC ADC enable
    time.sleep(0.03)  # let the first (short) integration cycle complete


# 5. Channel Calibration
# The TCS34725's R/G/B photodiodes have different spectral sensitivities, so raw
# readings under the same light are rarely balanced. These values were measured
# using auto_calibrate_white() against this project's white LED reference --
# if you swap sensors or LEDs, re-run auto_calibrate_white() and update these.
CAL_R = 1.756
CAL_G = 1.025
CAL_B = 1.000

# Minimum clear-channel value to treat as "off". This was lowered from 150
# after switching to a faster (24ms) integration time, since even boosted
# gain doesn't fully restore raw counts to their old 154ms-integration
# levels. If dim colors like red/green are still misread as OFF/DARK, lower
# this further; if ambient room light falsely triggers a color, raise it.
DARK_THRESHOLD = 40

# Saturation below this is treated as white. Real white LEDs are rarely
# perfectly neutral (warm/cool white LEDs skew reddish/bluish), so this is
# intentionally higher than a "pure white" theoretical value of 0.
WHITE_SATURATION_THRESHOLD = 35


# 6. Lightweight Math Engine for Color Separation
def calculate_hsv(r, g, b):
    """Converts calibrated RGB components into Hue (0-360) and Saturation (0-100)."""
    r *= CAL_R
    g *= CAL_G
    b *= CAL_B

    max_val = max(r, g, b)
    min_val = min(r, g, b)
    delta = max_val - min_val

    if max_val == 0:
        return 0, 0

    s = (delta / max_val) * 100

    if delta == 0:
        h = 0
    elif max_val == r:
        h = 60 * (((g - b) / delta) % 6)
    elif max_val == g:
        h = 60 * (((b - r) / delta) + 2)
    else:
        h = 60 * (((r - g) / delta) + 4)

    return int(h), int(s)


def identify_led_color(r, g, b, clear):
    """Classifies the light source into one of your target LED colors."""
    if clear < DARK_THRESHOLD:
        return "OFF / DARK"

    h, s = calculate_hsv(r, g, b)

    if s < WHITE_SATURATION_THRESHOLD:
        return "WHITE"

    # Widened + slightly overlapping windows so real-world LEDs (which rarely
    # sit at textbook-perfect hue angles) don't fall into the cracks between
    # categories. Magenta in particular is widened since red/blue mixes drift
    # toward either neighbor depending on sensor channel balance.
    if (h >= 0 and h < 15) or (h >= 345 and h <= 360):
        return "RED"
    elif h >= 15 and h < 70:
        return "YELLOW"
    elif h >= 70 and h < 160:
        return "GREEN"
    elif h >= 160 and h < 195:
        return "CYAN"
    elif h >= 195 and h < 255:
        return "BLUE"
    elif h >= 255 and h < 345:
        return "MAGENTA"

    return "UNKNOWN"


def calibrate_mode():
    """
    Diagnostic loop: prints raw + calibrated Hue/Saturation continuously.
    Shine each LED (especially the ones misclassifying) at the sensor and
    note the printed Hue value. Use those real numbers to adjust CAL_R/G/B
    and the hue windows in identify_led_color() above.
    """
    print("Calibration mode. Press Ctrl+C to stop.\n")
    try:
        while True:
            clear, red, green, blue = read_reg_words(REG_CDATAL, 4)
            h, s = calculate_hsv(red, green, blue)
            print(f"Raw  -> R:{red} G:{green} B:{blue} C:{clear}   "
                  f"HSV -> H:{h} S:{s}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nCalibration stopped.")


def auto_calibrate_white(samples=20):
    """
    Point the sensor at your WHITE light source and run this once.
    It averages several raw readings and computes CAL_R/CAL_G/CAL_B values
    that balance the three channels so a true white reads as (roughly)
    equal R, G, B -- fixing both the "white reads as cyan" issue and
    improving accuracy for every other color, since they all rely on the
    same channel balance.

    Copy the printed CAL_R / CAL_G / CAL_B values into the constants near
    the top of this file, replacing the current 1.0 defaults.
    """
    print(f"Point the sensor at a WHITE light source. Sampling {samples} readings...")
    time.sleep(1)

    r_total = g_total = b_total = 0
    for _ in range(samples):
        _, red, green, blue = read_reg_words(REG_CDATAL, 4)
        r_total += red
        g_total += green
        b_total += blue
        time.sleep(0.1)

    r_avg = r_total / samples
    g_avg = g_total / samples
    b_avg = b_total / samples

    print(f"\nRaw averages -> R:{r_avg:.1f} G:{g_avg:.1f} B:{b_avg:.1f}")

    target = max(r_avg, g_avg, b_avg)
    cal_r = target / r_avg if r_avg else 1.0
    cal_g = target / g_avg if g_avg else 1.0
    cal_b = target / b_avg if b_avg else 1.0

    print("\nCopy these into the CAL_R / CAL_G / CAL_B constants above:")
    print(f"CAL_R = {cal_r:.3f}")
    print(f"CAL_G = {cal_g:.3f}")
    print(f"CAL_B = {cal_b:.3f}")


# 7. Main Loop
def main():
    """
    Continuously scans for LED blinks in a fast, changing sequence (e.g. an
    LED that cycles through colors on a button press). Rather than sampling
    once every fixed interval, this samples quickly and only reports a color
    once it has been read consistently for a few samples in a row -- this
    avoids logging "blend" colors caught mid-transition between two blinks
    (e.g. green fading to blue briefly looking like cyan).
    """
    print("Initializing TCS34725 sensor...")
    init_sensor()
    print("Scanner running. Waiting for LED blinks. Press Ctrl+C to stop.\n")

    # How many consecutive matching samples are required before a color is
    # considered "confirmed" rather than a mid-transition blend. Raise this
    # if you still see false/blend colors; lower it if real blinks are too
    # short to hit this many samples.
    STABLE_SAMPLES = 3

    # Delay between samples. Keep this short relative to your LED's blink
    # duration -- e.g. if each blink lasts ~300ms, 0.03s gives ~10 samples
    # per blink, comfortably more than STABLE_SAMPLES.
    POLL_INTERVAL = 0.03

    last_confirmed = None   # last color that was actually reported
    candidate = None        # color currently being tracked as a possible match
    candidate_count = 0

    try:
        while True:
            clear, red, green, blue = read_reg_words(REG_CDATAL, 4)
            label = identify_led_color(red, green, blue, clear)

            if label == candidate:
                candidate_count += 1
            else:
                candidate = label
                candidate_count = 1

            # Confirm a new color once it's been stable for enough samples,
            # and it's different from whatever we last reported.
            if (candidate_count == STABLE_SAMPLES
                    and label != "OFF / DARK"
                    and label != last_confirmed):
                print(f"Detected: {label}")
                if clear > 0:
                    print(f"Ratio -> R: {int((red/clear)*100)}% | "
                          f"G: {int((green/clear)*100)}% | "
                          f"B: {int((blue/clear)*100)}% | C: {clear}")
                print("-" * 50)
                last_confirmed = label

            # Reset once the LED goes dark, so the same color can be
            # detected again next time it blinks.
            if label == "OFF / DARK":
                last_confirmed = None

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nScanner halted.")


if __name__ == "__main__":
    main()

    # Diagnostic modes -- swap in if you ever need to re-tune things.
    # Both require init_sensor() to be called first, e.g.:
    #   init_sensor()
    #   calibrate_mode()          # watch live Hue/Saturation numbers
    #   auto_calibrate_white()    # re-measure CAL_R/CAL_G/CAL_B (see README)
