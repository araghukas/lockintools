# input configuration
ISRC = {
    '0': 'A',
    '1': 'A-B',
    '2': 'I (MOhm)',
    '3': 'I (100 MOhm)'
}

# input grounding configuration
IGND = {
    '0': 'FLOAT',
    '1': 'GROUND'
}

# input coupling configuration
ICPL = {
    '0': 'AC',
    '1': 'DC'
}

# sensitivity
SENS = {
    '0': '2 nV/fA',
    '1': '5 nV/fA',
    '2': '10 nV/fA',
    '3': '20 nV/fA',
    '4': '50 nV/fA',
    '5': '100 nV/fA',
    '6': '200 nV/fA',
    '7': '500 nV/fA',
    '8': '1 uV/pA',
    '9': '2 uV/pA',
    '10': '5 uV/pA',
    '11': '10 uV/pA',
    '12': '20 uV/pA',
    '13': '50 uV/pA',
    '14': '100 uV/pA',
    '15': '200 uV/pA',
    '16': '500 uV/pA',
    '17': '1 mV/nA',
    '18': '2 mV/nA',
    '19': '5 mV/nA',
    '20': '10 mV/nA',
    '21': '20 mV/nA',
    '22': '50 mV/nA',
    '23': '100 mV/nA',
    '24': '200 mV/nA',
    '25': '500 mV/nA',
    '26': '1 V/uA'
}

# dynamic reserve mode
RMOD = {
    '0': 'HIGH RESERVE',
    '1': 'NORMAL',
    '2': 'LOW NOISE',
}

# time constant
OFLT = {
    '0': '10 us',
    '1': '30 us',
    '2': '100 us',
    '3': '300 us',
    '4': '1 ms',
    '5': '3 ms',
    '6': '10 ms',
    '7': '30 ms',
    '8': '100 ms',
    '9': '300 ms',
    '10': '1 s',
    '11': '3 s',
    '12': '10 s',
    '13': '30 s',
    '14': '100 s',
    '15': '300 s',
    '16': '1 ks',
    '17': '3 ks',
    '18': '10 ks',
    '19': '30 ks'
}

# low pass filter slope
OFSL = {
    '0': '6 dB/oct',
    '1': '12 dB/oct',
    '2': '18 dB/oct',
    '3': '24 dB/oct'
}

SETTINGS_DICT = dict(
    ISRC=ISRC,
    IGND=IGND,
    ICPL=ICPL,
    SENS=SENS,
    RMOD=RMOD,
    OFLT=OFLT,
    OFSL=OFSL,
    names={
        'ISRC': 'input',
        'IGND': 'grounding',
        'ICPL': 'input coupling',
        'SENS': 'sensitivity',
        'RMOD': 'dynamic reserve',
        'OFLT': 'time constant',
        'OFSL': 'low pass filter slope'
    }
)
