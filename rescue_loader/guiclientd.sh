#!/bin/bash

detect_touch () {
for i in /sys/class/input/input?
do
  inputname=$(cat ${i}/name)
  case "$inputname" in
  EP000*|EP079*|EP082*|EP085*|EP0510*|EP0512*)
    eventid=$(ls ${i} | grep event[0-9])
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/$eventid"
    export QWS="-touch -qws"
    return
    ;;
  *EXC3146*|*EXC3160*|*P80H60*|*P80H100*)
    eventid=$(ls ${i} | grep event[0-9])
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/$eventid"
    export QWS="-touch -qws"
    return
    ;;
  *Usb*Mouse|*USB*Mouse)
    eventid=$(ls ${i} | grep event[0-9])
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/$eventid"
    export QWS="-qws"
    ;;
  *)
    export QWS="-qws"
    ;;
  esac
done
}

detect_screen_size () {
  fbcount=$(ls -l /sys/class/graphics/fb? | wc -l)
  # filter out overlays and figure out the virtual_size for each fb?
  FBS=()
  W=99999
  H=99999
  count=0
  while [ $count -lt $fbcount ]
  do
    # workout smallest resolution, the loop should get the first device of the
    # same resolution, therefore no need to check "overlay" in "fb?/fsl_disp_dev_property"
    if [ -f "/sys/class/graphics/fb${count}/virtual_size" ]; then
      dW=$(cat "/sys/class/graphics/fb${count}/virtual_size" | cut -d"," -f1)
      dH=$(cat "/sys/class/graphics/fb${count}/virtual_size" | cut -d"," -f2)
      if [ $dW -lt $W -a $dH -lt $H ]; then
        W=$dW
        H=$dH
        fbmain=$count
        FBS+=( $count )
      fi
    fi
    count=$(( $count + 1 ))
  done
}

detect_multi () {
  # e.g. QWS_DISPLAY="Multi: LinuxFb:/dev/fb0 LinuxFb:/dev/fb2"
  if [ ${#FBS[@]} -gt 1 ]; then
    fbsetting="Multi: "
  else
    fbsetting=""
  fi
}

detect_transform () {
  # e.g. QWS_DISPLAY="Transformed:rot270:LinuxFb:mmWidth140:mmHeight68:/dev/fb0"
  dimension=""
  for fb in ${FBS[@]}
  do
    W=$(cat "/sys/class/graphics/fb${fb}/virtual_size" | cut -d"," -f1)
    H=$(cat "/sys/class/graphics/fb${fb}/virtual_size" | cut -d"," -f2)
    if [ $W -lt $H ]; then
      fbsetting="${fbsetting}Transformed:rot270:"
      if grep -qE "EP000|EP079|EP082|EP085|EP0510|EP0512" <<< $inputname; then
        dimension="mmWidth140:mmHeight68:"
        portraight=${fb}
      fi
      return
    fi
  done
}

display_setting () {
  if [ -n $fbmain ]; then
    if [ "$fbmain" = "$portraight" ]; then
        fbsetting="${fbsetting}LinuxFb:${dimension}/dev/fb${fbmain} "
    else
        fbsetting="${fbsetting}LinuxFb:/dev/fb${fbmain} "
    fi
  fi
  for fb in ${FBS[@]}
  do
    if [ "$fb" = "$fbmain" ]; then
      continue
    fi
    if [ "$fb" = "$portraight" ]; then
        fbsetting="${fbsetting}LinuxFb:${dimension}/dev/fb${fb} "
    else
        fbsetting="${fbsetting}LinuxFb:/dev/fb${fb} "
    fi
  done
}

#
# entry point
#
export DBUS_SESSION_BUS_ADDRESS="unix:path=/var/run/dbus/session_bus_socket"
detect_touch
detect_screen_size
detect_multi
detect_transform
display_setting

qwsdisp=$(echo "${fbsetting}" | xargs)
export QWS_DISPLAY="$qwsdisp"

echo "QWS_DISPLAY: $QWS_DISPLAY"
echo "QWS_MOUSE_PROTO: $QWS_MOUSE_PROTO"
echo "QWS: $QWS"

/usr/bin/python3 /usr/lib/python3.5/site-packages/rescue_loader/guiview.py $QWS
