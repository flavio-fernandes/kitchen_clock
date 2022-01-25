# SPDX-FileCopyrightText: 2020 Melissa LeBlanc-Williams, written for Adafruit Industries
#
# SPDX-License-Identifier: Unlicense
"""
`adafruit_matrixportal`
================================================================================

Helper library for the Adafruit RGB Matrix Shield + Metro M4 Airlift Lite.

* Author(s): Melissa LeBlanc-Williams

Implementation Notes
--------------------

**Hardware:**

* `Adafruit Metro M4 Express AirLift <https://www.adafruit.com/product/4000>`_
* `Adafruit RGB Matrix Shield <https://www.adafruit.com/product/2601>`_
* `64x32 RGB LED Matrix <https://www.adafruit.com/product/2278>`_

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://github.com/adafruit/circuitpython/releases

* Adafruit's Bus Device library: https://github.com/adafruit/Adafruit_CircuitPython_BusDevice
"""

import time
import gc
import board
import busio
from digitalio import DigitalInOut
import terminalio
from adafruit_esp32spi import adafruit_esp32spi, adafruit_esp32spi_wifimanager
from adafruit_bitmap_font import bitmap_font
import displayio
from adafruit_display_text.label import Label
import rgbmatrix
import framebufferio

try:
    from secrets import secrets
except ImportError:
    print(
        """WiFi settings are kept in secrets.py, please add them there!
the secrets dictionary must contain 'ssid' and 'password' at a minimum"""
    )
    raise

__version__ = "0.0.0-auto.0"
__repo__ = "https://github.com/adafruit/Adafruit_CircuitPython_PyPortal.git"

# pylint: disable=line-too-long
# pylint: disable=too-many-lines
# you'll need to pass in an io username, width, height, format (bit depth), io key, and then url!
IMAGE_CONVERTER_SERVICE = "https://io.adafruit.com/api/v2/%s/integrations/image-formatter?x-aio-key=%s&width=%d&height=%d&output=BMP%d&url=%s"
# you'll need to pass in an io username and key
TIME_SERVICE = (
    "https://io.adafruit.com/api/v2/%s/integrations/time/strftime?x-aio-key=%s"
)
# our strftime is %Y-%m-%d %H:%M:%S.%L %j %u %z %Z see http://strftime.net/ for decoding details
# See https://apidock.com/ruby/DateTime/strftime for full options
TIME_SERVICE_STRFTIME = (
    "&fmt=%25Y-%25m-%25d+%25H%3A%25M%3A%25S.%25L+%25j+%25u+%25z+%25Z"
)
# pylint: enable=line-too-long


