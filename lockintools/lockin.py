"""
Created on Thu Nov 7, 2019

@author: Pedro and Ara
"""

import serial  # `pyserial` package; NOT `serial` package
import warnings
import pandas as pd
import numpy as np
import time
import os
import sys

from datetime import datetime

from .settings import SETTINGS_DICT


class LockIn(object):
    """
    represents a usable connection with the lock-in amp.
    """

    def __init__(self, comm_port=None):

        # (detect os and) set communication port
        if comm_port is None:
            if sys.platform == 'darwin':
                self.comm_port = '/dev/cu.usbserial'

            elif sys.platform == 'win32':
                self.comm_port = 'COM5'

            else:
                raise ValueError("must specify `comm_port` if not using MacOS"
                                 "or Windows")
        else:
            self.comm_port = comm_port

        # set serial port property
        try:
            self._comm = serial.Serial(self.comm_port,
                                       baudrate=19200,
                                       parity=serial.PARITY_NONE,
                                       stopbits=serial.STOPBITS_ONE,
                                       bytesize=serial.EIGHTBITS,
                                       timeout=3)
        except serial.SerialException:
            print("FAILED to connect! Please check connection.")
            if sys.platform == 'darwin':
                print("make sure the driver is installed:\n"
                      "https://pbxbook.com/other/sw/PL2303_MacOSX_1_6_0.zip")

        self.print_to_stdout = True

    @property
    def comm(self):
        # `serial.Serial` object for handling communications
        return self._comm

    def close(self):
        """closes communication port"""
        if self.comm.is_open:
            self.comm.close()

    def open(self):
        """(re)-opens communication port"""
        if not self.comm.is_open:
            self.comm.open()

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
        """set lock-in amp. frequency"""
        command = 'FREQ' + str(freq)
        return self.cmd(command)

    def set_ampl(self, ampl):
        """set lock-in amp. voltage amplitude"""
        if ampl > 5.:
            raise ValueError("can not exceed amplitude of 5V")
        command = 'SLVL' + str(ampl)
        return self.cmd(command)

    def set_sens(self, sens):
        """set lock-in amp. sensitivity"""
        if 0 <= sens <= 26:
            self.cmd('SENS' + str(sens))
        else:
            raise ValueError("sensitivity setting must be between 0 (1 nV) and "
                             "26 (1 V)")

    def set_harm(self, harm):
        """set lock-in amp. detection harmonic"""
        harm = int(harm)
        if 1 <= harm <= 19999:
            self.cmd('HARM' + str(harm))
        else:
            raise ValueError("harmonic must be between 1 and 19999")

    def sweep(self, label: str, freqs, ampls, sens: int, harm: int,
              stb_time: float = 9.,
              meas_time: float = 1.,
              ampl_time: float = 5.,
              L_MAX: int = 50):
        """
        Conduct a frequency sweep measurement across one or more voltage
        amplitudes.

        :param label: (string) label for the sweep data
        :param freqs: (scalar or array-like) freqs. to sweep over
        :param ampls: (scalar or array-like) amplitudes to sweep over
        :param sens: (int) integer indicating lock-in amp. sensitivity setting
        :param harm: (int) detection harmonic
        :param stb_time: (float) time (s) for stabilization at each freq.
        :param meas_time: (float) time (s) for data collection at each freq.
        :param ampl_time: (float) time (s) for stabilization at each voltage
        :param L_MAX: (int) maximum data array size
        :return: (lockin.SweepData) container of pandas `DataFrame`s for
                 in- and out-of-phase detected voltages, and variances thereof
        """

        self.set_harm(harm)
        self.set_sens(sens)

        ampls = np.asarray(ampls)
        freqs = np.asarray(freqs)

        if ampls.ndim == 0:
            ampls = ampls[None]

        if freqs.ndim == 0:
            freqs = freqs[None]

        # buffer arrays for in- and out-of-phase data
        X = np.full((len(ampls), len(freqs), L_MAX), fill_value=np.nan)
        Y = np.full((len(ampls), len(freqs), L_MAX), fill_value=np.nan)

        for i, V in enumerate(ampls):

            self._print('V = {:.2f} volts'.format(V))
            self._print('waiting for stabilization after amplitude change...')

            self.set_ampl(V)
            time.sleep(ampl_time)

            for j, freq in enumerate(freqs):

                self._print('waiting for stabilization at f = {:.0f} Hz'
                            .format(freq))

                self.set_freq(freq)
                self.cmd('REST')
                time.sleep(stb_time)

                self._print('taking measurement')
                # beep(repeat=1)
                self.cmd('STRT')
                time.sleep(meas_time)
                self.cmd('PAUS')

                self._print('extracting values')
                N = self.cmd('SPTS?')

                x_str = self.cmd('TRCA?1,0,' + N)
                y_str = self.cmd('TRCA?2,0,' + N)

                # list of values measured at a single point
                # last character is a newline character
                x = np.array([float(x_) for x_ in x_str.strip().split(',')])
                y = np.array([float(y_) for y_ in y_str.strip().split(',')])

                try:
                    X[i, j][:len(x)] = x
                    Y[i, j][:len(x)] = y
                except ValueError:
                    warnings.warn("buffer array overflow encountered at point "
                                  "f = {:.1f} Hz, V = {:.1f} volts"
                                  .format(freq, V))
                    X[i, j] = x[:L_MAX]
                    Y[i, j] = y[:L_MAX]

                self._print('')

        return SweepData(X, Y, freqs, ampls, label, sens, harm)

    def get_config(self):
        raw_config = {}
        for key in SETTINGS_DICT.keys():
            if key != 'names':
                raw_config[key] = self.cmd(key + '?')
        return raw_config

    def _print(self, s):
        if self.print_to_stdout:
            print(s)


