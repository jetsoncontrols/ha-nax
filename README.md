# NAX Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)

A custom Home Assistant integration for Crestron NAX audio devices.

## Features

- **Media Player**: Control NAX audio zones
- **Select**: Choose inputs and AES67 streams
- **Binary Sensor**: Monitor device status
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

### Select
- **Input Selection**: Choose from available audio inputs
- **AES67 Stream**: Select AES67 network audio streams

### Binary Sensor
- **Connection Status**: Monitor device connectivity

## Requirements

- Home Assistant 2025.8 or newer
- Crestron NAX device with network connectivity
- Valid NAX device credentials

## Support

For issues and feature requests, please use the [GitHub Issues](https://github.com/jetsoncontrols/ha-nax/issues) page.

## License

This project is licensed under the MIT License.