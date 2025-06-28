# HFGCSpy/core/sdr_manager.py
# Version: 0.0.1

import numpy as np
from rtlsdr import RtlSdr
import logging

logger = logging.getLogger(__name__)

class SDRManager:
    def __init__(self, device_index=0, sample_rate=2.048e6, center_freq=8.992e6, gain='auto', ppm_correction=0):
        self.sdr = None
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.center_freq = center_freq
        self.gain = gain
        self.ppm_correction = ppm_correction
        self._is_open = False # Track SDR open state

    def open_sdr(self):
        if self._is_open:
            logger.info("SDR already open.")
            return

        try:
            # Attempt to open SDR by device index or serial number if device_index is a string
            if isinstance(self.device_index, str):
                self.sdr = RtlSdr(serial_number=self.device_index)
            else:
                self.sdr = RtlSdr(self.device_index)

            self.sdr.sample_rate = self.sample_rate
            self.sdr.center_freq = self.center_freq
            self.sdr.gain = self.gain
            self.sdr.freq_correction = self.ppm_correction
            self._is_open = True
            logger.info(f"SDR opened: Device={self.sdr.valid_devices[self.device_index].serial_number if self.device_index in self.sdr.valid_devices else self.device_index}, Sample Rate={self.sdr.sample_rate/1e6:.2f} Msps, "
                        f"Center Freq={self.sdr.center_freq/1e6:.3f} MHz, "
                        f"Gain={self.sdr.gain} dB, PPM={self.sdr.freq_correction}")
        except Exception as e:
            logger.error(f"Failed to open SDR device {self.device_index}: {e}", exc_info=True)
            self.sdr = None 
            self._is_open = False

    def close_sdr(self):
        if self.sdr and self._is_open:
            self.sdr.close()
            logger.info("SDR device closed.")
        self.sdr = None
        self._is_open = False

    def capture_samples(self, num_samples):
        if not self.sdr or not self._is_open:
            logger.error("SDR not initialized or not open. Cannot capture samples.")
            return np.array([])
        try:
            samples = self.sdr.read_samples(num_samples)
            return samples
        except Exception as e:
            logger.error(f"Error capturing samples from SDR: {e}", exc_info=True)
            # Attempt to re-open SDR if it seems disconnected or glitched
            self.close_sdr()
            logger.info("Attempting to re-open SDR after capture error.")
            self.open_sdr()
            return np.array([])

    def set_frequency(self, frequency_hz):
        if self.sdr and self._is_open:
            try:
                self.sdr.center_freq = frequency_hz
                self.center_freq = frequency_hz # Update internal state
                logger.info(f"SDR tuned to {frequency_hz / 1e6:.3f} MHz.")
            except Exception as e:
                logger.error(f"Error setting SDR frequency to {frequency_hz}: {e}", exc_info=True)
        else:
            logger.warning("SDR not open. Cannot set frequency.")

    # You would add more methods here for:
    # - Stream samples continuously (e.g., using a callback)
    # - Basic DSP (e.g., FFT for spectrum, basic demodulation functions)
    # - More advanced signal detection
    # - Specific HFGCS and JS8 signal processing (this will be the bulk of DSP work)
