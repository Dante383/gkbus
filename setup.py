from setuptools import find_packages, setup

setup(
	name='gkbus',
	packages=find_packages(),
	version='0.1.791',
	description='High-level KWP over K-line/CANbus library',
	author='Dante383',
	install_requires=['pyftdi==0.55.0', 'scapy==2.5.0', 'pyserial==3.5']
)
