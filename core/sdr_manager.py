# HFGCSpy/core/sdr_manager.py
# Version: 2.0.14 # Version bump for dynamic rtlsdr device discovery

import numpy as np
import logging
import time # For potential delays in error recovery

# Import the main RtlSdr class. We will dynamically find get_devices/find_devices.
from rtlsdr import RtlSdr 
# No longer attempting to import get_devices or util directly at module level

logger = logging.getLogger(__name__)

class SDRManager:
    def __init__(self, device_identifier=0, sample_rate=2.048e6, center_freq=8.992e6, gain='auto', ppm_correction=0):
        self.sdr = None
        self.device_identifier = device_identifier # Can be int index or string serial
        self.sample_rate = sample_rate
        self.center_freq = center_freq
        self.gain = gain
        self.ppm_correction = ppm_correction
        self._is_open = False # Track SDR open state

    @staticmethod
    def list_sdr_devices_serials():
        """
        Lists available RTL-SDR devices by their serial numbers.
        This method attempts various ways to find the device listing function.
        Returns a list of strings (serial numbers).
        """
        devices = []
        sdr_device_getter = None

        # Attempt 1: rtlsdr.get_devices() (most common for modern pyrtlsdr)
        try:
            import rtlsdr # Re-import locally to ensure module-level access
            if hasattr(rtlsdr, 'get_devices'):
                sdr_device_getter = rtlsdr.get_devices
                logger.debug("Using rtlsdr.get_devices() for device listing.")
        except AttributeError:
            pass # Try next method
        except Exception as e:
            logger.warning(f"rtlsdr.get_devices() failed with unexpected error: {e}")

        # Attempt 2: rtlsdr.RtlSdr.get_devices() (static method)
        if sdr_device_getter is None:
            try:
                if hasattr(RtlSdr, 'get_devices'):
                    sdr_device_getter = RtlSdr.get_devices
                    logger.debug("Using rtlsdr.RtlSdr.get_devices() for device listing.")
            except AttributeError:
                pass # Try next method
            except Exception as e:
                logger.warning(f"rtlsdr.RtlSdr.get_devices() failed with unexpected error: {e}")

        # Attempt 3: rtlsdr.util.find_devices() (older/utility submodule)
        if sdr_device_getter is None:
            try:
                import rtlsdr.util # Try importing the util submodule
                if hasattr(rtlsdr.util, 'find_devices'):
                    sdr_device_getter = rtlsdr.util.find_devices
                    logger.debug("Using rtlsdr.util.find_devices() for device listing.")
            except (ImportError, AttributeError):
                pass # No more methods to try
            except Exception as e:
                logger.warning(f"rtlsdr.util.find_devices() failed with unexpected error: {e}")

        if sdr_device_getter:
            try:
                sdr_devices = sdr_device_getter()
                for dev in sdr_devices:
                    # Ensure dev object has a serial_number attribute
                    if hasattr(dev, 'serial_number'):
                        devices.append(dev.serial_number)
                    else:
                        logger.warning(f"Detected SDR device without serial_number attribute: {dev}")
                logger.info(f"Successfully detected {len(devices)} SDR devices: {devices}.")
            except Exception as e:
                logger.critical(f"CRITICAL ERROR: Found a device listing function but it failed to execute: {e}", exc_info=True)
        else:
            logger.critical("CRITICAL ERROR: Could not find any suitable SDR device listing function in 'rtlsdr'. "
                            "This indicates a severe incompatibility or broken installation of pyrtlsdr.")
        return devices

    def open_sdr(self):
        if self._is_open:
            logger.info(f"SDR device {self.device_identifier} already open.")
            return

        try:
            # Use RtlSdr from the imported rtlsdr module
            if isinstance(self.device_identifier, str):
                self.sdr = RtlSdr(serial_number=self.device_identifier)
            else:
                self.sdr = RtlSdr(self.device_identifier)

            # Set parameters after SDR object is created and confirmed
            self.sdr.sample_rate = self.sample_rate
            self.sdr.center_freq = self.center_freq
            self.sdr.gain = self.gain
            self.sdr.freq_correction = self.ppm_correction
            
            self._is_open = True
            logger.info(f"SDR opened: Device='{self.device_identifier}' (Serial: {self.sdr.serial_number if hasattr(self.sdr, 'serial_number') else 'N/A'}), Sample Rate={self.sdr.sample_rate/1e6:.2f} Msps, "
                        f"Center Freq={self.sdr.center_freq/1e6:.3f} MHz, "
                        f"Gain={self.sdr.gain} dB, PPM={self.sdr.freq_correction}")
        except Exception as e:
            logger.error(f"Failed to open SDR device '{self.device_identifier}': {e}", exc_info=True)
            self.sdr = None 
            self._is_open = False
            # Add a small delay on failure to prevent rapid re-attempts
            time.sleep(1)

    def close_sdr(self):
        if self.sdr and self._is_open:
            self.sdr.close()
            logger.info(f"SDR device '{self.device_identifier}' closed.")
        self.sdr = None
        self._is_open = False

    def capture_samples(self, num_samples):
        if not self.sdr or not self._is_open:
            # logger.error(f"SDR device '{self.device_identifier}' not initialized or not open. Cannot capture samples.")
            return np.array([])
        try:
            samples = self.sdr.read_samples(num_samples)
            return samples
        except Exception as e:
            logger.error(f"Error capturing samples from SDR device '{self.device_identifier}': {e}", exc_info=True)
            # Attempt to re-open SDR if it seems disconnected or glitched
            logger.info(f"Attempting to re-open SDR device '{self.device_identifier}' after capture error.")
            self.close_sdr()
            self.open_sdr() # Try to re-open
            return np.array([])

    def set_frequency(self, frequency_hz):
        if self.sdr and self._is_open:
            try:
                self.sdr.center_freq = frequency_hz
                self.center_freq = frequency_hz # Update internal state
                logger.debug(f"SDR device '{self.device_identifier}' tuned to {frequency_hz / 1e6:.3f} MHz.")
            except Exception as e:
                logger.error(f"Error setting SDR device '{self.device_identifier}' frequency to {frequency_hz}: {e}", exc_info=True)
        else:
            logger.warning(f"SDR device '{self.device_identifier}' not open. Cannot set frequency.")

    def calculate_rssi(self, samples):
        """
        Calculates the Received Signal Strength Indicator (RSSI) from complex samples.
        RSSI is typically proportional to the average power of the signal.
        Returns RSSI in dB.
        """
        if samples.size == 0:
            return -float('inf') # Return negative infinity for no samples
        
        # Calculate power from complex samples (I^2 + Q^2)
        power = np.mean(np.abs(samples)**2)
        
        # Convert to dBm (assuming 1mW reference, adjust if different reference is needed)
        # For RTL-SDR, raw power values are relative, so dBFS is more appropriate.
        # A common way for relative power is 10 * log10(mean_power)
        if power > 0:
            rssi_db = 10 * np.log10(power)
        else:
            rssi_db = -100 # Very low value for zero or negative power
        
        return rssi_db
