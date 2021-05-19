# NOTE: Make sure you've created your secrets.py file before running this example
# https://learn.adafruit.com/adafruit-pyportal/internet-connect#whats-a-secrets-file-17-2
#

import gc
import json
import os
import time
from collections import namedtuple

import board
import digitalio
import displayio
import microcontroller
import neopixel
import rtc

import adafruit_esp32spi.adafruit_esp32spi_socket as socket
from adafruit_display_shapes.line import Line
from adafruit_esp32spi import adafruit_esp32spi_wifimanager
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from mini_matrixportal import MatrixPortal
from secrets import secrets

MSG_TIME_IDX = 0
MSG_TXT_IDX = 1

matrixportal = MatrixPortal(debug=True)
print("Connecting to WiFi...")
wifi = adafruit_esp32spi_wifimanager.ESPSPI_WiFiManager(
    matrixportal._esp, secrets, None
)
wifi.connect()
print("My IP address is", matrixportal._esp.pretty_ip(matrixportal._esp.ip_address))

# ------- Real Time Clock  ------- #

global_rtc = rtc.RTC()

# --------------- Text ----------------- #
TIME_FONT = "time_font.bdf"

# hour (ID = MSG_TIME_IDX)
matrixportal.add_text(
    text_font=TIME_FONT,
    text_position=(0, 8),
    text_color=0xFFFFFF,
)
matrixportal.preload_font(b"0123456789:", TIME_FONT)
matrixportal.set_text(" ", MSG_TIME_IDX)

# status/messages (ID = MSG_TXT_IDX)
matrixportal.add_text(
    text_position=(0, 25),
)
matrixportal.set_text(" ", MSG_TXT_IDX)

SECS_COLOR = 0x404040
SECS_WIDTH = 4
seconds_line = Line(
    0, 0, matrixportal.display.width, matrixportal.display.height, 0xFF0000
)
seconds_index = len(matrixportal.splash)
matrixportal.splash.append(seconds_line)


def _set_text_center(val, index, text_color=None):
    pixels_used = 0
    for chararcter in val:
        glyph = matrixportal._text[index]._font.get_glyph(ord(chararcter))
        pixels_used += glyph.shift_x
    if pixels_used >= matrixportal.display.width:
        new_x = 0
    else:
        new_x = int((matrixportal.display.width - pixels_used) / 2)
    curr_y = matrixportal._text_position[index][1]
    matrixportal.set_text(
        val,
        index,
        text_color=text_color,
        scrolling=False,
        text_position=(new_x, curr_y),
    )


def display_date_and_temp():
    global outside_temp

    # roycbiv: https://en.m.wikipedia.org/wiki/ROYGBIV
    now = global_rtc.datetime
    week_days = [
        ("Mon", 0xFF0000),  # red
        ("Tue", 0xFF4500),  # orange
        ("Wed", 0xFFFF00),  # yellow
        ("Thu", 0x00FF00),  # green
        ("Fri", 0x0000FF),  # blue
        ("Sat", 0x595DFF),  # indigo
        ("Sun", 0x9F51FF),  # violet
    ]
    months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]

    # info = f"{week_days[now.tm_wday][0]}|{months[now.tm_mon-1]}{now.tm_mday:02}"
    info = f"{now.tm_mday}/{months[now.tm_mon-1]}"

    if outside_temp is not None:
        info += f" {outside_temp}F"
    matrixportal._text_color[MSG_TXT_IDX] = week_days[now.tm_wday][1]
    _set_text_center(info, MSG_TXT_IDX)


def _pretty_hour(hour):
    if hour == 0:
        return 12
    if hour > 12:
        return hour - 12
    return hour


display_needs_refresh = True
cached_mins = None


def display_main():
    global display_needs_refresh, cached_mins, counters

    now = global_rtc.datetime
    matrixportal.splash[seconds_index] = Line(
        now.tm_sec, 1, now.tm_sec + SECS_WIDTH, 1, SECS_COLOR
    )
    if "local_time" not in counters:
        _set_text_center(str(int(time.monotonic())), MSG_TIME_IDX)
        return

    if cached_mins == now.tm_min and not display_needs_refresh:
        return

    _set_text_center(f"{_pretty_hour(now.tm_hour)}:{now.tm_min:02}", MSG_TIME_IDX)

    if not msg_state:
        display_date_and_temp()

    cached_mins = now.tm_min
    display_needs_refresh = False


