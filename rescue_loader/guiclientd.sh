#!/bin/bash

detect_touch () {
for i in /sys/class/input/input?
do
  if ( grep -qEi "powerkey" ${i}/name ); then
    continue
  elif ( grep -qE "EP000|EP079|EP082|EP085|EP0510|EP0512" ${i}/name ) && ( grep -qE "18" ${i}/id/bustype ); then
    eventid=$(ls ${i} | grep event[0-9])
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/$eventid"
    export QWS="-touch -qws"
    return
  elif ( grep -qE "EXC3146|EXC3160|P80H60|P80H100" ${i}/name ) && ( grep -qE "3" ${i}/id/bustype ); then
    eventid=$(ls ${i} | grep event[0-9])
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/$eventid"
    export QWS="-touch -qws"
    return
  elif ( grep -qEi "USB.*MOUSE" ${i}/name ) && ( grep -qE "3" ${i}/id/bustype ); then
    eventid=$(ls ${i} | grep event[0-9])
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/$eventid"
    export QWS="-qws"
  else
    export QWS="-qws"
  fi
done

}

detect_screen_size () {
  # filter out overlays and figure out the virtual_size for each fb?
  W=99999
  H=99999
  FB=0
  FBS=()
  count=$(( $1-1 ))
  while [ $count -ge 0 ]
  do
    if ! grep -q "overlay" "/sys/class/graphics/fb${count}/fsl_disp_dev_property"; then
      dW=$(cat "/sys/class/graphics/fb${count}/virtual_size" | cut -d"," -f1)
      dH=$(cat "/sys/class/graphics/fb${count}/virtual_size" | cut -d"," -f2)
      if [ $dW -lt $W -a $dH -lt $H ]; then
        W=$dW
        H=$dH
        FB=$count
      fi
      FBS+=( $count )
    fi
    count=$(( $count-1 ))
  done
}

detect_display () {
  fbcount=$(ls -l /sys/class/graphics/fb? | wc -l)
  if [ "$fbcount" = "1" ]; then
    fbsetting="LinuxFb:/dev/fb0"
  else
    detect_screen_size $fbcount
    # e.g. QWS_DISPLAY="Multi: LinuxFb:/dev/fb0 LinuxFB:/dev/fb2"
    fbsetting="Multi: LinuxFb:/dev/fb${FB}"
    if [ ! $W -eq 99999 -a ! $H -eq 99999 ]; then
      for i in ${FBS[@]}
      do
        if [ ! $i -eq $FB ]; then
          fbsetting="$fbsetting LinuxFb:/dev/fb${i}"
        fi
      done
    fi
  fi
}

export DBUS_SESSION_BUS_ADDRESS="unix:path=/var/run/dbus/session_bus_socket"
detect_display
W=$(fbset | grep geometry | awk '{print $2}')
H=$(fbset | grep geometry | awk '{print $3}')
if (( $W < $H )); then
  export QWS_DISPLAY="Transformed:rot270:$fbsetting"
else
  export QWS_DISPLAY="$fbsetting"
fi

detect_touch

echo "QWS_DISPLAY: $QWS_DISPLAY"
echo "QWS_MOUSE_PROTO: $QWS_MOUSE_PROTO"
echo "QWS: $QWS"

/usr/bin/python3 /usr/lib/python3.5/site-packages/rescue_loader/guiview.py $QWS
