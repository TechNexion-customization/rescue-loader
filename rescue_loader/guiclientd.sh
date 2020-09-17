#!/bin/bash

export DBUS_SESSION_BUS_ADDRESS="unix:path=/var/run/dbus/session_bus_socket"
if fbset | grep geometry | awk '{print (( test $2 < $3 ))}'; then
  export QWS_DISPLAY="transformed:mmWidth140:mmHeight68:rot270 directfb:0"
  export QWS_MOUSE_PROTO="linuxinput:/dev/input/event1"
else
  export QWS_DISPLAY="directfb:0"
fi
/usr/bin/python3 /usr/lib/python3.5/site-packages/rescue_loader/guiview.py -qws

