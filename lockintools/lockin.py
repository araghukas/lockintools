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

try:
    from serial.tools import list_ports

    IMPORTED_LIST_PORTS = True
except ValueError:
    IMPORTED_LIST_PORTS = False

from .options import SETTINGS_DICT

# link to usb-serial driver for macOS
_L1 = "http://www.prolific.com.tw/UserFiles/files/PL2303HXD_G_Driver_v2_0_0_20191204.zip"

# blog post explaining how to bypass blocked extensions
# need this because no Big Sur version of driver as of Jan 7 2020.
_L2 = "https://eclecticlight.co/2019/06/01/how-to-bypass-mojave-10-14-5s-new-kext-security/"


class LockInError(Exception):
    """named exception for LockIn serial port connection issues"""
    pass


class LockIn(object):
    """
    represents a usable connection with the lock-in amp.
    """
    PRINT_BLANK = "({:>3d} : {:>10,.2f} Hz) x_ave, y_ave = {:.4e}, {:.4e} [V]"

    @staticmethod
    def get_serial(comm_port):
        return serial.Serial(comm_port,
                             baudrate=19200,
                             parity=serial.PARITY_NONE,
                             stopbits=serial.STOPBITS_ONE,
                             bytesize=serial.EIGHTBITS,
                             timeout=3)

    DEFAULT_PORTS = {
        'darwin': ['/dev/cu.usbserial-1410'],
        'win32': ['COM5'],
        'linux': ['/dev/ttyUSB0']
    }

    def __init__(self, comm_port: str = None):
        # (detect os and) set communication port
        self._comm = None
        if comm_port is not None:
            try:
                self._comm = LockIn.get_serial(comm_port)
            except serial.SerialException:
                print("lockintools: could not connect to port: %s" % comm_port)
        else:
            print("lockintools: trying default ports for platform: %s" % sys.platform)
            for cp in LockIn.DEFAULT_PORTS[sys.platform]:
                try:
                    self._comm = LockIn.get_serial(cp)
                    break
                except serial.SerialException:
                    print("lockintools: could not connect to port: %s" % cp)

            if self._comm is None and IMPORTED_LIST_PORTS:
                print("lockintools: tying to detect port and auto-connect...")
                for cp_match in list_ports.grep("(usb|USB)"):
                    cp_str = str(cp_match).split('-')[0].strip()
                    try:
                        self._comm = LockIn.get_serial(cp_str)
                        break
                    except serial.SerialException:
                        print("lockintools: could not connect to port: %s" % cp_str)

        if self._comm is None:
            raise LockInError("lockintools: CONNECTION FAILED! Do you have a driver installed?")
        print("lockintools: SUCCESS! Connection established.")
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

    def get_reading(self, ch, meas_time=0.1, stdev=False):
        """
        read average value from channel `ch` over `meas_time` seconds
        optionally, also return standard deviation (`stdev=True`)
        """
        if not (ch == 1 or ch == 2):
            raise ValueError("channel `ch` should be 1 or 2")

        self.cmd("REST")
        self.cmd("STRT")
        time.sleep(meas_time)
        self.cmd("PAUS")
        N = self.cmd("SPTS?")
        r_str = self.cmd("TRCA?" + str(ch) + ",0," + N)
        r = [float(ri) for ri in r_str.split(',')[:-1]]
        if stdev:
            return np.mean(r), np.std(r)
        return np.mean(r)

    def get_x(self, meas_time=0.1, stdev=False):
        return self.get_reading(ch=1, meas_time=meas_time, stdev=stdev)

    def get_y(self, meas_time=0.1, stdev=False):
        return self.get_reading(ch=2, meas_time=meas_time, stdev=stdev)

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

                # self._print("waiting for stabilization at f = {:.4f} Hz "
                #             "({:d}/{:d})".format(freq, j + 1, len(freqs)))

                self.set_freq(freq)
                self.cmd('REST')
                time.sleep(stb_time)

                # self._print('taking measurement')
                # beep(repeat=1)
                self.cmd('STRT')
                time.sleep(meas_time)
                self.cmd('PAUS')

                # self._print('extracting values')
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
                    warnings.warn("buffer array overflow encountered at point "
                                  "f = {:.1f} Hz, V = {:.1f} volts"
                                  .format(freq, V))
                    X[i, j] = x[:L_MAX]
                    Y[i, j] = y[:L_MAX]

                x_ = np.mean(x[~np.isnan(x)])
                y_ = np.mean(y[~np.isnan(y)])
                self._print(LockIn.PRINT_BLANK.format(j + 1, freq, x_, y_))
                # self._print('')

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
                dV_x[i, j] = np.std(_X_)
                dV_y[i, j] = np.std(_Y_)

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
        for key, sweep_data in kwargs.items():
            if hasattr(self, key):
                if isinstance(sweep_data, SweepData):
                    self.__setattr__(key, sweep_data)
                else:
                    raise ValueError("keyword argument '{}' is an not instance "
                                     "of `lck_tools.SweepData` class"
                                     .format(sweep_data))
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
        for name, sweep_data in zip(['Vs_3w', 'Vs_1w', 'Vsh_1w'],
                                    [self.Vs_3w, self.Vs_1w, self.Vsh_1w]):

            # skip empty data sets
            if sweep_data is None:
                continue

            # recall each `Data` is an instance of `SweepData`
            V_x_file_path = (self.DIR
                             + '_'.join(['{}'.format(name), sweep_data.ID])
                             + '.xlsx')
            V_y_file_path = (self.DIR
                             + '_'.join(['{}_o'.format(name), sweep_data.ID])
                             + '.xlsx')

            with pd.ExcelWriter(V_x_file_path) as writer:
                sweep_data.V_x.to_excel(writer, sheet_name='val')
                sweep_data.dV_x.to_excel(writer, sheet_name='var')

            with pd.ExcelWriter(V_y_file_path) as writer:
                sweep_data.V_y.to_excel(writer, sheet_name='val')
                sweep_data.dV_y.to_excel(writer, sheet_name='var')

        print("saved sweep data in '{}'".format(self.DIR))

    def save_tc3omega(self, ampl):
        self.init_save()
        for name, sweep_data in zip(['Vs_3w', 'Vs_1w', 'Vsh_1w'],
                                    [self.Vs_3w, self.Vs_1w, self.Vsh_1w]):
            if sweep_data is None:
                raise ValueError("no recorded data for attribute '{}'"
                                 .format(name))

        if not (np.all(self.Vs_1w.freqs == self.Vs_3w.freqs)
                and np.all(self.Vs_1w.freqs == self.Vsh_1w.freqs)):
            raise IndexError("frequencies don't match across scans")

        if not (ampl in self.Vs_1w.Vs and ampl in self.Vs_3w.Vs
                and ampl in self.Vsh_1w.Vs):
            raise ValueError("specified voltage not found in every scan")

        # unpack DataFrames into arrays
        # values
        _Vs_3w = self.Vs_3w.V_x[ampl].values
        _Vs_1w = self.Vs_1w.V_x[ampl].values
        _Vsh_1w = self.Vsh_1w.V_x[ampl].values
        _Vs_3w_o = self.Vs_3w.V_y[ampl].values
        _Vs_1w_o = self.Vs_1w.V_y[ampl].values
        _Vsh_1w_o = self.Vsh_1w.V_y[ampl].values
        # standard deviation of values
        _dVs_3w = self.Vs_3w.dV_x[ampl].values
        _dVs_1w = self.Vs_1w.dV_x[ampl].values
        _dVsh_1w = self.Vsh_1w.dV_x[ampl].values
        _dVs_3w_o = self.Vs_3w.dV_y[ampl].values
        _dVs_1w_o = self.Vs_3w.dV_y[ampl].values
        _dVsh_1w_o = self.Vsh_1w.dV_y[ampl].values

        # write voltage values
        V_output = np.array([_Vs_3w, _Vs_3w_o,
                             _Vs_1w, _Vs_1w_o,
                             _Vsh_1w, _Vsh_1w_o])
        V_columns = ['Vs_3w', 'Vs_3w_o',
                     'Vs_1w', 'Vs_1w_o',
                     'Vsh_1w', 'Vsh_1w_o']

        V_output_df = pd.DataFrame(V_output.T, columns=V_columns)
        V_output_df.insert(0, 'freq', self.Vs_1w.freqs)

        V_file_name = 'tc3omega_data_{}_V'.format(ampl) + '.csv'
        V_output_df.to_csv(self.DIR + V_file_name, index=False)
        print("saved tc3omega digest in '{}'".format(self.DIR))

        # write voltage errors
        dV_output = np.array([_dVs_3w, _dVs_3w_o,
                              _dVs_1w, _dVs_1w_o,
                              _dVsh_1w, _dVsh_1w_o])
        dV_columns = ['dVs_3w', 'dVs_3w_o',
                      'dVs_1w', 'dVs_1w_o',
                      'dVsh_1w', 'dVsh_1w_o']

        dV_output_df = pd.DataFrame(dV_output.T, columns=dV_columns)
        dV_output_df.insert(0, 'freq', self.Vs_1w.freqs)

        dV_file_name = 'tc3omega_data_{}_V'.format(ampl) + '.error.csv'
        dV_output_df.to_csv(self.DIR + dV_file_name, index=False)
        print("saved tc3omega error digest in '{}'".format(self.DIR))
