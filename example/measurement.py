from lockintools.tools import *

"""
Make sure you've installed lockintools by running

    >>> pip install .

from the directory that contains `setup.py`
"""

if __name__ = "__main__":

    # connect to lock-in
    lock = LockIn()

    # create frequency range
    freqs = freqspace(100, 15000, 30)

    # choose one voltage or provide list thereof
    Vs = 3.

    # create measurement object
    meas = Measurement(lock, freqs, Vs, label='BCB_Si_vac')

    # obtain relevant measurements
    meas.measure_sample3w(stb_time=8)
    meas.measure_sample1w(stb_time=5)
    meas.measure_shunt1w(stb_time=5)
    meas.save_all()
