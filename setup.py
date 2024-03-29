from distutils.core import setup
from setuptools import find_packages

setup(
	name='gkbus',
	packages=find_packages(),
	version='0.1.81',
	description='High-level KWP over K-line/CANbus library',
	author='Dante383',
	install_requires=['pyftdi==0.55.0', 'scapy==2.5.0', 'pyserial==3.5']
)
