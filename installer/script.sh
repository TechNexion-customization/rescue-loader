#!/bin/sh

# suffix of framebuffer images to be installed
os=tn_generic

# file to be installed
image=`ls -1 /media/sdcard/image/*.xz | head -1`
if [ X$image = X ]
then
   image=/media/sdcard/image/image.xz
   os=tn_generic
fi

for i in 0 1 2
do
	for j in 0 1
	do
		if [ -e /dev/mmcblk${i}boot${j} ]
		then
			b=`expr ${j} + 1`
			echo Disabling boot partition ${b} of mmcblk${i} '(' mmcblk${i}boot${j} ')'
			mmc bootpart disable ${b} 1 /dev/mmcblk${i}
		fi
	done
done

os=`basename $image | sed 's/.xz//'`

target_calbfile_path=/dev/mmcblk2p2
# suffix of framebuffer images to be installed

# color of progress meter
# android green = a4ca39
# ubuntu orange = f47421
# yocto blue = 00ccff
# generic red = 451312

case "$os" in
"android")
     color=a4ca39
     ;;
"ubuntu")
     color=f47421
     ;;
"yocto")
     color=00ccff
     ;;
"tn_generic" | "image")
     color=451312
     ;;
*)
     os=image
     color=451312
     ;;
esac

cp /home/rescue/*.bgra.xz /tmp/

while [ ! -c /dev/fb0 ]
do
	usleep 250000
done

res=720x480
pic_w=720
pic_h=480
fb_w=`fbset | grep "mode " | sed -e 's/^mode\ "\(.*\)x\(.*\)-.*"/\1/'`
fb_h=`fbset | grep "mode " | sed -e 's/^mode\ "\(.*\)x\(.*\)-.*"/\2/'`
fb_d=`fbset | grep "geometry" | sed -e 's/.*geometry\s.*\s.*\s.*\s.*\s\(.*\)/\1/'`
calibrate=0

case "$fb_d" in
"16")
     clrspace=BGR
     ;;
"24")
     clrspace=BGR
     ;;
"32")
     clrspace=BGRA
     ;;
*)
     clrspace=BGRA
     ;;
esac

cd /tmp/

# Check if image file exists, or enter into OTG mass storage mode
if [ ! -e $image ] ; then
        modprobe g_mass_storage file=/dev/mmcblk2 stall=0 removable=1
	xzcat ${res}_install_tn_interactive_mode.bgra.xz | convert -size ${res} -depth 8 BGRA: -scale ${fb_w}x${fb_h}\! ${clrspace}:/dev/fb0
	exit 0
fi

lvds=`cat /proc/cmdline | grep ldb -i`
if [ "$lvds""X" != "X" ]
then
	calibrate=1
fi

lcd=`cat /proc/cmdline | grep lcd -i`
if [ "$lcd""X" != "X" ]
then
	calibrate=0
fi

#if there is no touch controller found, don't need to calibrate
#ads7846=`cat /proc/bus/input/devices | grep 'ADS7846 Touchscreen' -i`
if ( ! grep -q ADS7846 /proc/bus/input/devices 2>&1 > /dev/null )
then
        calibrate=0
fi

prism=`cat /proc/interrupts | grep prism -i`
if [ "$prism""X" != "X" ]
then
	calibrate=0
fi

if ( grep -iq eGalaxTouch /proc/bus/input/devices 2>&1 > /dev/null )
then
	calibrate=0
fi

if ( grep -q FT /proc/bus/input/devices 2>&1 > /dev/null )
then
        calibrate=0
fi

export TSLIB_CALIBFILE=/tmp/pointercal

if [ $calibrate = 0 ]
then
	xzcat ${res}_install_${os}1.bgra.xz | convert -size ${res} -depth 8 BGRA: -scale ${fb_w}x${fb_h}\! ${clrspace}:/dev/fb0
fi

# extract and dump image to the CPU eMMC/SD block device
echo 0 > /tmp/progress
max=`unxz -lv ${image} | grep "Uncompressed" | sed -e 's/.*(\(\w*\)\sB)/\1/'`
echo ${max} > /tmp/max
finfo=`basename ${image} .xz`\(`numfmt --to=iec-i --suffix=B ${max}`\)

/home/rescue/progress.sh ${color} &

( xzcat ${image} | pv -N ${finfo} -brp -s ${max} | dd of=/dev/mmcblk2 bs=1048576 oflag=dsync 2>/tmp/progress; echo wq | fdisk /dev/mmcblk2 )& pid=$!

if [ $calibrate = 1 ]
then
	ts_calibrate -t 20
	xzcat ${res}_install_${os}1.bgra.xz | convert -size ${res} -depth 8 BGRA: -scale ${fb_w}x${fb_h}\! ${clrspace}:/dev/fb0
fi
wait $pid

mkdir -p /tmp/new
if [ -f $TSLIB_CALIBFILE ]
then
	if [ X${os} = Xandroid ]
	then
		#copy calibrate file to /data in android
		target_calbfile_path=/dev/mmcblk2p4
	fi
	partprobe

	while [ ! -b $target_calbfile_path ]
	do
		usleep 250000
		sync
	done

	mount $target_calbfile_path /tmp/new && cp $TSLIB_CALIBFILE /tmp/new; umount /tmp/new
fi
mount /dev/mmcblk2p1 /tmp/new
cp -f /media/sdcard/image/uEnv.txt /tmp/new/
cp -f /media/sdcard/image/*dtb /tmp/new/
cp -f /media/sdcard/image/*scr /tmp/new/
cp -f /media/sdcard/image/*.{bmp,BMP} /tmp/new/
cp -f /media/sdcard/image/bootplash.* /tmp/new/
sync; sync; sync
umount /tmp/new

xzcat ${res}_install_${os}2.bgra.xz | convert -size ${res} -depth 8 BGRA: -scale ${fb_w}x${fb_h}\! ${clrspace}:/dev/fb0

sync; sync; sync

#xzcat ${res}_install_${os}3.bgra.xz | convert -size ${res} -depth 8 BGRA: -scale ${fb_w}x${fb_h}\! ${clrspace}:/dev/fb0

