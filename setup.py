from setuptools import setup, find_packages

setup(
   name='livetube',
   version='1.2.5',
   description='A module for youtube livestream',
   url="https://github.com/sam01101/livetube",
   author='Sam',
   author_email='lau.sam745033858@gmail.com',
   packages=find_packages(),
   install_requires=['aiohttp']
)
