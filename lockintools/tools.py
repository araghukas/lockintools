"""
Created on Thu Nov 7, 2019

@author: Pedro and Ara
"""

import serial  # `pyserial` package NOT `serial` package
import warnings
import pandas as pd
import numpy as np
import time
import os
import sys
import simpleaudio as sa
from datetime import datetime
from lockintools.settings import SETTINGS_DICT


class LockIn(object):
    """
    represents a usable connection with the lock-in amp.
    """

    def __init__(self, comm_port=None):
        if comm_port is None:
            if sys.platform == 'darwin':
                # for Macs; note this requires the driver at:
                # https://pbxbook.com/other/sw/PL2303_MacOSX_1_6_0.zip
                self.comm_port = '/dev/cu.usbserial'

            elif sys.platform == 'win32':
                self.comm_port = 'COM5'

            else:
                raise ValueError("must specify `comm_port` if not using MacOS or Windows")
        else:
            self.comm_port = comm_port
        try:
            self.comm = serial.Serial(self.comm_port, baudrate=19200, parity=serial.PARITY_NONE,
                                      stopbits=serial.STOPBITS_ONE, bytesize=serial.EIGHTBITS,
                                      timeout=3)
        except serial.SerialException:
            print("FAILED to connect!")
            if sys.platform == 'darwin':
                print("make sure the driver is installed:\n"
                      "https://pbxbook.com/other/sw/PL2303_MacOSX_1_6_0.zip")

    def close(self):
        """closes communication port"""

        if self.comm.is_open:
            self.comm.close()
        return

    def open(self):
        """(re)-opens communication port"""

        if not self.comm.is_open:
            self.comm.open()
        return

    def cmd(self, command):
        """execute arbitrary lockin command"""

        self.comm.write(str.encode(command + '\n'))
        self.comm.flush()
        if '?' in command:
            state = bytes.decode(self.comm.readline())
            return state
        else:
            return

    def set_freq(self, freq):
        """set frequency"""

        command = 'FREQ' + str(freq)
        return self.cmd(command)

    def set_ampl(self, ampl):
        """set voltage oscillation amplitude"""

        if ampl > 5.:
            raise ValueError("can not exceed amplitude of 5V")
        command = 'SLVL' + str(ampl)
        return self.cmd(command)

    def set_sens(self, sens):
        """set sensitivity"""

        if 0 <= sens <= 26:
            self.cmd('SENS' + str(sens))
        else:
            raise ValueError("sensitivity setting must be between 0 (1 nV) and 26 (1 V)")

    def set_harm(self, harm):
        """set detection harmonic"""

        if 1 <= harm <= 19999:
            self.cmd('HARM' + str(harm))
        else:
            raise ValueError

    def sweep(self, label, freqs, Vs, sens, harm,
              stb_time=9, mes_time=1, ampl_time=5, disp=False, L_MAX=50):

        self.set_harm(harm)
        self.set_sens(sens)

        Vs = np.asarray(Vs)
        freqs = np.asarray(freqs)

        if Vs.ndim == 0:
            Vs = Vs[None]

        if freqs.ndim == 0:
            freqs = freqs[None]

        X = np.full((len(Vs), len(freqs), L_MAX), fill_value=np.nan)
        Y = np.full((len(Vs), len(freqs), L_MAX), fill_value=np.nan)

        for i, V in enumerate(Vs):
            self.set_ampl(V)
            printornot('V = {:.2f} volts'.format(V), disp)
            printornot('waiting for stabilization after amplitude change...', disp)
            time.sleep(ampl_time)
            for j, freq in enumerate(freqs):
                printornot('', disp)
                self.set_freq(freq)

                printornot('waiting for stabilization at f = {:.0f} HZ'
                           .format(freq), disp)
                self.cmd('REST')
                time.sleep(stb_time)

                printornot('taking measurement', disp)
                # beep(repeat=1)
                self.cmd('STRT')
                time.sleep(mes_time)
                self.cmd('PAUS')

                printornot('extracting values', disp)
                N = self.cmd('SPTS?')

                x_str = self.cmd('TRCA?1,0,' + N)
                y_str = self.cmd('TRCA?2,0,' + N)

                # list of values measured at a single point
                # last character is a newline character
                x = np.array([float(_) for _ in x_str.split(',')[:-1]])
                y = np.array([float(_) for _ in y_str.split(',')[:-1]])

                try:
                    X[i, j][:len(x)] = x
                    Y[i, j][:len(x)] = y
                except ValueError:
                    warnings.warn("buffer overflow encountered at point "
                                  "f = {:.1f} Hz, V = {:.1f} volts"
                                  .format(freq, V))
                    X[i, j] = x[:L_MAX]
                    Y[i, j] = y[:L_MAX]

                printornot('', disp)

        return SweepData(X, Y, freqs, Vs, label, sens, harm)

    def get_config(self):
        raw_config = {}
        for key in SETTINGS_DICT.keys():
            if key != 'names':
                raw_config[key] = self.cmd(key + '?')
        return LockInStatus(raw_config)

    def set_config(self, file_path):
        """set lock in configuration from file"""
        pass


