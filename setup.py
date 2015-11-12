#!/usr/bin/env python
# _*_ coding: utf-8 _*_
from setuptools import setup, find_packages
import os
import imp
import shutil

banner = """
██████╗ ███████╗██╗   ██╗██████╗ ███████╗██████╗ ███╗   ██╗███████╗████████╗██╗ ██████╗███████╗   
██╔══██╗██╔════╝╚██╗ ██╔╝██╔══██╗██╔════╝██╔══██╗████╗  ██║██╔════╝╚══██╔══╝██║██╔════╝██╔════╝   
██████╔╝███████╗ ╚████╔╝ ██████╔╝█████╗  ██████╔╝██╔██╗ ██║█████╗     ██║   ██║██║     ███████╗   
██╔═══╝ ╚════██║  ╚██╔╝  ██╔══██╗██╔══╝  ██╔══██╗██║╚██╗██║██╔══╝     ██║   ██║██║     ╚════██║   
██║     ███████║   ██║   ██████╔╝███████╗██║  ██║██║ ╚████║███████╗   ██║   ██║╚██████╗███████║██╗
╚═╝     ╚══════╝   ╚═╝   ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝ ╚═════╝╚══════╝╚═╝
"""
print banner

def non_python_files(path):
    """ Return all non-python-file filenames in path """
    result = []
    all_results = []
    module_suffixes = [info[0] for info in imp.get_suffixes()]
    ignore_dirs = ['cvs']
    for item in os.listdir(path):
        name = os.path.join(path, item)
        if (
            os.path.isfile(name) and
            os.path.splitext(item)[1] not in module_suffixes
            ):
            result.append(name)
        elif os.path.isdir(name) and item.lower() not in ignore_dirs:
            all_results.extend(non_python_files(name))
    if result:
        all_results.append((path, result))
    return all_results

data_files = non_python_files(os.path.join('synchrony', 'static'))
data_files.extend( non_python_files(os.path.join('synchrony', 'templates')))

try:
	fd           = open("requirements.txt")
	REQUIREMENTS = fd.read()
	fd.close()
except Exception, e:
	print "Error opening requirements.txt: " + e.strerror
	raise SystemExit

setup(name='Synchrony',
      version="0.0.1",
      description='A collaborative hyperdocument editor with distributed version control',
      author='Luke Brooks',
      author_email='luke@psybernetics.org.uk',
      url='http://psybernetics.org.uk/emissary',
      download_url = 'https://github.com/Psybernetics/Synchrony/tarball/1.0.0',
      data_files = data_files,
      packages=['synchrony', 'synchrony.resources', 'synchrony.controllers', 'synchrony.views', 'synchrony.streams', 'synchrony.tests'],
      include_package_data=True,
      install_requires=REQUIREMENTS.split('\n'),
      keywords=["p2p", "collaboration"]
)

print "Copying synchrony.py to /usr/bin/synchrony"
shutil.copyfile("./synchrony.py", "/usr/bin/synchrony")

print "Making /usr/bin/synchrony executable."
os.chmod("/usr/bin/synchrony", 0755)
print 'Check "synchrony --help" for options.'

