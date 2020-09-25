#!/bin/bash

detect_touch () {
for i in /sys/class/input/input?
do
  if ( grep -qE "EP000|EP079|EP082|EP085|EP0510|EP0512|EXC3146|EXC3160|P80H100" ${i}/name ); then
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/event1"
    export QWS="-touch -qws"
    return
  elif ( grep -qE "P80H60" ${i}/name ); then
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/event1"
    export QWS="-touch -qws"
    return
  elif ( grep -qE "ADS7846" ${i}/name ); then
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/event1"
    export QWS="-touch -qws"
    return
  else
    export QWS="-qws"
  fi
done
}

export DBUS_SESSION_BUS_ADDRESS="unix:path=/var/run/dbus/session_bus_socket"
W=$(fbset | grep geometry | awk '{print $2}')
H=$(fbset | grep geometry | awk '{print $3}')
if (( $W < $H )); then
  export QWS_DISPLAY="transformed:mmWidth140:mmHeight68:rot270 directfb:0"
else
  export QWS_DISPLAY="directfb:0"
fi

detect_touch
/usr/bin/python3 /usr/lib/python3.5/site-packages/rescue_loader/guiview.py $QWS

