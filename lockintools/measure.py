from datetime import datetime
import numpy as np
import time

from .tools import freqspace, beep
from .lockin import LockIn, LockInData


class Measure3w(object):
    default_ranges = dict(freqs=freqspace(10, 15000, 10),
                          ampls=3.0)

    sample_1w_defaults = dict(sens=26,
                              stb_time=5,
                              meas_time=1,
                              ampl_time=5)

    sample_3w_defaults = dict(sens=22,
                              stb_time=10,
                              meas_time=1,
                              ampl_time=5)

    shunt_1w_defaults = dict(sens=22,
                             stb_time=5,
                             meas_time=1,
                             ampl_time=5)

    def __init__(self, freqs=None, ampls=None, lock=None, label=None,
                 working_dir=None, create_dir=None):
        self.freqs = freqs
        self.ampls = ampls
        self.lock = lock
        self.label = label
        self.lockindata = LockInData(working_dir, create_dir)

    @property
    def label(self):
        return self._label

    @label.setter
    def label(self, _label):
        if _label is None:
            time_stamp = datetime.now().strftime("%b_%d_%Y_%H-%M")
            self._label = '_'.join(['untitled', time_stamp])
        else:
            self._label = str(_label)

    @property
    def freqs(self):
        return self._freqs

    @freqs.setter
    def freqs(self, _freqs):
        if _freqs is None:
            self._freqs = Measure3w.default_ranges['freqs']
        else:
            self._freqs = _freqs

    @property
    def ampls(self):
        return self._ampls

    @ampls.setter
    def ampls(self, _ampls):
        if _ampls is None:
            self._ampls = Measure3w.default_ranges['ampls']
        else:
            self._ampls = _ampls

    @property
    def lock(self):
        return self._lock

    @lock.setter
    def lock(self, _lock):
        if _lock is None:
            self._lock = LockIn()
        elif isinstance(_lock, LockIn):
            self._lock = _lock
        else:
            raise ValueError("must assign `LockIn` object to this attribute")

    def sweep_sample1w(self, **kwargs):
        _kwargs = Measure3w.sample_1w_defaults.copy()
        for key, value in kwargs.items():
            _kwargs[key] = value

        print("sweeping sample 1-omega voltage")
        self.lock.set_coupling_mode("AC")
        # self.lock.set_input_mode("A")

        sweep_data = self.lock.sweep(label=self.label, freqs=self.freqs,
                                     ampls=self.ampls, harm=1, **_kwargs)
        self.lockindata.add_sweeps(Vs_1w=sweep_data)
        self.lockindata.save_all()

    def sweep_sample3w(self, **kwargs):
        _kwargs = Measure3w.sample_3w_defaults.copy()
        for key, value in kwargs.items():
            _kwargs[key] = value

        print("sweeping sample 3-omega voltage")
        self.lock.set_coupling_mode("AC")
        # self.lock.set_input_mode("A-B")

        sweep_data = self.lock.sweep(label=self.label, freqs=self.freqs,
                                     ampls=self.ampls, harm=3, **_kwargs)
        self.lockindata.add_sweeps(Vs_3w=sweep_data)
        self.lockindata.save_all()

    def sweep_shunt1w(self, countdown=True, count=30, **kwargs):
        _kwargs = Measure3w.shunt_1w_defaults.copy()
        for key, value in kwargs.items():
            _kwargs[key] = value

        if countdown:
            for i in range(count):
                if i % 10 == 0:
                    beep(freq=550, duration=.5, repeat=5)
                    print("switch input cables to shunt!")
                    print("proceeding in:")
                print(30 - i)
                time.sleep(1)

        print("sweeping shunt 1-omega voltage")
        self.lock.set_coupling_mode("AC")
        # self.lock.set_input_mode("A-B")

        sweep_data = self.lock.sweep(label=self.label, freqs=self.freqs,
                                     ampls=self.ampls, harm=1, **_kwargs)
        self.lockindata.add_sweeps(Vsh_1w=sweep_data)
        self.lockindata.save_all()

    def test_run(self):
        self.sweep_sample1w()
        self.sweep_sample3w()
        self.sweep_shunt1w(countdown=True, count=30)
        self.save_tc3omega()

    def save_tc3omega(self):
        if np.isscalar(self.ampls):
            self.lockindata.save_tc3omega(self.ampls)
        else:
            for ampl in self.ampls:
                self.lockindata.save_tc3omega(ampl)
