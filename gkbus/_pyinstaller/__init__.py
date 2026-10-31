'''
PyInstaller hooks, found through the pyinstaller40 entry point - apps frozen with gkbus
get the 32 bit J2534 helper without changes to their spec
'''
import os


def get_hook_dirs () -> list[str]:
	return [os.path.dirname(os.path.abspath(__file__))]