class SweepData(object):
    """
    Contains the data relevant to a single sweep.

    i.e. the amplitude of the oscillations described by the `harm`th harmonic of
    the voltage measured across the heater line or shunt, for a driving
    voltage `V` in `Vs` at a frequency `freq` in `freqs`.

    The digested values (ex: `V_x[i]` and `dV_x[i]) at each point are the
    average of many measurements at that point and the variance of those
    measurements.
    """

    def __init__(self, X, Y, freqs, Vs, label, sens, harm):
        dt1 = datetime.now()
        dt = dt1.strftime("%d-%m-%Y_%H-%M")
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


class LockInData(object):
    """
    contains and manages the data of various sweeps
    """

    # TODO: consider standardizing data objects with `tc3omega` package.

    def __init__(self, working_dir=None, create_dir=None, **kwargs):

        if working_dir is None:
            self.working_dir = os.getcwd()
        else:
            self.working_dir = os.path.expanduser(working_dir)

        self.create_dir = create_dir
        self.directory_created = False
        self.DIR = None  # absolute path to directory where files are saved

        self.Vs_3w = None
        self.Vs_1w = None
        self.Vsh_1w = None

        self.add_sweeps(**kwargs)

    def add_sweeps(self, **kwargs):
        for key, Data in kwargs.items():
            if hasattr(self, key):
                if isinstance(Data, SweepData):
                    self.__setattr__(key, Data)
                else:
                    raise ValueError("keyword argument '{}' is an not instance "
                                     "of `lck_tools.SweepData` class"
                                     .format(Data))
            else:
                raise ValueError("keyword argument '{}' is not one of "
                                 "'Vs_3w', 'Vs_1w', or 'Vsh_1w'.".format(key))

    def init_save(self):
        if self.directory_created:
            return

        if self.create_dir is None:
            self.create_dir = 'recorded_' + str(datetime.date(datetime.now()))

        # check if created directory name conflicts with any that already exist
        name_conflict = True
        d = 0
        os.chdir(self.working_dir)
        while name_conflict:
            try:
                os.mkdir(self.create_dir)
                name_conflict = False
            except FileExistsError:
                if d == 0:
                    self.create_dir += '(1)'
                    d += 1
                else:
                    self.create_dir = self.create_dir.replace('({})'.format(d),
                                                              '')
                    d += 1
                    self.create_dir += '({})'.format(d)
        self.directory_created = True
        self.DIR = '/'.join([self.working_dir, self.create_dir, ''])

    def save_all(self):
        self.init_save()
        for name, Data in zip(['Vs_3w', 'Vs_1w', 'Vsh_1w'],
                              [self.Vs_3w, self.Vs_1w, self.Vsh_1w]):

            # skip empty data sets
            if Data is None:
                continue

            # recall each `Data` is an instance of `SweepData`
            V_x_file_path = (self.DIR
                             + '_'.join(['{}'.format(name), Data.ID])
                             + '.xlsx')
            V_y_file_path = (self.DIR
                             + '_'.join(['{}_o'.format(name), Data.ID])
                             + '.xlsx')

            with pd.ExcelWriter(V_x_file_path) as writer:
                Data.V_x.to_excel(writer, sheet_name='val')
                Data.dV_x.to_excel(writer, sheet_name='var')

            with pd.ExcelWriter(V_y_file_path) as writer:
                Data.V_y.to_excel(writer, sheet_name='val')
                Data.dV_y.to_excel(writer, sheet_name='var')

        print("saved sweep data in '{}'".format(self.DIR))

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

        # unpack dataframes into arrays
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
