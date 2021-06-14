from setuptools import setup, find_packages

setup(
   name='livetube',
   version='2.0.1',
   description='A module for youtube livestream',
   url="https://github.com/sam01101/livetube",
   author='Sam',
   author_email='lau.sam745033858@gmail.com',
   packages=find_packages(),
   install_requires=['aiohttp']
)

""" Credit:
Hashing a dict: https://stackoverflow.com/a/22003440/15117344

SAPISIDHASH algorithm: https://stackoverflow.com/a/32065323/15117344


"""