#!/bin/sh
# Builds the openport-j2534 drivers gkbus ships with, from an openport-j2534 checkout
# (https://github.com/bisak/openport-j2534):
#
#   ./build.sh /path/to/openport-j2534 [tag or commit, HEAD by default] [windows zip]
#
# Builds what the machine has a compiler for and leaves the other drivers as they are:
# - the native library: linux-<machine>/libj2534.so (needs libusb-1.0-0-dev and pkg-config)
#   or macos/libj2534.dylib
# - win32/openport-j2534-32.dll and win64/openport-j2534-64.dll: taken from the release's
#   openport-j2534-<version>-windows.zip if it's given - what gkbus ships, they are the
#   DLLs upstream tested - and built with mingw-w64 otherwise (Debian / Ubuntu:
#   apt install gcc-mingw-w64)
#
# The tag or commit is built from a clean export, so the checkout's working tree isn't
# touched and uncommitted changes aren't shipped. VERSION says what was built.
set -e

[ -n "$1" ] || { echo "usage: $0 /path/to/openport-j2534 [tag or commit] [windows zip]" >&2; exit 1; }
source=$(cd "$1" && pwd)
ref=${2:-HEAD}
windows_zip=${3:+$(cd "$(dirname "$3")" && pwd)/$(basename "$3")}
drivers=$(cd "$(dirname "$0")" && pwd)

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git -C "$source" archive "$ref" | tar -x -C "$work"

# no debug info, and no build timestamp in the DLLs, so a rebuild of the same commit
# gives the same files
cflags='-O2'

case "$(uname -s)" in
	Linux) native="linux-$(uname -m)"; library=libj2534.so ;;
	Darwin) native=macos; library=libj2534.dylib ;;
	*) native= ;;
esac
if [ -n "$native" ]; then
	make -C "$work" CFLAGS="$cflags" "$library"
	mkdir -p "$drivers/$native"
	cp "$work/$library" "$drivers/$native/$library"
	strip -x "$drivers/$native/$library"
fi

if [ -n "$windows_zip" ]; then
	# the DLLs upstream's CI built and tested for the release
	unzip -q "$windows_zip" -d "$work/release"
	release=$(dirname "$(find "$work/release" -name SHA256SUMS.txt)")
	(cd "$release" && sha256sum -c --quiet SHA256SUMS.txt)
	for bits in 32 64; do
		mkdir -p "$drivers/win$bits"
		cp "$release/win$bits/openport-j2534-$bits.dll" "$drivers/win$bits/"
	done
else
	for bits in 32 64; do
		[ "$bits" = 32 ] && cc=i686-w64-mingw32-gcc || cc=x86_64-w64-mingw32-gcc
		if ! command -v "$cc" > /dev/null; then
			echo "no $cc, win$bits is not rebuilt" >&2
			continue
		fi
		dll="build/win$bits/openport-j2534-$bits.dll"
		# the linker flags ride on CC: the Makefile has no LDFLAGS, and derives dlltool from CC.
		# Stripped by the linker, strip would stamp the DLL with the time again
		make -C "$work" CC="$cc -s -Wl,--no-insert-timestamp" DLLTOOL="${cc%gcc}dlltool" \
			CFLAGS="$cflags" "$dll"
		mkdir -p "$drivers/win$bits"
		cp "$work/$dll" "$drivers/win$bits/"
	done
fi

cp "$work/LICENSE" "$work/NOTICE" "$drivers/"
# the tag if it's a release, v0.5.0-3-gabc1234 style otherwise
git -C "$source" describe --tags --always "$ref" > "$drivers/VERSION"
echo "built openport-j2534 $(cat "$drivers/VERSION")"
