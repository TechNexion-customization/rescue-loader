#!/bin/bash

detect_touch () {
for i in /sys/class/input/input?
do
  inputname=$(cat ${i}/name)
  eventid=$(ls ${i} | grep event[0-9])
  case "$inputname" in
  EP000*|EP079*|EP082*|EP085*|EP0510*|EP0512*)
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/$eventid"
    export QWS="-touch -qws"
    inputevent="/dev/input/$eventid"
    return
    ;;
  *EXC3146*|*EXC3160*|*P80H60*|*P80H100*)
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/$eventid"
    export QWS="-touch -qws"
    inputevent="/dev/input/$eventid"
    return
    ;;
  *Usb*Mouse|*USB*Mouse)
    export QWS_MOUSE_PROTO="linuxinput:/dev/input/$eventid"
    export QWS="-qws"
    inputevent="/dev/input/$eventid"
    ;;
  *)
    export QWS="-qws"
    inputevent="/dev/input/$eventid"
    return
    ;;
  esac
done
}

detect_panel () {
inch=""
panelwidth=""
panelheight=""
if [ -d /sys/bus/mipi-dsi/devices ]; then
  for i in /sys/bus/mipi-dsi/devices/*
  do
    panel=$(cat ${i}/uevent)
    case "$panel" in
    *ili9881c*)
      # directly connected mipi-dsi panel
      inch="5"
      return
      ;;
    *g080uan01*)
      # directly connected mipi-dsi panel
      inch="8"
      return
      ;;
    *g101uan02*)
      # directly connected mipi-dsi panel
      inch="10"
      return
      ;;
    *m101nwwb*)
      # connected lvds panel
      inch="10"
      return
      ;;
    *g156xw01*)
      # connected lvds panel
      inch="15"
      return
      ;;
    *g215hvn01*)
      # connected lvds panel
      inch="21"
      return
      ;;
    *dsi2lvds*)
      # handles lvds panels via sn65dsi84 MIPI-LVDS bridge.
      if [ -r ${i}/of_node/panel-width-mm -a -r ${i}/of_node/panel-height-mm ]; then
        panelwidth="$(( 16#$(hexdump -s2 -e '/1 "%02x"' ${i}/of_node/panel-width-mm | sed s,^0*,,g) ))"
        panelheight="$(( 16#$(hexdump -s2 -e '/1 "%02x"' ${i}/of_node/panel-height-mm | sed s,^0*,,g) ))"
        echo "WxH: $panelwidth x $panelheight"
        return
      fi
      ;;
    *)
      ;;
    esac
  done
fi
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
      fi
      if grep -q "BG" "/sys/class/graphics/fb${count}/name"; then
        FBS+=( $count )
      elif [ -d /sys/bus/mipi-dsi/devices ]; then
        FBS+=( $count )
      fi
    fi
    count=$(( $count + 1 ))
  done
}

setup_multi () {
  # e.g. QWS_DISPLAY="Multi: LinuxFb:/dev/fb0 LinuxFb:/dev/fb2"
  if [ ${#FBS[@]} -gt 1 ]; then
    fbsetting="Multi: "
  else
    fbsetting=""
  fi
}

setup_transform () {
  # e.g. QWS_DISPLAY="Transformed:rot270:LinuxFb:mmWidth140:mmHeight68:/dev/fb0"
  dimension=""
  for fb in ${FBS[@]}
  do
    # portraight or landscape
    W=$(cat "/sys/class/graphics/fb${fb}/virtual_size" | cut -d"," -f1)
    H=$(cat "/sys/class/graphics/fb${fb}/virtual_size" | cut -d"," -f2)
    if [ $W -lt $H ]; then
      fbsetting="${fbsetting}Transformed:rot270:"
      portraight=${fb}
      rotate="-90"
      inputevent="${inputevent}:rotate=270"
    fi

    #
    # workout the dimensions for smaller panels for default font size calculation by Qt
    # W:H ratio are usually 1.6:1 ===> 1.5:1
    #
    if [ "$inch" != "" ]; then
      case "$inch" in
      5)
        dimension="mmWidth195:mmHeight110:" # 720x1280
        ww="275"
        hh="172"
        ;;
      8)
        dimension="mmWidth275:mmHeight172:" # 1200,1920
        ;;
      10)
        dimension="mmWidth347:mmHeight217:" # 1920x1200
        ;;
      15)
        dimension="mmWidth550:mmHeight344:" # 1920x1200
        ;;
      21)
        dimension="mmWidth762:mmHeight476:" # 1920x1200
        ;;
      esac
      return
    fi
    if [ "${panelwidth}" != "" -a "${panelheight}" != "" ]; then
      # 5' : 110(mm)x62(mm)
      # 7' : 163(mm)x95(mm)
      # 8' : 172(mm)x107(mm)
      # 10': 217(mm)x135(mm)
      # 15': 344(mm)x193(mm)
      # 21': 476(mm)x268(mm)
      hh=$panelwidth
      ww=$(( $panelwidth * $panelwidth / $panelheight ))
      dimension="mmWidth${ww}:mmHeight${hh}:"
      return
    fi
  done
}

setup_display () {
  if [ -n $fbmain ]; then
    fbsetting="${fbsetting}LinuxFb:${dimension}/dev/fb${fbmain} "
  fi
  for fb in ${FBS[@]}
  do
    if [ "$fb" = "$fbmain" ]; then
      continue
    fi
    fbsetting="${fbsetting}LinuxFb:${dimension}/dev/fb${fb} "
  done
}

#
# entry point
#
export DBUS_SESSION_BUS_ADDRESS="unix:path=/var/run/dbus/session_bus_socket"
detect_touch
detect_panel
detect_screen_size
setup_multi
setup_transform
setup_display

qwsdisp=$(echo "${fbsetting}" | xargs)
echo "DISPLAY: ${qwsdisp}"
echo "INPUT: ${inputevent}"

if ! grep -q "wayland" <<< $QT_QPA_PLATFORM; then
  export QT_QPA_PLATFORM="eglfs"
  export QT_QPA_EGLFS_INTEGRATION="eglfs_viv"
  export QT_QPA_EGLFS_ROTATION="${rotate}"
  export QT_QPA_EGLFS_PHYSICAL_WIDTH="${ww}"
  export QT_QPA_EGLFS_PHYSICAL_HEIGHT="${hh}"
  export QT_QPA_EVDEV_TOUCHSCREEN_PARAMETERS="${inputevent}"
fi

/usr/bin/python3 /usr/lib/python3.7/site-packages/tsl/guiview.py
