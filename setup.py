import distutils.dir_util
from distutils.command import build
import os, sys, re
try:
    import setuptools
    from setuptools import setup, find_packages
    from setuptools.command import install
except ImportError:
    sys.stderr.write("Warning: could not import setuptools; falling back to distutils.\n")
    from distutils.core import setup
    from distutils.command import install

from beeactions.version import get_version

long_description = """BeeActions is a tool to help analyse actions performed by animals
(Bees for instance) and record the time when one of the registered
actions are done. A set of configurable shortcuts is used for quick
registration of the actions while a chronometer register the elapsed time
since the start of the acquisition"""

with open('README.rst') as fd:
    long_description = fd.read()

setupOpts = dict(
    name='beeactions',
    description='Bee Behaviour Temporal Analysis',
    long_description='',
    license='CECILL-B',
    url='',
    author='Sébastien Weber',
    author_email='sebastien.weber@cemes.fr',
    classifiers = [
        "Programming Language :: Python :: 3",
        "Development Status :: 5 - Production/Stable",
        "Environment :: Other Environment",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Human Machine Interfaces",
        "Topic :: Scientific/Engineering :: Visualization",
        "License :: CeCILL-B Free Software License Agreement (CECILL-B)",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: User Interfaces",
        ],)

def listAllPackages(pkgroot):
    path = os.getcwd()
    n = len(path.split(os.path.sep))
    subdirs = [i[0].split(os.path.sep)[n:] for i in os.walk(os.path.join(path, pkgroot)) if '__init__.py' in i[2]]
    return ['.'.join(p) for p in subdirs]


allPackages = (listAllPackages(pkgroot='pymodaq')) #+
               #['pyqtgraph.'+x for x in helpers.listAllPackages(pkgroot='examples')])



def get_packages():

    packages=find_packages()
    for pkg in packages:
        if 'hardware.' in pkg:
            packages.pop(packages.index(pkg))
    return packages

allPackages = get_packages()



setup(
    version=get_version(),
     #cmdclass={'build': Build,},
    #           'install': Install,
    #           'deb': helpers.DebCommand,
    #           'test': helpers.TestCommand,
    #           'debug': helpers.DebugCommand,
    #           'mergetest': helpers.MergeTestCommand,
    #           'style': helpers.StyleCommand},
    packages=allPackages,
    #package_dir={'examples': 'examples'},  ## install examples along with the rest of the source
    package_data={},
    entry_points={},
    python_requires='>=3.6, <3.8',
    install_requires=[
        'pymodaq>=2.0',
        ],
    include_package_data=True,
    **setupOpts
)