def one_sec_tick():
    global msg_state, display_needs_refresh, img_state

    # Manage timeouts
    if msg_state:
        curr_timeout = msg_state.get("timeout")
        if isinstance(curr_timeout, int):
            if curr_timeout <= 0:
                matrixportal.set_text(val=" ", index=MSG_TXT_IDX, scrolling=False)
                display_needs_refresh = True
                msg_state.clear()
            else:
                msg_state["timeout"] = curr_timeout - 1

    if img_state:
        curr_timeout = img_state.get("timeout")
        if isinstance(curr_timeout, int):
            if curr_timeout <= 0:
                _parse_img(None, message="")
            else:
                img_state["timeout"] = curr_timeout - 1

        if img_state.get("img_only"):
            return

    if matrixportal.display.brightness:
        # check if scroll needs to be started
        if matrixportal._scrolling_index is None:
            matrixportal.scroll()

        display_main()


# ------- Leds  ------- #

# ref: https://www.devdungeon.com/content/pyportal-circuitpy-tutorial-adabox-011#toc-27
pixels = neopixel.NeoPixel(board.NEOPIXEL, 1, auto_write=True)
pixels[0] = (0, 0, 0)

board_led = digitalio.DigitalInOut(board.L)  # Or board.D13
board_led.switch_to_output()

# ------- Stats  ------- #

counters = {}


def _inc_counter(name):
    global counters
    curr_value = counters.get(name, 0)
    counters[name] = curr_value + 1


# ------------- MQTT Topic Setup ------------- #


def _parse_ping(_topic, _message):
    global tss
    tss["send_status"] = None  # clear to force send status now
    _inc_counter("ping")


def _parse_brightness(topic, message):
    print("_parse_brightness: {0} {1} {2}".format(len(message), topic, message))
    set_brightness(message)
    _inc_counter("brightness")


def _parse_neopixel(_topic, message):
    global pixels
    try:
        value = int(message)
    except ValueError as e:
        print(f"bad neo value: {e}")
        return
    pixels[0] = ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
    _inc_counter("neo")


def _parse_blinkrate(_topic, message):
    global tss, TS_INTERVALS, board_led

    message = message.lower()
    value_map = {"off": 0, "no": 0, "on": None, "yes": None, "": LED_BLINK_DEFAULT}
    try:
        if message.startswith("-") or message in value_map:
            value = value_map.get(message)
        else:
            value = float(message)
    except ValueError as e:
        print(f"bad blink value given {message}: {e}")
        return

    if value:
        TS_INTERVALS[LED_BLINK] = TS(value, interval_led_blink)
        tss[LED_BLINK] = None
    else:
        # Stop blinking. Turn off if value is 0. Turn on if value is None.
        try:
            del TS_INTERVALS[LED_BLINK]
            del tss[LED_BLINK]
        except KeyError:
            pass
        board_led.value = value is None
    _inc_counter("blink")


def _parse_localtime_message(topic, message):
    # /aio/local_time : 2021-01-15 23:07:36.339 015 5 -0500 EST
    try:
        print(f"Local time mqtt: {message}")
        times = message.split(" ")
        the_date = times[0]
        the_time = times[1]
        year_day = int(times[2])
        week_day = int(times[3])
        is_dst = None  # no way to know yet
        year, month, mday = [int(x) for x in the_date.split("-")]
        the_time = the_time.split(".")[0]
        hours, minutes, seconds = [int(x) for x in the_time.split(":")]
        now = time.struct_time(
            (year, month, mday, hours, minutes, seconds, week_day, year_day, is_dst)
        )
        global_rtc.datetime = now
        _inc_counter("local_time")
    except Exception as e:
        print(f"Error in _parse_localtime_message -", e)
        _inc_counter("local_time_failed")


outside_temp = None


def _parse_temperature_outside(topic, message):
    global outside_temp
    outside_temp = int(message)
    _inc_counter("outside_temp")


msg_state = {}


def _parse_msg_message(topic, message):
    global display_needs_refresh
    global msg_state

    print(f"msg_message: {message}")
    _inc_counter("msg_message")
    try:
        msg_state = json.loads(message)
    except ValueError:
        msg_state = {"msg": message, "timeout": 20}

    display_needs_refresh = True
    if not msg_state.get("msg"):
        msg_state.clear()
        return

    # timeout
    timeout = msg_state.get("timeout")
    if timeout is not None:
        msg_state["timeout"] = int(timeout)

    color = msg_state.get("text_color") or msg_state.get("color")
    if color:
        msg_state["text_color"] = matrixportal.html_color_convert(color)

    no_scroll = msg_state.get("no_scroll")
    if no_scroll is not None:
        scrolling = str(no_scroll).lower() != "true"
    else:
        scrolling = True

    x_position = msg_state.get("x")
    if str(x_position).lower() == "center":
        _set_text_center(
            val=msg_state.get("msg"),
            index=MSG_TXT_IDX,
            text_color=msg_state.get("text_color"),
        )
        return

    text_position = None
    if x_position is not None:
        try:
            text_position = (
                int(x_position),
                matrixportal._text_position[MSG_TXT_IDX][1],
            )
        except Exception as e:
            print(f"Failed to parse position {x_position}: {e}")

    matrixportal.set_text(
        val=msg_state.get("msg"),
        index=MSG_TXT_IDX,
        text_color=msg_state.get("text_color"),
        scrolling=scrolling,
        text_position=text_position,
    )


