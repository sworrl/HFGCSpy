HFGCSpy - High-Frequency Global Communications System Spy
HFGCSpy is a powerful, self-contained application designed to turn your Raspberry Pi and an RTL-SDR dongle into a dedicated receiver for High-Frequency Global Communications System (HFGCS) and S2 GhostNet (JS8) traffic. It provides a modern, interactive web interface for real-time monitoring of decoded messages, along with capabilities to integrate and monitor public online SDRs.

This project is structured for easy deployment on Raspberry Pi devices, running as a background service with a locally hosted web UI, removing the need for continuous terminal interaction after setup.

Table of Contents
Features

Prerequisites

Installation

One-Line Install

Manual Setup (for development/debugging)

Usage

Accessing the Web UI

Web UI Overview

Configuring HFGCSpy (Important!)

Service Control

Project Structure

Contributing

License

Version

Features
Local SDR Monitoring: Directly interfaces with your RTL-SDR dongle (a dedicated dongle for HFGCSpy is recommended to avoid conflicts with other SDR software).

HFGCS Traffic Capture: Scans and processes various HFGCS transmissions including voice, EAMs (Encrypted Action Messages), and Skyking messages.

S2 GhostNet (JS8) Decoding: Supports decoding of JS8 mode traffic, commonly used by S2 GhostNet, without a graphical JS8Call client.

Persistent Data Storage: Decoded messages are stored in a local SQLite database (hfgcspy.db).

Interactive Web UI:

Modern, aesthetically pleasing dark mode interface.

Real-time display of captured messages with essential details.

Integrated audio playback for recorded transmissions.

Dynamic waveform visualization behind audio controls.

Configurable message display (messages per page).

Light/Dark mode toggle.

Tabbed interface for "Local SDR" and "Online SDR" messages.

Sub-tabs to filter messages by individual local SDRs or configured online SDRs.

Online SDR Integration: Ability to add and monitor public WebSDR or KiwiSDR streams (future expansion will support automatic data recording from these).

Background Service: Runs as a systemd service, ensuring 24/7 operation.

Apache2 Integration: Web UI served securely and efficiently via Apache2 with optional Let's Encrypt SSL detection.

Easy Setup: A single bash script handles most installation and configuration tasks.

Prerequisites
Hardware: Raspberry Pi (64-bit recommended, e.g., Pi 3B+, 4, 5) with a connected RTL-SDR USB dongle. (For simultaneous operation with other SDR software like OpenWebRX, a second RTL-SDR dongle is advised).

Operating System: Raspberry Pi OS (64-bit, e.g., Bookworm) or a compatible Debian-based 64-bit Linux distribution.

Network: Active internet connection during installation.

Privileges: sudo access.

Installation
The setup.sh script automates the entire installation process.

One-Line Install
To install HFGCSpy on your Raspberry Pi, run the following command in your terminal. This command will download the setup.sh script to a temporary location and execute it with root privileges.

sudo curl -o /tmp/setup.sh -fsSL https://raw.githubusercontent.com/sworrl/HFGCSpy/main/setup.sh && sudo chmod +x /tmp/setup.sh && sudo /tmp/setup.sh --install

During installation, the script will:

Update system packages and install necessary dependencies (Git, Python3, Apache2, rtl-sdr tools, etc.).

Prompt for desired application and web UI installation directories (defaults: /opt/hfgcspy and /var/www/html/hfgcspy). You can accept the defaults by pressing Enter.

Blacklist conflicting DVB-T kernel modules (requires a reboot for full effect).

Clone the HFGCSpy repository.

Set up a Python virtual environment and install Python dependencies.

Configure Apache2 to serve the web UI, including an option to set up HTTPS using detected Let's Encrypt certificates.

Create necessary data and recordings directories with correct permissions.

Ask if you want HFGCSpy to start automatically at boot (recommended).

Start the HFGCSpy background service.

After the installation completes, it is CRITICAL to reboot your Raspberry Pi:

sudo reboot

Manual Setup (for development/debugging)
For developers or those who prefer manual control, you can perform the steps outlined in the setup.sh script manually. This involves:

Installing dependencies (Python, rtl-sdr, Apache2).

Cloning the repository: git clone https://github.com/sworrl/HFGCSpy.git /opt/hfgcspy

Setting up the Python virtual environment and pip installing requirements.txt.

Configuring config.ini (see below).

Manually configuring Apache2 to serve the web UI (e.g., from /opt/hfgcspy/web_ui) and alias the data directory (e.g., /hfgcspy_data to /opt/hfgcspy/web_ui/hfgcspy_data).

Creating and enabling a systemd service file (example provided in the setup.sh script).

Usage
Accessing the Web UI
After successful installation and reboot, open a web browser on a device on the same network as your Raspberry Pi and navigate to:

