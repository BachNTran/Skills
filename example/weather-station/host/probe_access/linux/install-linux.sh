#!/bin/sh
# Install the udev rule and add the current user to plugdev (needs sudo once).
set -eu
sudo install -m 0644 "$(dirname "$0")/99-stlink.rules" /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG plugdev "$USER"
echo "log out and back in, then: lsusb -d 0483:"
