from setuptools import setup, find_packages

setup(
   name='livetube',
   version='2.2.0',
   description='A module for youtube livestream',
   url="https://github.com/sam01101/livetube",
   author='Sam',
   author_email='sam@vtr.ac',
   packages=find_packages(),
   install_requires=['aiohttp', 'yarl', 'protobuf'],

)

""" Source:
Hashing a dict: https://stackoverflow.com/a/22003440/15117344

SAPISIDHASH algorithm: https://stackoverflow.com/a/32065323/15117344


"""