img_state = {}
img_index = None


def _parse_img(_topic, message=""):
    global display_needs_refresh, seconds_index
    global img_state, img_index

    print(f"img: {message}")
    _inc_counter("img_message")
    try:
        img_params = json.loads(message)
    except ValueError:
        img_params = {"img": message, "timeout": 20}

    if img_index:
        del matrixportal.splash[img_index]
        img_index = None

    img_file = img_state.get("img_file")
    if img_file:
        img_file.close()

    img_state.clear()

    if not img_params.get("img"):
        display_needs_refresh = True
        return

    for filename in (
        "bmps/" + img_params["img"] + ".bmp",
        "bmps/" + img_params["img"],
        img_params["img"],
        img_params["img"] + ".bmp",
    ):
        try:
            os.stat(filename)
            break
        except OSError:
            pass
    print(f"opening image: {filename}")
    img_state["img_file"] = open(filename, "rb")
    img_bitmap = displayio.OnDiskBitmap(img_state["img_file"])
    img_state["img_frame_count"] = int(img_bitmap.height / matrixportal.display.height)
    img_sprite = displayio.TileGrid(
        img_bitmap,
        pixel_shader=displayio.ColorConverter(),
        tile_width=img_bitmap.width,
        tile_height=matrixportal.display.height,
        x=max(matrixportal.display.width - img_bitmap.width, 0) // 2,
        y=0,
    )
    img_index = len(matrixportal.splash)
    matrixportal.splash.append(img_sprite)

    # timeout
    timeout = img_params.get("timeout")
    if timeout is not None:
        img_state["timeout"] = int(timeout)

    img_only = img_params.get("img_only")
    if img_only is not None:
        img_only = str(img_only).lower() == "true"
    else:
        img_only = True
    img_state["img_only"] = img_only
    if img_only:
        matrixportal.set_text(" ", MSG_TIME_IDX)
        matrixportal.set_text(" ", MSG_TXT_IDX)
        if seconds_index is not None:
            # Clear seconds line
            matrixportal.splash[seconds_index] = Line(0, 1, 0, 1, 0x00)


def advance_img():
    global img_state, img_index

    if not img_state or not matrixportal.display.brightness:
        return

    img_curr_frame = img_state.get("img_curr_frame", 0)
    matrixportal.splash[img_index][0] = img_curr_frame
    img_state["img_curr_frame"] = (img_curr_frame + 1) % img_state["img_frame_count"]


mqtt_topic = secrets.get("topic_prefix") or "/matrixportal"
mqtt_pub_status = f"{mqtt_topic}/status"

mqtt_subs = {
    f"{mqtt_topic}/ping": _parse_ping,
    f"{mqtt_topic}/brightness": _parse_brightness,
    f"{mqtt_topic}/neopixel": _parse_neopixel,
    f"{mqtt_topic}/blinkrate": _parse_blinkrate,
    f"{mqtt_topic}/msg": _parse_msg_message,
    f"{mqtt_topic}/img": _parse_img,
    "/aio/local_time": _parse_localtime_message,
    "/sensor/temperature_outside": _parse_temperature_outside,
}

# ------------- MQTT Functions ------------- #

# Define callback methods which are called when events occur
# pylint: disable=unused-argument, redefined-outer-name
def connect(client, userdata, flags, rc):
    # This function will be called when the client is connected
    # successfully to the broker.
    print("Connected to MQTT Broker!", end=" ")
    print(f"mqtt_msg: {client.mqtt_msg}", end=" ")
    print(f"Flags: {flags} RC: {rc}")
    for mqtt_sub in mqtt_subs:
        print(f"Subscribing to {mqtt_sub}")
        client.subscribe(mqtt_sub)
    _inc_counter("connect")


def disconnected(_client, _userdata, rc):
    # This method is called when the client is disconnected
    print(f"Disconnected from MQTT Broker! RC: {rc}")
    _inc_counter("disconnected")


def subscribe(_client, _userdata, topic, granted_qos):
    # This method is called when the client subscribes to a new feed
    print(f"Subscribed to {topic} with QOS level {granted_qos}")
    _inc_counter("subscribe")


def publish(_client, userdata, topic, pid):
    # This method is called when the client publishes data to a feed
    print(f"Published to {topic} with PID {pid}")
    _inc_counter("publish")