class SweepData(object):
    """
    Contains the data relevant to a single sweep.

    i.e. the amplitude of the oscillations described by the `harm`th harmonic of the voltage measured across the
    heater line (or shunt), for a driving voltage `V` in `Vs` at a frequency `freq` in `freqs`.

    The digested values (ex: `V_x[i]` and `dV_x[i]) at each point are the average of many measurements at that point
    and the variance of those measurements.
    """

    def __init__(self, X, Y, freqs, Vs, label, sens, harm):
        dt1 = datetime.now()
        dt = dt1.strftime("%d-%m-%Y_%H:%M:%S")
        self.ID = '_'.join([label, 'HARM' + str(harm), 'SENS' + str(sens), dt])

        # frequency and voltage ranges
        self.freqs = freqs
        self.Vs = Vs

        # full raw buffer output from lock-in (padded with NaNs)
        self.X = X
        self.Y = Y

        n = len(freqs)
        m = len(Vs)

        # initialing arrays for digests
        V_x = np.zeros((m, n))  # in-phase amplitudes (left lockin display)
        V_y = np.zeros((m, n))  # out-of-phase amplitudes (right lockin display)
        dV_x = np.zeros((m, n))  # variances of buffer outputs over time
        dV_y = np.zeros((m, n))  # variances of buffer output over time

        for i in range(m):
            for j in range(n):
                _X_ = X[i, j]
                _Y_ = Y[i, j]

                _X_ = _X_[~np.isnan(_X_)]
                _Y_ = _Y_[~np.isnan(_Y_)]

                V_x[i, j] = np.mean(_X_)
                V_y[i, j] = np.mean(_Y_)
                dV_x[i, j] = np.var(_X_)
                dV_y[i, j] = np.var(_Y_)

        # converting to DataFrames for readability
        self.V_x = pd.DataFrame(V_x.T, index=freqs, columns=Vs)
        self.V_y = pd.DataFrame(V_y.T, index=freqs, columns=Vs)
        self.dV_x = pd.DataFrame(dV_x.T, index=freqs, columns=Vs)
        self.dV_y = pd.DataFrame(dV_y.T, index=freqs, columns=Vs)

    def __call__(self):
        print("data ID: {}".format(self.ID))


