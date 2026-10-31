#!/bin/sh
# Builds gkbus_j2534_helper32.exe, the 32 bit Windows helper that loads 32 bit J2534 DLLs
# for a 64 bit Python. Needs mingw-w64 (Debian / Ubuntu: apt install gcc-mingw-w64-i686)
set -e
cd "$(dirname "$0")"
i686-w64-mingw32-gcc -std=c99 -O2 -Wall -Wextra -s -static \
	-Wl,--no-insert-timestamp \
	-o gkbus_j2534_helper32.exe j2534_helper.c
