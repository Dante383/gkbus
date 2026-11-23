'''
The openport-j2534 drivers gkbus ships with, see gkbus/device/j2534/registry.py. Data files,
so they keep their place in the package and UPX leaves them alone
'''
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files('gkbus.device.j2534', includes=['drivers/**'])
