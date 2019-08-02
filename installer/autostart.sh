#!/bin/sh

loop=1
sleep 3

echo === Auto Start ==

while [ $loop == "1" ]
do
	if [ -d /sys/block/mmcblk0/mmcblk0p1 ]
	then
		mount /dev/mmcblk0p1 /media/sdcard -o ro
		loop=0
	else
		sleep 1
	fi
done

if [ -f /media/sdcard/image/script.sh ]
then
	cp /media/sdcard/image/script.sh /tmp/
	sed -i 's/^M//' /tmp/script.sh
	# fromdos /tmp/script.sh
	chmod +x /tmp/script.sh
else
	cp /home/rescue/script.sh /tmp/
fi

/tmp/script.sh

umount /media/sdcard
rm -f /tmp/script.sh