class LockInData(object):
    """
    contains and manages measurement data in chunks that are instances of `SweepData`, above
    """

    # TODO: consider standardizing data objects with `tc3omega` module.

    def __init__(self, new_directory=None, **kwargs):

        self.new_directory = new_directory
        self.directory_created = False
        self.DIR = None

        self.Vs_3w = None
        self.Vs_1w = None
        self.Vsh_1w = None

        for key, Data in kwargs.items():
            if hasattr(self, key):
                if Data.__class__ is SweepData:
                    self.__setattr__(key, Data)
                else:
                    raise ValueError("keyword argument '{}' is an not instance of "
                                     "`lck_tools.SweepData` class".format(Data))
            else:
                raise ValueError("keyword argument '{}' is not one of "
                                 "'Vs_3w', 'Vs_1w', or 'Vsh_1w'.".format(key))

    def init_save(self):
        if self.directory_created:
            return

        if self.new_directory is None:
            self.new_directory = 'recorded_' + str(datetime.date(datetime.now()))

        name_conflict = True
        counter = 0
        while name_conflict:
            try:
                os.mkdir(self.new_directory)
                name_conflict = False
            except FileExistsError:
                if counter == 0:
                    self.new_directory += '(1)'
                    counter += 1
                else:
                    self.new_directory = self.new_directory.replace('({})'.format(counter), '')
                    counter += 1
                    self.new_directory += '({})'.format(counter)
        self.directory_created = True

        self.DIR = '/'.join([os.getcwd(), self.new_directory]) + '/'

    def save_all(self):
        self.init_save()
        for name, Data in zip(['Vs_3w', 'Vs_1w', 'Vsh_1w'],
                              [self.Vs_3w, self.Vs_1w, self.Vsh_1w]):

            # skip empty data sets
            if Data is None:
                warnings.warn("no recorded data for attribute '{}'"
                              .format(name))
                continue

            # recall each `Data` is an instance of `SweepData`
            V_x_file_path = self.DIR + '_'.join(['({})'.format(name), Data.ID]) + '.xlsx'
            V_y_file_path = self.DIR + '_'.join(['({}_o)'.format(name), Data.ID]) + '.xlsx'

            with pd.ExcelWriter(V_x_file_path) as writer:
                Data.V_x.to_excel(writer, sheet_name='val')
                Data.dV_x.to_excel(writer, sheet_name='var')

            with pd.ExcelWriter(V_y_file_path) as writer:
                Data.V_y.to_excel(writer, sheet_name='val')
                Data.dV_y.to_excel(writer, sheet_name='var')

        print("saved all sweeps in '{}'".format(self.DIR))
        return

    def save_tc3omega(self, ampl):
        self.init_save()
        for name, Data in zip(['Vs_3w', 'Vs_1w', 'Vsh_1w'],
                              [self.Vs_3w, self.Vs_1w, self.Vsh_1w]):
            if Data is None:
                raise ValueError("no recorded data for attribute '{}'"
                                 .format(name))

        if not (np.all(self.Vs_1w.freqs == self.Vs_3w.freqs)
                and np.all(self.Vs_1w.freqs == self.Vsh_1w.freqs)):
            raise IndexError("frequencies don't match across scans")

        if not (ampl in self.Vs_1w.Vs and ampl in self.Vs_3w.Vs
                and ampl in self.Vsh_1w.Vs):
            raise ValueError("specified voltage not found in every scan")

        # TODO: I don't like this one bit; too clumsy, too much not DNR

        _Vs_3w = self.Vs_3w.V_x[ampl].values
        _Vs_1w = self.Vs_1w.V_x[ampl].values
        _Vsh_1w = self.Vsh_1w.V_x[ampl].values

        _Vs_3w_o = self.Vs_3w.V_y[ampl].values
        _Vs_1w_o = self.Vs_1w.V_y[ampl].values
        _Vsh_1w_o = self.Vsh_1w.V_y[ampl].values

        output = np.array([_Vs_3w, _Vs_3w_o,
                           _Vs_1w, _Vs_1w_o,
                           _Vsh_1w, _Vsh_1w_o])

        columns = ['Vs_3w', 'Vs_3w_o',
                   'Vs_1w', 'Vs_1w_o',
                   'Vsh_1w', 'Vsh_1w_o']

        output_df = pd.DataFrame(output.T, columns=columns)
        output_df.insert(0, 'freq', self.Vs_1w.freqs)

        file_name = 'tc3omega_data_{}_V'.format(ampl) + '.csv'

        output_df.to_csv(self.DIR + file_name, index=False)

        print("saved tc3omega digest in '{}'".format(self.DIR))
        return


class LockInStatus(object):
    """
    NOT QUITE READY

    contains relevant lock-in amplifier settings
    """

    def __init__(self, raw_config):
        self.raw_config = raw_config
        self.config = {}
        for key in raw_config:
            readable_key = SETTINGS_DICT['names'][key]
            self.config[readable_key] = SETTINGS_DICT[key][raw_config[key].strip('\r')]
        return

    def __call__(self):
        for key in self.config:
            print("{: <20} {: >30}"
                  .format(key, self.config[key]))

    def save(self, path):
        """save configuration"""
        pass

    @classmethod
    def from_file(cls, file_path):
        """parse text in file; convert to raw_config;"""
        raw_config = 'not this string but the parsed dict read from a file'
        return cls(raw_config)


def beep(freq=440, duration=1, repeat=3, wait_time=0.5):
    """
    plays a beep sound
    """
    sample_rate = 44100
    t = np.linspace(0, duration, duration * sample_rate, False)
    note = np.sin(freq * t * 2 * np.pi)
    audio = note * (2**15 - 1) / np.max(np.abs(note))
    audio = audio.astype(np.int16)

    for i in range(repeat):
        play_obj = sa.play_buffer(audio, 1, 2, sample_rate)
        play_obj.wait_done()
        time.sleep(wait_time)


def freqspace(f_min, f_max, N):
    """
    creates array of `N` exponentially increasing values between `f_min` and `f_max`
    """
    return np.round([f_min * (f_max / f_min)**(i / (N - 1)) for i in range(N)])


def printornot(string, disp):
    """
    is there a better way to optionally suppress prints?
    """
    if not disp:
        return
    print(string)