class MatrixPortal:
    # pylint: disable=too-many-instance-attributes, too-many-locals, too-many-branches, too-many-statements
    def __init__(
        self,
        *,
        esp=None,
        external_spi=None,
        bit_depth=4,
        debug=False
    ):

        self._debug = debug

        try:
            displayio.release_displays()
            matrix = rgbmatrix.RGBMatrix(
                width=64,
                height=32,
                bit_depth=bit_depth,
                rgb_pins=[board.MTX_R1, board.MTX_G1, board.MTX_B1, board.MTX_R2, board.MTX_G2,
                          board.MTX_B2],
                addr_pins=[board.MTX_ADDRA, board.MTX_ADDRB, board.MTX_ADDRC, board.MTX_ADDRD],
                clock_pin=board.MTX_CLK,
                latch_pin=board.MTX_LAT,
                output_enable_pin=board.MTX_OE,
            )
            self.display = framebufferio.FramebufferDisplay(matrix)
        except ValueError:
            raise RuntimeError("Failed to initialize RGB Matrix")

        if self._debug:
            print("Init display")
        self.splash = displayio.Group()

        if esp:  # If there was a passed ESP Object
            if self._debug:
                print("Passed ESP32 to MatrixPortal")
            self._esp = esp
            if external_spi:  # If SPI Object Passed
                spi = external_spi
            else:  # Else: Make ESP32 connection
                spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        else:
            if self._debug:
                print("Init ESP32")
            esp32_ready = DigitalInOut(board.ESP_BUSY)
            esp32_gpio0 = DigitalInOut(board.ESP_GPIO0)
            esp32_reset = DigitalInOut(board.ESP_RESET)
            esp32_cs = DigitalInOut(board.ESP_CS)
            spi = busio.SPI(board.SCK, board.MOSI, board.MISO)

            self._esp = adafruit_esp32spi.ESP_SPIcontrol(
                spi, esp32_cs, esp32_ready, esp32_reset, esp32_gpio0
            )
        # self._esp._debug = 1
        for _ in range(3):  # retries
            try:
                print("ESP firmware:", self._esp.firmware_version)
                break
            except RuntimeError:
                print("Retrying ESP32 connection")
                time.sleep(1)
                self._esp.reset()
        else:
            raise RuntimeError("Was not able to find ESP32")

        # set the default background
        self.display.show(self.splash)

        self._text = []
        self._text_font = []
        self._text_color = []
        self._text_position = []
        self._text_wrap = []
        self._text_maxlen = []
        self._text_transform = []
        self._text_scrolling = []
        self._scrolling_index = None

        # Font Cache
        self._fonts = {}

        gc.collect()

    def add_text(
        self,
        text_position=None,
        text_font=None,
        text_color=0x808080,
        text_wrap=False,
        text_maxlen=0,
        text_transform=None,
        scrolling=False,
    ):
        """
        Add text labels with settings

        :param str text_font: The path to your font file for your data text display.
        :param text_position: The position of your extracted text on the display in an (x, y) tuple.
                              Can be a list of tuples for when there's a list of json_paths, for
                              example.
        :param text_color: The color of the text, in 0xRRGGBB format. Can be a list of colors for
                           when there's multiple texts. Defaults to ``None``.
        :param text_wrap: Whether or not to wrap text (for long text data chunks). Defaults to
                          ``False``, no wrapping.
        :param text_maxlen: The max length of the text for text wrapping. Defaults to 0.
        :param text_transform: A function that will be called on the text before display
        :param bool scrolling: If true, text is placed offscreen and the scroll() function is used
                               to scroll text on a pixel-by-pixel basis. Multiple text labels with
                               the scrolling set to True will be cycled through.

        """
        if not text_wrap:
            text_wrap = 0
        if not text_maxlen:
            text_maxlen = 0
        if not text_transform:
            text_transform = None
        if scrolling:
            text_position = (self.display.width, text_position[1])

        gc.collect()

        if self._debug:
            print("Init text area")

        self._text.append(None)
        self._text_font.append(self._load_font(text_font))
        self._text_color.append(text_color)
        self._text_position.append(text_position)
        self._text_wrap.append(text_wrap)
        self._text_maxlen.append(text_maxlen)
        self._text_transform.append(text_transform)
        self._text_scrolling.append(scrolling)

    def preload_font(self, glyphs=None, font=None):
        # pylint: disable=line-too-long
        """Preload font.

        :param glyphs: The font glyphs to load. Defaults to ``None``, uses alphanumeric glyphs if
                       None.
        """
        # pylint: enable=line-too-long
        if not glyphs:
            glyphs = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-!,. \"'?!"
        for name in self._fonts:
            if font and name != font:
                continue
            if name is not "terminal":
                self._fonts[name].load_glyphs(glyphs)
            if self._debug:
                print(f"Preloading font {name} glyphs: {glyphs}")

    def set_text(self, val, index=0, text_color=None, scrolling=None, text_position=None):

        """Display text, with indexing into our list of text boxes.

        :param str val: The text to be displayed
        :param index: Defaults to 0.

        """
        # Make sure at least a single label exists
        if not self._text:
            assert index == 0
            self.add_text()

        font = self._fonts[self._text_font[index]]
        string = str(val)
        if self._text_maxlen[index]:
            string = string[: self._text_maxlen[index]]

        if text_color is not None:
            self._text_color[index] = text_color
        if text_position is not None:
            self._text_position[index] = text_position
        if scrolling is not None:
            scrolling = str(scrolling).lower() == "true"
            if scrolling:
                curr_y = self._text_position[index][1]
                self._text_position[index] = (self.display.width, curr_y)
            self._text_scrolling[index] = scrolling
            if self._scrolling_index == index:
                # self._text[index].x = self.display.width
                # line_width = self._text[index].bounding_box[2]
                # self._text[index].x = -line_width
                self._scrolling_index = None

        if self._text[index]:
            # print("Replacing text area with :", string)
            # self._text[index].text = string
            # return
            try:
                text_index = self.splash.index(self._text[index])
            except AttributeError:
                for i in range(len(self.splash)):
                    if self.splash[i] == self._text[index]:
                        text_index = i
                        break

            self._text[index] = Label(font, text=string)
            self._text[index].color = self._text_color[index]
            self._text[index].x = self._text_position[index][0]
            self._text[index].y = self._text_position[index][1]
            self.splash[text_index] = self._text[index]
            return

        if self._text_position[index]:  # if we want it placed somewhere...
            print("Making text area with string:", string)
            self._text[index] = Label(font, text=string)
            self._text[index].color = self._text_color[index]
            self._text[index].x = self._text_position[index][0]
            self._text[index].y = self._text_position[index][1]
            self.splash.append(self._text[index])

    def _connect_esp(self):
        while not self._esp.is_connected:
            # secrets dictionary must contain 'ssid' and 'password' at a minimum
            print("Connecting to AP", secrets["ssid"])
            if secrets["ssid"] == "CHANGE ME" or secrets["password"] == "CHANGE ME":
                change_me = "\n" + "*" * 45
                change_me += "\nPlease update the 'secrets.py' file on your\n"
                change_me += "CIRCUITPY drive to include your local WiFi\n"
                change_me += "access point SSID name in 'ssid' and SSID\n"
                change_me += "password in 'password'. Then save to reload!\n"
                change_me += "*" * 45
                raise OSError(change_me)
            try:
                self._esp.connect(secrets)
            except RuntimeError as error:
                print("Could not connect to internet", error)
                print("Retrying in 3 seconds...")
                time.sleep(3)

    def _get_next_scrollable_text_index(self):
        index = self._scrolling_index
        wrapped = False
        while True:
            if index is None:
                index = 0
            else:
                index += 1
            if index >= len(self._text_scrolling):
                if wrapped:
                    return None
                index = 0
                wrapped = True
            if self._text_scrolling[index]:
                return index
            if index == self._scrolling_index:
                return None

    def scroll(self):
        """Scroll any text that needs scrolling. We also want to queue up
        multiple lines one after another. To get simultaneous lines, we can
        simply use a line break."""

        if self._scrolling_index is None:  # Not initialized yet
            next_index = self._get_next_scrollable_text_index()
            if next_index is None:
                return
            self._scrolling_index = next_index

        # set line to label with self._scrolling_index

        self._text[self._scrolling_index].x = self._text[self._scrolling_index].x - 1
        line_width = self._text[self._scrolling_index].bounding_box[2]
        if self._text[self._scrolling_index].x < -line_width:
            # Find the next line
            self._scrolling_index = self._get_next_scrollable_text_index()
            if self._scrolling_index is not None:
                self._text[self._scrolling_index].x = self.display.width

    def _load_font(self, font):
        """
        Load and cache a font if not previously loaded
        Return the key of the cached font

        :param font: Either terminalio.FONT or the path to the bdf font file

        """
        if font is terminalio.FONT or not font:
            if "terminal" not in self._fonts:
                self._fonts["terminal"] = terminalio.FONT
            return "terminal"
        if font not in self._fonts:
            self._fonts[font] = bitmap_font.load_font(font)
        return font

    @staticmethod
    def html_color_convert(color):
        """Convert an HTML color code to an integer

        :param color: The color value to be converted

        """
        if isinstance(color, str):
            if color.startswith("#"):
                return int(color[1:])
            return int(color, 16)
        return color  # Return unconverted
