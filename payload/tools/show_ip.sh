#!/bin/sh
IP=$(ifconfig wlan0 2>/dev/null | sed -n 's/.*inet addr:\([^ ]*\).*/\1/p')
eips -c
eips 0 0 "Kindle IP: ${IP:-not connected}"
