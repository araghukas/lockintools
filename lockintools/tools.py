import time
import numpy as np
import simpleaudio as sa


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
    creates array of `N` exponentially increasing values from `f_min` to `f_max`
    """
    N = int(N)
    if f_min <= 0 or f_max <= 0:
        raise ValueError("frequencies must be positive non-zero")
    elif N <= 0:
        raise ValueError("number of elements in frequency range must be an "
                         "integer >= 1")
    return np.round([f_min * (f_max / f_min)**(i / (N - 1)) for i in range(N)])


def printornot(string, disp):
    """
    is there a better way to optionally suppress prints?
    """
    if not disp:
        return
    print(string)
