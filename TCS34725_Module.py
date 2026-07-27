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

# Turn off the onboard white LED using software
led_control_pin = Pin(2, Pin.OUT) # Replace '2' with the physical pin connected to the sensor's INT/LED pin
led_control_pin.value(0)          # Pull low to turn it completely OFF


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
    write_reg(REG_ATIME, 0xC0)   # Integration time: 154ms
    write_reg(REG_CONTROL, 0x01)  # Gain: 4x
    write_reg(REG_ENABLE, 0x01)   # Power ON
    time.sleep(0.003)
    write_reg(REG_ENABLE, 0x01 | 0x02)  # Power ON + RGBC ADC enable
    time.sleep(0.16)  # let the first integration cycle complete


# 5. Lightweight Math Engine for Color Separation
def calculate_hsv(r, g, b):
    """Converts raw RGB components into Hue (0-360) and Saturation (0-100)."""
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
    if clear < 150:
        return "OFF / DARK"

    h, s = calculate_hsv(r, g, b)

    if s < 25:
        return "WHITE"

    if (h >= 0 and h < 20) or (h >= 335 and h <= 360):
        return "RED"
    elif h >= 20 and h < 75:
        return "YELLOW"
    elif h >= 75 and h < 160:
        return "GREEN"
    elif h >= 160 and h < 200:
        return "CYAN"
    elif h >= 200 and h < 270:
        return "BLUE"
    elif h >= 270 and h < 335:
        return "MAGENTA"

    return "UNKNOWN"


# 6. Main Loop
def main():
    print("Initializing TCS34725 sensor...")
    init_sensor()
    print("Scanner running. Press Ctrl+C to stop.\n")

    try:
        while True:
            # REG_CDATAL onward gives Clear, Red, Green, Blue in that order
            clear, red, green, blue = read_reg_words(REG_CDATAL, 4)

            label = identify_led_color(red, green, blue, clear)
            print(f"Detected: {label}")

            if clear > 0:
                print(f"Ratio -> R: {int((red/clear)*100)}% | "
                      f"G: {int((green/clear)*100)}% | "
                      f"B: {int((blue/clear)*100)}% | C: {clear}")

            print("-" * 50)
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nScanner halted.")


if __name__ == "__main__":
    main()
