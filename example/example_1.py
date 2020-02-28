import lockintools.tools as lt
from lockintools.measure import Measure3w

"""
Make sure you've installed lockintools by running

    >>> pip install .

from the directory that contains `setup.py`

To run the code below:

    >>> python example_1.py
"""

if __name__ == "__main__":
    """ uncomment below for default test run """
    # m = Measure3w(new_directory='~/Desktop')
    # m.test_run()

    """ custom 3-omega measurement """
    # Default frequency and voltage amplitude ranges are used if not specified on instantiation:
    #
    # default_ranges = dict(freqs=freqspace(10, 15000, 10),
    #                       ampls=3.0)
    #

    m = Measure3w(working_dir='~/Desktop',
                  create_dir='test_run1',
                  label='custom_test',
                  freqs=lt.freqspace(10, 1000, 3))  # [10, 100, 1000] Hz

    # can provide LockIn.sweep() arguments as kwargs for the sweep methods below,
    # this includes:
    #
    #     sens : (required) sensitivity setting
    #     stb_time : (default 9) frequency stabilization wait time (in seconds)
    #     meas_time : (default 1) time reading data from lock-in's buffer
    #     ampl_time : (default 5) voltage stabilization wait time
    #     print_progress : (default True) logs measurements by printing each result

    m.sweep_sample1w(sens=26, stb_time=6.5, meas_time=0.5, ampl_time=2.9)
    m.sweep_sample3w()

    # Measure3w will use its defaults if kwargs are not passed to the sweep methods:
    #
    # sample_1w_defaults = dict(sens=26,
    #                           stb_time=5,
    #                           meas_time=1,
    #                           ampl_time=5)
    #
    # sample_3w_defaults = dict(sens=22,
    #                           stb_time=10,
    #                           meas_time=1,
    #                           ampl_time=5)
    #
    # shunt_1w_defaults = dict(sens=22,
    #                          stb_time=5,
    #                          meas_time=1,
    #                          ampl_time=5)

    # the shunt sweep has a (very primitive) warning built in to remind you to switch the BNC cables
    m.sweep_shunt1w(countdown=True, count=30)

    # finally, to save a tc3omega digest you must run
    m.save_tc3omega()

