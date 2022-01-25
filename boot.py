import storage, usb_cdc
import usb_hid
import board, digitalio
import time
import usb_midi
import neopixel

buttonpins = (board.BUTTON_DOWN, board.BUTTON_UP)
buttons = []
for buttonpin in buttonpins:
    button = digitalio.DigitalInOut(buttonpin)
    button.pull = digitalio.Pull.UP
    buttons.append(button)

pixel_pin = board.NEOPIXEL
pixels = neopixel.NeoPixel(pixel_pin, 1, auto_write=True)
# RGB
pixels.fill((0, 0, 255))
time.sleep(3)
pixels.fill((0, 0, 0))

# Button is False when pressed
buttons_pressed = 0
for button in buttons:
    if not button.value:
        buttons_pressed += 1

if not buttons_pressed:
    # Disable devices only if button is not pressed.
    usb_midi.disable()
    storage.disable_usb_drive()
    usb_cdc.enable(console=False, data=False)
    usb_hid.disable()



