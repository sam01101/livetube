from setuptools import setup, find_packages

setup(
   name='livetube',
   version='1.2',
   description='A module for youtube livestream',
   author='Sam',
   author_email='lau.sam745033858@gmail.com',
   packages=find_packages(),
   install_requires=['aiohttp']
)