def message(_client, topic, message):
    # This method is called when the subscribed feed has a new value
    if topic in mqtt_subs:
        mqtt_subs[topic](topic, message)


# ------------- Network Connection ------------- #

# Initialize MQTT interface with the esp interface
# MQTT.set_socket(socket, matrixportal.network._wifi.esp)
MQTT.set_socket(socket, matrixportal._esp)

# Set up a MiniMQTT Client
client = MQTT.MQTT(
    broker=secrets["broker"],
    port=secrets.get("broker_port") or 1883,
    username=secrets["broker_user"],
    password=secrets["broker_pass"],
)
client.attach_logger()
client.set_logger_level("DEBUG")

# Connect callback handlers to client
client.on_connect = connect
client.on_disconnect = disconnected
client.on_subscribe = subscribe
client.on_publish = publish
client.on_message = message

print(f"Attempting to MQTT connect to {client.broker}")
try:
    client.connect()
except Exception as e:
    print(f"FATAL! Unable to MQTT connect to {client.broker}: {e}")
    time.sleep(120)
    # bye bye cruel world
    microcontroller.reset()


# ------------- Screen elements ------------- #


def set_brightness(val):
    global display_needs_refresh

    """Adjust the TFT backlight.
    :param val: The backlight brightness. Use a value between ``0`` and ``1``, where ``0`` is
                off, and ``1`` is 100% brightness. Can also be 'on' or 'off'
    """
    if isinstance(val, str):
        val = {
            "on": 1,
            "off": 0,
            "mid": 0.5,
            "min": 0.01,
            "max": 1,
            "yes": 1,
            "no": 0,
            "y": 1,
            "n": 0,
        }.get(val.lower(), val)
    try:
        val = float(val)
    except (ValueError, TypeError):
        return
    val = max(0, min(1.0, val))
    # matrixportal.display.auto_brightness = False
    matrixportal.display.brightness = val
    display_needs_refresh = True


set_brightness("on")


# ------------- Iteration routines ------------- #


def interval_send_status():
    global counters

    value = {
        "uptime_mins": int(time.monotonic() - t0) // 60,
        "brightness": matrixportal.display.brightness,
        "ip": wifi.ip_address(),
        "counters": str(counters),
        "mem_free": gc.mem_free(),
    }
    client.publish(mqtt_pub_status, json.dumps(value))
    print(f"send_status: {mqtt_pub_status}: {value}")


def interval_led_blink():
    board_led.value = not board_led.value


def _try_reconnect(e):
    print(f"Failed mqtt loop: {e}")
    _inc_counter("fail_loop")
    time.sleep(3)
    try:
        client.disconnect()
        client.connect()
    except Exception as e:
        # bye bye cruel world
        print(f"FATAL! Failed reconnect: {e}")
        microcontroller.reset()


# ------------- Main loop ------------- #

LED_BLINK = "led_blink"
LED_BLINK_DEFAULT = 60

# tss routines
TS = namedtuple("TS", "interval fun")
TS_INTERVALS = {
    "send_status": TS(10 * 60, interval_send_status),
    LED_BLINK: TS(LED_BLINK_DEFAULT, interval_led_blink),  # may be overridden via mqtt
    "1sec": TS(1, one_sec_tick),
    "img_frame": TS(0.1, advance_img),
}


tss = {interval: None for interval in TS_INTERVALS}
t0 = time.monotonic()
now = t0
while True:
    try:
        if (
            not client.loop()
            and matrixportal._scrolling_index is None
            and not img_state
        ):
            # Take a little break if nothing really happened
            time.sleep(0.123)
    except Exception as e:
        _try_reconnect(e)

    if not img_state and matrixportal._scrolling_index is not None:
        # Scroll the text block, but only if there is work
        # There is an explicit in a less frequent interval (one_sec_tick)
        matrixportal.scroll()

    now = time.monotonic()
    for ts_interval in TS_INTERVALS:
        if (
            not tss[ts_interval]
            or now > tss[ts_interval] + TS_INTERVALS[ts_interval].interval
        ):
            try:
                if TS_INTERVALS[ts_interval].interval >= 60:
                    lt = time.localtime()
                    print(
                        f"{lt.tm_hour}:{lt.tm_min}:{lt.tm_sec} Interval {ts_interval} triggered"
                    )
                else:
                    # print(".", end="")
                    pass
                TS_INTERVALS[ts_interval].fun()
            except (ValueError, RuntimeError) as e:
                print(f"Error in {ts_interval}, retrying in 10s: {e}")
                tss[ts_interval] = (now - TS_INTERVALS[ts_interval].interval) + 10
                _inc_counter("fail_runtime")
                continue
            except Exception as e:
                print(f"Failed {ts_interval}: {e}")
                _inc_counter("fail_other")
            tss[ts_interval] = time.monotonic()
