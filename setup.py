from setuptools import setup, find_packages
from lockintools import __version__

setup(
    name="lockintools",
    version=__version__,
    description="Interface tools for Stanford Research Instruments lock-in amplifier "
    "model SR830 DSP (TM); used for 3ω thermal conductivity measurements.",
    author="Pedro Oliviera & Ara Ghukasyan",
    author_email="ghukasa@mcmaster.ca",
    py_modules=["tools", "settings", "measure"],
    packages=find_packages(),
    install_requires=["numpy",
                      "pandas",
                      "simpleaudio",
                      "pyserial",
                      "datetime",
                      "openpyxl"],
    zip_safe=False
)
