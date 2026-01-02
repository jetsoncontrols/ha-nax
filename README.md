# NAX Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

A custom Home Assistant integration for Crestron NAX audio devices.

## Features

- **Media Player**: Control NAX audio zones with volume, mute, and input selection
- **Select**: Choose inputs, AES67 streams, and tone generator modes
- **Binary Sensor**: Monitor device status, signal detection, and clipping
- **Switch**: Control tone generator channels and zone test tones
- **Number**: Configure audio settings, volumes, and tone generator frequency
- **Siren**: Trigger door chimes and announcements
- **Device Integration**: Full device support with proper device registry

## Installation

### HACS (Recommended)

1. Install [HACS](https://hacs.xyz/) if you haven't already
2. Add this repository as a custom repository in HACS
3. Install the "NAX" integration
4. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/nax` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to Settings → Devices & Services
2. Click "Add Integration"
3. Search for "NAX"
4. Enter your NAX device details:
   - **Host**: IP address of your NAX device
   - **Username**: NAX device username
   - **Password**: NAX device password

## Supported Devices

This integration supports Crestron NAX audio devices that use the CresNext WebSocket API.

## Entities

### Media Player
- Control volume, mute, and input selection
- View current playing status
- One entity per zone

### Select
- **Input Selection**: Choose from available audio inputs (one per zone)
- **AES67 Stream**: Select AES67 network audio streams (one per zone with AES67 receiver)
- **Tone Generator Mode**: Select tone generator mode - Tone, WhiteNoise, or PinkNoise (diagnostic, one per device)

### Binary Sensor
- **Connection Status**: Monitor device connectivity
- **Input Signal Detection**: Monitor signal presence on inputs (one per input)
- **Input Clipping Detection**: Monitor clipping on inputs (diagnostic, one per input)
- **Zone Signal Detection**: Monitor signal presence on zones (one per zone)

### Switch
- **Tone Generator Left Channel**: Enable/disable tone generator left channel (diagnostic, one per device)
- **Tone Generator Right Channel**: Enable/disable tone generator right channel (diagnostic, one per device)
- **Zone Test Tone**: Activate test tone on individual zones (diagnostic, one per zone)

### Number
- **Input Compensation**: Adjust input level compensation in dB (configuration, one per input)
- **Zone Default Volume**: Set default volume percentage (configuration, one per zone)
- **Zone Minimum Volume**: Set minimum volume limit (configuration, one per zone)
- **Zone Maximum Volume**: Set maximum volume limit (configuration, one per zone)
- **Tone Generator Frequency**: Set tone generator frequency 20-20000 Hz (diagnostic, one per device)
- **Zone Test Tone Volume**: Set test tone volume percentage (diagnostic, one per zone)

### Siren
- **Door Chime**: Trigger door chimes with configurable tones (one per device)

## Entity Categories

- **Standard**: Main control entities (media players, input selects, volume controls)
- **Configuration**: Settings and limits (input compensation, volume limits)
- **Diagnostic**: Testing and troubleshooting tools (tone generator, test tones, signal monitoring)

## Requirements

- Home Assistant 2025.8 or newer
- Crestron NAX device with network connectivity
- Valid NAX device credentials

## Support

For issues and feature requests, please use the [GitHub Issues](https://github.com/jetsoncontrols/ha-nax/issues) page.

## License

This project is licensed under the MIT License.