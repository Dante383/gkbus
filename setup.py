from setuptools import find_packages, setup

setup(
	name='gkbus',
	packages=find_packages(),
	version='0.1.67',
	description='High-level KWP over K-line/CANbus library',
	author='Dante383',
	setup_requires=['pyftdi', 'scapy', 'pyserial']
)
