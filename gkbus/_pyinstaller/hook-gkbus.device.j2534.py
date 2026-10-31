'''
The 32 bit J2534 helper, see gkbus/device/j2534/bridge.py. A data file, so UPX leaves it alone
'''
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files('gkbus.device.j2534', includes=['helper/*.exe'])
