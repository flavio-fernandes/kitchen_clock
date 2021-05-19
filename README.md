# kitchen_clock

#### CircuitPython based project for Adafruit MatrixPortal controlled via MQTT

This repo is a snapshot of all files and python script
needed to have time and messages displayed on a MatrixPortal.
This project uses an MQTT broker for obtaining the time as well as
displaying custom messages. There is also support for using
[Bitmap Pixel Art and Animation](https://learn.adafruit.com/pixel-art-matrix-display).
If you rather use a PyPortal, check out the [pyportal_station](https://github.com/flavio-fernandes/pyportal_station)
project.

### Challenge

While I am using a newer version of Circuit Python, Matrix Portal
and the Mini-MQTT libraries just don't fit in the MatrixPortal
microcontroller. That made this project a little challenging, and I now better
understand why the upcoming version 7 is so important. The compromise I
came up with was to use an older version of Mini-MQTT and a [*crippled*](https://github.com/flavio-fernandes/kitchen_clock/blob/main/lib/mini_matrixportal.py)
version of the Matrix Portal library.

**Adafruit_CircuitPython_MiniMQTT**: Using commit [407bb4f](https://github.com/adafruit/Adafruit_CircuitPython_MiniMQTT/commit/407bb4f43c0e46c5bcaceccf01481ab9690d6ce3)

**Adafruit_CircuitPython_MatrixPortal**: Baseline from commit [6f1d9d4](https://github.com/adafruit/Adafruit_CircuitPython_MatrixPortal/commit/6f1d9d4b7af347cc94a47d379c8bb1f286a2d7b6)
and removing all the code I did not need.

Besides the 2 libraries above, this project uses the following awesome libraries from the
[bundle 6.2-20210507](https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/tag/20210507):
- adafruit_bitmap_font (1.5.0)
- adafruit_display_shapes (2.1.0)
- adafruit_display_text (2.18.4)
- adafruit_esp32spi (3.5.9)
- adafruit_logging (1.2.8)
- adafruit_requests (1.9.9)
- neopixel (6.0.3)

But you can probably use newer versions of the 6.2 bundle.

### Hardware

The key components are the [Adafruit Matrix Portal](https://www.adafruit.com/product/4745) and the
[64x32 RGB LED Matrix - 6mm pitch](https://www.adafruit.com/product/2276) from Adafruit. 

Plugging the MatrixPortal directly on the HUB 75 socket made it stick out and that was not
well suited for this project. I had to come up with an adaptor.
Take a look at [thingiverse 4850550](https://www.thingiverse.com/thing:4850550) for info on
the brackets I made and printed for the clock, as well as the accessories used.

### secrets.py

Make sure to create a file called secrets.py to include info on the wifi as well as the MQTT
broker you will connect to. Use [**secrets.py.sample**](https://github.com/flavio-fernandes/kitchen_clock/blob/main/secrets.py.sample)
as reference.


### Removing _all_ files from CIRCUITPY drive

```
# NOTE: Do not do this before backing up all files!!!
>>> import storage ; storage.erase_filesystem()
```

### Copying files from cloned repo to CIRCUITPY drive
```
# First, get to the REPL prompt so the board will not auto-restart as
# you copy files into it

# Assuming that MatrixPortal is mounted under /Volumes/CIRCUITPY
$  cd ${THIS_REPO_DIR}
$  [ -d /Volumes/CIRCUITPY/ ] && \
   rm -rf /Volumes/CIRCUITPY/* && \
   (tar czf - *) | ( cd /Volumes/CIRCUITPY ; tar xzvf - ) && \
   echo ok || echo not_okay
```

### Time

Once MQTT is connected, this code expects an MQTT message to be sent
to it -- at least once -- so it can learn what the local time is.
See [**_parse_localtime_message()**](https://github.com/flavio-fernandes/kitchen_clock/blob/main/kitchen_clock.py#L266)
for an example of what that looks like

```text
topic: /aio/local_time  payload: 2021-05-18 23:23:36.339 015 5 -0500 EST
```

### Topics

These are the MQTT topics you can publish to the clock:

```python
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
```

Example commands

```bash
PREFIX='matrix_portal'
MQTT=192.168.10.238

# Subscribing to status messages
mosquitto_sub -F '@Y-@m-@dT@H:@M:@S@z : %q : %t : %p' -h $MQTT -t "${PREFIX}/status"

# Request general info
mosquitto_pub -h $MQTT -t "${PREFIX}/ping" -r -n

# Turn screen on/off
mosquitto_pub -h $MQTT -t "${PREFIX}/brightness" -m on
mosquitto_pub -h $MQTT -t "${PREFIX}/brightness" -m off

# Neopixel control
mosquitto_pub -h $MQTT -t "/${PREFIX}/neopixel" -m 0        ; # off
mosquitto_pub -h $MQTT -t "/${PREFIX}/neopixel" -m 0xff     ; # blue
mosquitto_pub -h $MQTT -t "/${PREFIX}/neopixel" -m 0xff00   ; # green
mosquitto_pub -h $MQTT -t "/${PREFIX}/neopixel" -m 0xff0000 ; # red

# On board led blink
mosquitto_pub -h $MQTT -t "/${PREFIX}/blinkrate" -m 0    ; # off
mosquitto_pub -h $MQTT -t "/${PREFIX}/blinkrate" -m 0.1  ; # 100ms

# Messages
mosquitto_pub -h $MQTT -t "/${PREFIX}/msg" -m foo

mosquitto_pub -h $MQTT -t "/${PREFIX}/msg" -m \
  '{"msg": "hello", "text_color": "#0x595dff", "timeout": 40, "x": "center"}'

mosquitto_pub -h $MQTT -t "/${PREFIX}/msg" -m \
  '{"msg": "hi", "no_scroll": "True", "x": -10}'

mosquitto_pub -h $MQTT -t "/${PREFIX}/msg" -m '{"msg": "hi scroll"}'

mosquitto_pub -h $MQTT -t "/${PREFIX}/msg" -n ; # clear

# Animations
mosquitto_pub -h $MQTT -t "/${PREFIX}/img" -m 'parrot'

mosquitto_pub -h $MQTT -t "/${PREFIX}/img" -m '{"img": "sine.bmp" }'

mosquitto_pub -h $MQTT -t "/${PREFIX}/img" -m '{"img": "bmps/rings.bmp", "timeout": 10 }'

mosquitto_pub -h $MQTT -t "/${PREFIX}/img" -n ; # clear
```