http://<Your_Raspberry_Pi_IP_Address>/hfgcspy (if no SSL configured)

https://<Your_Domain_Name>/hfgcspy (if HTTPS configured via Apache2)

Replace <Your_Raspberry_Pi_IP_Address> with your Pi's actual IP address (e.g., 192.168.1.100) or <Your_Domain_Name> if you used a domain and configured SSL.

Web UI Overview
Animated Title: The "HFGCSpy" title features a dynamic, multi-colored animation.

Service Status: Real-time indicators show the running status of HFGCS and S2 GhostNet capture services.

Tabs:

Local SDR: Displays messages captured by your local RTL-SDR(s).

Online SDR: Displays messages captured from configured public online WebSDRs/KiwiSDRs.

Sub-tabs: Under "Local SDR" and "Online SDR" tabs, dynamic sub-tabs will appear for each detected local SDR or configured online SDR, allowing you to filter messages by source.

Message Cards: Each captured message is displayed in a detailed card format, including:

Timestamp (24-hour format)

Frequency (kHz)

Mode (USB, JS8, AM, etc.)

Message Type (HFGCS Voice, EAM, S2 GhostNet, etc.)

Callsign

Decoded Text

Notes

Audio Playback: An embedded audio player allows you to listen to recorded audio.

Waveform Visualization: A "Draw Waveform" button generates a visual representation of the audio within the player's background using p5.js.

Delete Button: Allows deletion of individual messages from the database (currently simulated).

Options Modal: Accessed via the settings icon (cogwheel) in the top-right header.

Appearance: Toggle Light/Dark Mode.

SDR Service Control: Enable/Disable HFGCS and JS8 scanning services.

Message Display: Control number of messages displayed per page.

Local SDR Device Selection: Select which detected RTL-SDRs HFGCSpy should use.

Online SDR Configuration: Add/remove URLs and names for online WebSDR/KiwiSDRs.

Configuring HFGCSpy (Important!)
Due to the design choice of no internal API for HFGCSpy's backend configuration, certain changes made in the Web UI's "Options" modal require manual intervention to persist and take effect on the backend.

Locate the configuration file:
sudo nano /opt/hfgcspy/config.ini

Edit config.ini:

[scan_services]: To enable/disable HFGCS or JS8 scanning, set hfgcs = yes or js8 = yes.

[sdr_selection]: To choose which local SDRs to use, edit selected_devices = <SDR_SERIAL_1>, <SDR_SERIAL_2>. You can find detected SDR serials by running sudo /opt/hfgcspy/venv/bin/python3 -c "from core.sdr_manager import SDRManager; print(SDRManager.list_sdr_devices_serials())" in your terminal. Use all to select all detected SDRs (selected_devices = all).

[online_sdrs]: To add/remove online SDRs, manually add entries like sdr_europe = http://sdr.example.com:8073,web_sdr. The format is name = url,type.

[sdr]: You can manually set sample_rate, gain, ppm_correction here initially if you prefer. These are the default settings for newly opened SDRs.

Restart the HFGCSpy Service:
After any changes to config.ini, you must restart the HFGCSpy service for them to take effect:

sudo systemctl restart hfgcspy.service

The web UI will then pick up the new status and display it.

Service Control
HFGCSpy runs as a systemd service named hfgcspy.service. You can control it from the terminal:

Check status: sudo systemctl status hfgcspy.service

Start: sudo systemctl start hfgcspy.service

Stop: sudo systemctl stop hfgcspy.service

Restart: sudo systemctl restart hfgcspy.service

View logs: sudo journalctl -u hfgcspy.service -f

Project Structure
HFGCSpy/
├── setup.sh                  # Bash installer script
├── hfgcs.py                  # Main Python application (runs as daemon)
├── requirements.txt            # Python dependencies
├── config.ini                  # Active application configuration (created from template)
├── core/
│   ├── __init__.py             # Python package marker
│   ├── sdr_manager.py          # Handles RTL-SDR device interaction
│   └── data_store.py           # Manages SQLite database and data storage
├── web_ui/
│   ├── index.html              # Main web dashboard (all CSS and JS embedded)
│   └── recordings/             # Directory for recorded audio files (created by setup.sh)
└── data/                       # Directory for SQLite DB (hfgcspy.db)
└── logs/                       # Directory for application logs

Contributing
Contributions are welcome! If you find bugs, have feature requests, or would like to contribute code, please open an issue or pull request on the GitHub repository.

License
This project is licensed under the GNU General Public License v3.0. See the LICENSE file for details (to be added to your repository).

Version
HFGCSpy Application Version: 0.0.3
Installer (setup.sh) Version: 1.1.1
