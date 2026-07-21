# kitchen_clock

#### CircuitPython based project for Adafruit MatrixPortal controlled via MQTT

This repo is a snapshot of all files and python script
needed to have time and messages displayed on a MatrixPortal.
This project uses an MQTT broker for obtaining the time as well as
displaying custom messages. There is also support for using
[Bitmap Pixel Art and Animation](https://learn.adafruit.com/pixel-art-matrix-display).
If you rather use a PyPortal, check out the [pyportal_station](https://github.com/flavio-fernandes/pyportal_station)
project.

[![Kitchen Clock Show-and-Tell](https://live.staticflickr.com/65535/52251360538_e63c498a2d_z.jpg)](https://youtu.be/DB5dh_nL3hY?t=1666)

### CircuitPython firmware

This board runs [CircuitPython 10.2.1](https://circuitpython.org/board/matrixportal_m4/), the
latest stable release that still supports the MatrixPortal M4 (samd51j19). To flash it:

1. Download the `.uf2` for `matrixportal_m4` from the link above.
2. Double-tap the reset button on the MatrixPortal to enter the UF2 bootloader; a `MATRIXBOOT`
   drive appears.
3. Drag the `.uf2` file onto `MATRIXBOOT`. The board reboots as `CIRCUITPY` running the new
   version.
4. Copy this repo's files onto `CIRCUITPY` (see "Copying files from cloned repo" below).

### Libraries

**Adafruit_CircuitPython_MiniMQTT**: Vendored as plain `.py` source (not `.mpy`) to keep readable
tracebacks, pulled from the [bundle 20260718](https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/tag/20260718)
`-py-` archive.

**Adafruit_CircuitPython_MatrixPortal**: Baseline from commit [6f1d9d4](https://github.com/adafruit/Adafruit_CircuitPython_MatrixPortal/commit/6f1d9d4b7af347cc94a47d379c8bb1f286a2d7b6)
and removing all the code I did not need.

Besides the 2 libraries above, this project uses the following awesome libraries from the
[bundle 10.x 20260718](https://github.com/adafruit/Adafruit_CircuitPython_Bundle/releases/tag/20260718):
```
Found device at /Volumes/CIRCUITPY, running CircuitPython 10.2.1.
- adafruit_bitmap_font==2.4.2
- adafruit_bus_device==5.2.17
- adafruit_connection_manager==3.1.8
- adafruit_display_text==5.0.4
- adafruit_esp32spi==11.1.3
- adafruit_logging==5.6.4
- adafruit_minimqtt==8.1.0
- adafruit_pixelbuf==2.0.12
- adafruit_requests==4.1.17
- adafruit_ticks==1.1.7
- neopixel==6.4.2
```

`adafruit_connection_manager` is a new addition: newer `adafruit_esp32spi` releases dropped the
old `adafruit_esp32spi_socket` module and `MQTT.set_socket()` pattern in favor of a socket-pool
(`adafruit_connection_manager.get_radio_socketpool()` / `get_radio_ssl_context()`) passed directly
to `MQTT.MQTT(...)` -- see `kitchen_clock.py`'s "Network Connection" section.

`adafruit_ticks` is also new: `adafruit_minimqtt` now depends on it directly
(`from adafruit_ticks import ticks_diff, ticks_ms`) for rollover-safe timing. It's a standalone
single-file library, not something our code imports directly.

`adafruit_display_shapes` was removed: the once-a-second "seconds" indicator used to be a fresh
`Line` object every tick, which allocates a new Bitmap/Palette/TileGrid 86400 times a day and
fragments the heap over long uptimes (this was the cause of the clock's animations slowing down
over time). It's now a single pre-allocated `displayio.Bitmap` repainted in place, which removed
the last user of that library.

You can probably use newer versions of the 10.x bundle as they come out; just keep the `.mpy`
files matched to the CircuitPython version flashed on the board (mixing bytecode versions will
fail to import).

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
mosquitto_pub -h $MQTT -t "${PREFIX}/neopixel" -m 0        ; # off
mosquitto_pub -h $MQTT -t "${PREFIX}/neopixel" -m 0xff     ; # blue
mosquitto_pub -h $MQTT -t "${PREFIX}/neopixel" -m 0xff00   ; # green
mosquitto_pub -h $MQTT -t "${PREFIX}/neopixel" -m 0xff0000 ; # red

# On board led blink
mosquitto_pub -h $MQTT -t "${PREFIX}/blinkrate" -m 0    ; # off
mosquitto_pub -h $MQTT -t "${PREFIX}/blinkrate" -m 0.1  ; # 100ms

# Messages
mosquitto_pub -h $MQTT -t "${PREFIX}/msg" -m foo

mosquitto_pub -h $MQTT -t "${PREFIX}/msg" -m \
  '{"msg": "hello", "text_color": "#0x595dff", "timeout": 40, "x": "center"}'

mosquitto_pub -h $MQTT -t "${PREFIX}/msg" -m \
  '{"msg": "..hi", "no_scroll": "True", "x": -10}'  ; # -10 value x will make the message omit the ".."

mosquitto_pub -h $MQTT -t "${PREFIX}/msg" -m '{"msg": "hi scroll"}'

mosquitto_pub -h $MQTT -t "${PREFIX}/msg" -n ; # clear

# Animations
mosquitto_pub -h $MQTT -t "${PREFIX}/img" -m 'parrot'

mosquitto_pub -h $MQTT -t "${PREFIX}/img" -m '{"img": "sine.bmp" }'

mosquitto_pub -h $MQTT -t "${PREFIX}/img" -m '{"img": "bmps/rings.bmp", "timeout": 10 }'

for x in cat fireworks hop parrot rings ruby sine ; do \
  mosquitto_pub -h $MQTT -t "${PREFIX}/img" -m $x
  sleep 10
done

mosquitto_pub -h $MQTT -t "${PREFIX}/img" -n ; # clear
```
