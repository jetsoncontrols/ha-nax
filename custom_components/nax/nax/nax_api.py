"""Websocket API for DM Nax devices."""

import asyncio
from collections.abc import Callable
import json
import logging
import ssl
import threading
from typing import Any

import httpx
import websockets
from websockets import WebSocketClientProtocol
from websockets.extensions import permessage_deflate

from .misc.custom_merger import nax_custom_merger

_LOGGER = logging.getLogger(__name__)


class NaxApi:
    """Class for interacting with the NAX system."""

    def __init__(
        self, ip: str, username: str, password: str, http_fallback: bool = False
    ) -> None:
        """Initialize the NaxApi class."""
        self._ip = ip
        self._username = username
        self._password = password
        self._http_fallback = http_fallback

        self._ws_client: WebSocketClientProtocol | None = None
        self._ws_client_connected: bool = False
        self._ws_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._loginResponse: httpx.Response | None = None
        self._json_state: dict[str, Any] = {}
        self._data_subscriptions: dict[str, list[Callable[[str, Any], None]]] = {}
        self._subscribe_data_lock = threading.RLock()
        self._connection_subscriptions: list[list[Callable[[bool], None]]] = []
        self._subscribe_connection_lock = threading.RLock()

    def get_websocket_connected(self) -> bool:
        """Return True if logged in, False if not."""
        return self._ws_client_connected

    def get_base_url(self) -> str | None:
        """Return the base URL of the NAX system."""
        if self._ip is None:
            return None
        return f"https://{self._ip}"

    def __get_login_url(self) -> str | None:
        if self.get_base_url() is None:
            return None
        return f"{self.get_base_url()}/userlogin.html"

    def __get_websocket_url(self) -> str | None:
        if self._ip is None:
            return None
        return f"wss://{self._ip}/websockify"

    async def http_login(self) -> tuple[bool, str]:
        """Log in to the NAX system."""
        try:
            async with httpx.AsyncClient(verify=False) as client:
                userLoginGetResponse = await client.get(
                    url=self.__get_login_url(), timeout=5
                )
                self._loginResponse = await client.post(
                    url=self.__get_login_url(),
                    cookies={"TRACKID": userLoginGetResponse.cookies["TRACKID"]},
                    headers={
                        "Origin": self.get_base_url(),
                        "Referer": self.__get_login_url(),
                    },
                    data={"login": self._username, "passwd": self._password},
                    timeout=5,
                )
        except (httpx.ConnectTimeout, httpx.NetworkError) as e:
            return False, f"Could not connect: {e}"

        if self._loginResponse.is_error:
            return False, f"Login attempt failed: {self._loginResponse.text}"

        if "CREST-XSRF-TOKEN" not in self._loginResponse.headers:
            return False, "Login attempt failed: Token missing in login response"

        self._loginResponse.headers["X-CREST-XSRF-TOKEN"] = self._loginResponse.headers[
            "CREST-XSRF-TOKEN"
        ]
        self._loginResponse.cookies.set(
            "TRACKID", userLoginGetResponse.cookies["TRACKID"]
        )
        return True, "Connected successfully"

    def logout(self) -> None:
        """Log out of the NAX system."""
        self.__get_request(path="/logout")
        self._loginResponse = None
        self._ws_client_connected = False
        self._json_state = {}
        if self._ws_task is not None:
            self._ws_task.cancel()
            self._ws_task = None
        if self._ws_client is not None:
            loop = asyncio.new_event_loop()

            def close_ws_client():
                asyncio.set_event_loop(loop)
                future = asyncio.run_coroutine_threadsafe(self._ws_client.close(), loop)
                future.result()
                self._ws_client = None
                loop.close()

            threading.Thread(target=close_ws_client).start()

    def _reconnect(self) -> None:
        _LOGGER.debug("Reconnecting to NAX")

        async def reconnect_coroutine():
            while True:
                http_connect, http_msg = await self.http_login()
                ws_connect = False
                ws_msg = ""
                if http_connect:
                    ws_connect, ws_msg = await self.async_upgrade_websocket()
                    if ws_connect:
                        _LOGGER.debug("Reconnected to NAX")
                        return
                if not http_connect or not ws_connect:
                    _LOGGER.error(
                        f"Could not reconnect to NAX: HTTP: {http_msg}, WS: {ws_msg}"  # noqa: G004
                    )
                    self._ws_client_connected = False
                    for callback in self._connection_subscriptions:
                        callback(self._ws_client_connected)
                await asyncio.sleep(3)  # wait before trying to reconnect

        self._reconnect_task = asyncio.create_task(reconnect_coroutine())

    def __get_request(self, path: str):
        get_request = httpx.get(
            url=self.get_base_url() + path,
            headers=self._loginResponse.headers,
            cookies=self._loginResponse.cookies,
            verify=False,
            timeout=5,
        )
        if get_request.is_success:
            try:
                return get_request.json()
            except json.JSONDecodeError:
                return get_request.text
        elif not get_request.is_redirect:
            _LOGGER.error(
                f"Get request for {get_request.url} failed: {get_request.status_code}: text: {get_request.text}"  # noqa: G004
            )

    def __post_request(self, path: str, json_data: Any | None) -> Any:
        post_request = httpx.post(
            url=self.get_base_url() + path,
            headers=self._loginResponse.headers,
            cookies=self._loginResponse.cookies,
            json=json_data,
            verify=False,
            timeout=5,
        )
        if post_request.is_success:
            try:
                return post_request.json()
            except json.JSONDecodeError:
                return post_request.text
        else:
            _LOGGER.error(
                f"Post request for {post_request.url} failed: {post_request.status_code} text: {post_request.text}"  # noqa: G004
            )

    async def async_upgrade_websocket(self) -> tuple[bool, str]:
        """Upgrade previously http_login to websocket."""
        self._ws_client = None
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        headers = {
            "Origin": self.get_base_url(),
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
            "Cookie": "; ".join(
                [
                    f"{name}={value}"
                    for name, value in self._loginResponse.cookies.items()
                ]
            ),
        }

        try:
            client: WebSocketClientProtocol = await websockets.connect(
                self.__get_websocket_url(),
                ssl=ssl_context,
                ping_interval=1.0,
                extra_headers=headers,
                extensions=[
                    permessage_deflate.ClientPerMessageDeflateFactory(
                        server_max_window_bits=11,
                        client_max_window_bits=11,
                        compress_settings={"memLevel": 4},
                    ),
                ],
            )
            self._ws_client = client
            self._ws_client_connected = True
            _LOGGER.info("Connected to websocket")
            for callback in self._connection_subscriptions:
                callback(self._ws_client_connected)
        except ssl.SSLCertVerificationError:
            _LOGGER.exception("An SSL certificate verification error occurred")
            return False, "Connection Failed, SSL certificate verification error"
        except websockets.exceptions.InvalidStatusCode:
            _LOGGER.exception("An invalid status code was received")
            return False, "Connection Failed, Invalid status code"
        if self._ws_client is not None:
            self._ws_task = asyncio.run_coroutine_threadsafe(
                self.__ws_handler(self._ws_client), asyncio.get_event_loop()
            )
            return True, "Connected successfully"

    async def __ws_handler(self, client: WebSocketClientProtocol) -> None:
        try:
            receive_buffer = ""
            json_raw_messages = []

            await client.send("/Device/")  # Request all device data

            while self._ws_task is not None and not self._ws_task.done():
                try:
                    receive_buffer += await client.recv()
                    while "\n" in receive_buffer:
                        json_raw_message, receive_buffer = receive_buffer.split("\n", 1)
                        if not json_raw_message.isspace():
                            json_raw_messages.append(json_raw_message)
                except (
                    websockets.exceptions.ConnectionClosedOK,
                    websockets.exceptions.ConnectionClosedError,
                ):
                    _LOGGER.debug("Websocket Connection closed")
                    self._reconnect()
                    return
                try:
                    while json_raw_messages:
                        json_raw_message = json_raw_messages.pop(0)
                        new_message_json = json.loads(json_raw_message)
                        self.__process_received_json_message(new_message_json)
                except json.JSONDecodeError:
                    _LOGGER.error(f"Error decoding JSON: {json_raw_message}")  # noqa: G004
        except (asyncio.CancelledError, RuntimeError):
            _LOGGER.debug("Websocket task cancelled")

    def __process_received_json_message(self, json_message: dict[str, Any]) -> None:
        print(json.dumps(json_message, indent=4))
        if "Actions" in json_message:
            for action in json_message["Actions"]:
                for result in action["Results"]:
                    if result["StatusInfo"] != "OK":
                        _LOGGER.error(
                            f"Error in action: Path: {result['Path']}, Property: {result['Property']}, StatusId: {result['StatusId']}, StatusInfo: {result['StatusInfo']}"  # noqa: G004
                        )
            return
        nax_custom_merger.merge(self._json_state, json_message)
        new_message_paths = self.__get_json_paths(json_message)
        matching_paths = [
            path for path in new_message_paths if path in self._data_subscriptions
        ]
        for path in matching_paths:
            matching_path_value = self.__get_value_by_json_path(json_message, path)
            for callback in self._data_subscriptions[path]:
                callback(path, matching_path_value)

    def subscribe_connection_updates(
        self,
        callback: Callable[[bool], None],
        trigger_current_value: bool = False,
    ) -> None:
        """Subscribe to connection updates.

        Args:
            callback: A callable that takes a boolean parameter.
            trigger_current_value: Whether to trigger the callback with the current connection value.

        Returns:
            None

        """
        self._subscribe_connection_lock.acquire()
        self._connection_subscriptions.append(callback)
        if trigger_current_value:
            callback(self.get_websocket_connected())
        self._subscribe_connection_lock.release()

    def subscribe_data_updates(
        self,
        path: str,
        callback: Callable[[str, Any], None],
        trigger_current_value: bool = False,
    ) -> None:
        """Subscribe to data updates.

        Args:
            path: The path to subscribe to.
            callback: A callable that takes a string and any parameter.
            trigger_current_value: Whether to trigger the callback with the current value.

        Returns:
            None

        """
        self._subscribe_data_lock.acquire()
        if path not in self._data_subscriptions:
            self._data_subscriptions[path] = []
        self._data_subscriptions[path].append(callback)
        if trigger_current_value and path in self.__get_json_paths(self._json_state):
            matching_path_value = self.__get_value_by_json_path(self._json_state, path)
            if matching_path_value is not None:
                callback(path, matching_path_value)
        self._subscribe_data_lock.release()

    def unsubscribe_data_updates(self, path: str, callback: Callable[[str, Any], None]):
        """Unsubscribe from data updates.

        Args:
            path: The path to unsubscribe from.
            callback: A callable that takes a string and any parameter.

        Returns:
            None

        """
        self._subscribe_data_lock.acquire()
        if path in self._data_subscriptions:
            self._data_subscriptions[path].remove(callback)
        self._subscribe_data_lock.release()

    def __get_json_paths(self, json_obj, current_path="", paths=None) -> list[str]:
        if paths is None:
            paths = []
        for key, value in json_obj.items():
            new_path = f"{current_path}.{key}" if current_path else key
            paths.append(new_path)
            if isinstance(value, dict):
                self.__get_json_paths(value, new_path, paths)
        return paths

    def __get_value_by_json_path(
        self, json_obj, path, path_separator: chr = "."
    ) -> Any | None:
        parts = path.split(path_separator)
        for part in parts:
            if isinstance(json_obj, dict):
                json_obj = json_obj.get(part, None)
        return json_obj

    def get_data(
        self, data_path: str
    ) -> dict[str, Any] | str | bool | int | float | None:
        json_state_data = self.__get_value_by_json_path(self._json_state, data_path)
        if json_state_data is not None:
            return json_state_data
        if self._http_fallback:
            get_data = self.__get_request(path=f"/{data_path.replace('.', '/')}")
            return self.__get_value_by_json_path(get_data, data_path)

    async def put_data(self, data_path: str, json_data: Any) -> None:
        if self.get_websocket_connected():
            await self._ws_client.send(json.dumps(json_data))
        elif self._http_fallback:
            await self.__post_request(
                path=f"/{data_path.replace('.', '/')}", json_data=json_data
            )

    def get_device_name(self) -> str | None:
        """Get the name of the device.

        Returns:
            The name of the device as a string, or None if the name is not available.

        """
        return self.get_data("Device.DeviceInfo.Name")

    def get_device_mac_address(self) -> str | None:
        """Get the MAC address of the device.

        Returns:
            The MAC address of the device as a string, or None if the MAC address is not available.

        """
        return self.get_data("Device.DeviceInfo.MacAddress")

    def get_device_manufacturer(self) -> str | None:
        """Get the manufacturer of the device.

        Returns:
            The manufacturer of the device as a string, or None if the name is not available.

        """
        return self.get_data("Device.DeviceInfo.Manufacturer")

    def get_device_model(self) -> str | None:
        """Get the model of the device.

        Returns:
            The model of the device as a string, or None if the model is not available.

        """
        return self.get_data("Device.DeviceInfo.Model")

    def get_device_firmware_version(self) -> str | None:
        """Get the firmware version of the device.

        Returns:
            The firmware version of the device as a string, or None if the version is not available.

        """
        return self.get_data("Device.DeviceInfo.DeviceVersion")

    def get_device_serial_number(self) -> str | None:
        """Get the serial number of the device.

        Returns:
            The serial number of the device as a string, or None if the serial number is not available.

        """
        return self.get_data("Device.DeviceInfo.SerialNumber")

    def __get_zone_outputs(self) -> dict[str:Any] | None:
        return self.get_data("Device.ZoneOutputs.Zones")

    def get_all_zone_outputs(self) -> list[str]:
        """Get a list of all zone outputs.

        Returns:
            A list of strings representing all zone outputs.

        """
        result = []
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            for zone_output in zone_outputs_json:
                result.append(zone_output)  # noqa: PERF402
        return result

    def get_zone_name(self, zone_output: str) -> str | None:
        """Get the name of a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The name of the specified zone output as a string, or None if the name is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["Name"]

    def get_zone_audio_source(self, zone_output: str) -> str | None:
        """Get the audio source for a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The audio source for the specified zone output as a string, or None if the audio source is not available.

        """
        zone_routes = self.get_data("Device.AvMatrixRouting.Routes")
        if zone_routes and zone_output in zone_routes:
            if "AudioSource" in zone_routes[zone_output]:
                if zone_routes[zone_output]["AudioSource"] != "":
                    return zone_routes[zone_output]["AudioSource"]
        return None

    def get_aes67_streams(self) -> list[dict[str, str]] | None:
        """Get the list of available AES67 streams.

        Returns:
            A list of available AES67 streams as strings, or None if no streams are available.

        """
        streams = self.get_data("Device.NaxAudio.NaxSdp.NaxSdpStreams")
        return [
            {
                "address": stream["NetworkAddressStatus"],
                "name": stream["SessionNameStatus"],
            }
            for stream in streams.values()
            if stream
        ]

    def get_stream_zone_receiver_mapping(self, zone_output: str) -> str | None:
        """Get the receiver mapping for a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The receiver mapping for the specified zone output as a string, or None if the mapping is not available.

        """
        rx_mappings = self.get_data(
            "Device.NaxAudio.StreamReferenceMapping.NaxRxStreams"
        )
        for streamer in rx_mappings:
            if rx_mappings[streamer]["Path"] == f"ZoneOutputs/Zones/{zone_output}":
                return streamer

    def get_aes67_address_is_local(self, address: str) -> bool:
        """Check if an AES67 address is local.

        Args:
            address: The AES67 address to check.

        Returns:
            A boolean indicating if the address is local.

        """
        tx_streams = self.get_data("Device.NaxAudio.NaxTx.NaxTxStreams")
        for stream in tx_streams.values():
            if stream["NetworkAddressStatus"] == address:
                return True
        return False

    def get_aes67_address_for_input(self, input: str) -> str | None:
        """Get the AES67 address for a specific input.

        Args:
            input: The input identifier.

        Returns:
            The AES67 address for the specified input as a string, or None if the address is not available.

        """
        naxAudio = self.get_data("Device.NaxAudio")
        naxTxStreams = naxAudio["StreamReferenceMapping"]["NaxTxStreams"]
        for stream in naxTxStreams:
            if naxTxStreams[stream]["Path"] == f"InputSources/Inputs/{input}":
                return naxAudio["NaxTx"]["NaxTxStreams"][stream]["NetworkAddressStatus"]
        return None

    def get_nax_rx_stream_address(self, streamer: str) -> str | None:
        """Get the network address for a specific NaxRx streamer.

        Args:
            streamer: The NaxRx streamer identifier.

        Returns:
            The network address for the specified NaxRx streamer as a string, or None if the address is not available.

        """
        stream = self.get_data(f"Device.NaxAudio.NaxRx.NaxRxStreams.{streamer}")
        return stream["NetworkAddressStatus"]

    async def set_nax_rx_stream(self, streamer: str, address: str) -> None:
        """Set the network address for a specific NaxRx streamer.

        Args:
            streamer: The NaxRx streamer identifier.
            address: The network address to set.

        Returns:
            None

        """
        json_data = {
            "Device": {
                "NaxAudio": {
                    "NaxRx": {
                        "NaxRxStreams": {
                            streamer: {
                                "NetworkAddressRequested": address,
                            }
                        }
                    }
                }
            }
        }
        await self.put_data(
            data_path=f"Device.NaxAudio.NaxRx.NaxRxStreams.{streamer}.NetworkAddressRequested",
            json_data=json_data,
        )

    def get_zone_volume(self, zone_output: str) -> float | None:
        """Get the volume of a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The volume of the specified zone output as a float, or None if the volume is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Volume"]

    def get_zone_muted(self, zone_output: str) -> bool | None:
        """Get the mute status of a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The mute status of the specified zone output as a boolean, or None if the mute status is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["IsMuted"]

    def get_zone_signal_detected(self, zone_output: str) -> bool | None:
        """Get the signal detection status for a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The signal detection status for the specified zone output as a boolean, or None if the status is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["IsSignalDetected"]

    def get_zone_casting_active(self, zone_output: str) -> bool | None:
        """Get the casting active status for a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The casting active status for the specified zone output as a boolean, or None if the status is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneBasedProviders"][
                "IsCastingActive"
            ]

    def get_zone_signal_clipping(self, zone_output: str) -> bool | None:
        """Get the signal clipping status for a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The signal clipping status for the specified zone output as a boolean, or None if the status is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["IsSignalClipping"]

    def get_zone_speaker_clipping(self, zone_output: str) -> bool | None:
        """Get the clipping status of a specific zone output's speaker.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The clipping status of the specified zone output's speaker as a boolean, or None if the status is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsClippingDetected"
            ]

    def get_zone_speaker_critical_fault(self, zone_output: str) -> bool | None:
        """Get the critical fault status of a specific zone output's speaker.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The critical fault status of the specified zone output's speaker as a boolean, or None if the status is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsCriticalFaultDetected"
            ]

    def get_zone_speaker_dc_fault(self, zone_output: str) -> bool | None:
        """Get the DC fault status of a specific zone output's speaker.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The DC fault status of the specified zone output's speaker as a boolean, or None if the status is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsDcFaultDetected"
            ]

    def get_zone_speaker_over_current(self, zone_output: str) -> bool | None:
        """Get the over current status of a specific zone output's speaker.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The over current status of the specified zone output's speaker as a boolean, or None if the status is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsOverCurrentConditionDetected"
            ]

    def get_zone_speaker_over_temperature(self, zone_output: str) -> bool | None:
        """Get the over temperature status of a specific zone output's speaker.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The over temperature status of the specified zone output's speaker as a boolean, or None if the status is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsOverTemperatureConditionDetected"
            ]

    def get_zone_speaker_voltage_fault(self, zone_output: str) -> bool | None:
        """Get the voltage fault status of a specific zone output's speaker.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The voltage fault status of the specified zone output's speaker as a boolean, or None if the status is not available.

        """
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsVoltageFaultDetected"
            ]

    def get_input_sources(self) -> list[str] | None:
        """Get the list of available input sources.

        Returns:
            A list of available input sources as strings, or None if no input sources are available.

        """
        inputs = self.get_data("Device.InputSources.Inputs")
        if inputs:
            return list(inputs.keys())

    def get_input_source_name(self, input_source: str) -> str | None:
        """Get the name of a specific input source.

        Args:
            input_source: The input source identifier.

        Returns:
            The name of the specified input source as a string, or None if the name is not available.

        """
        if input_source:
            return self.get_data(f"Device.InputSources.Inputs.{input_source}.Name")

    def get_input_source_signal_present(self, input_source: str) -> bool | None:
        """Get the signal present status of a specific input source.

        Args:
            input_source: The input source identifier.

        Returns:
            The signal present status of the specified input source as a boolean, or None if the status is not available.

        """
        if input_source:
            return self.get_data(
                f"Device.InputSources.Inputs.{input_source}.IsSignalPresent"
            )

    def get_input_source_clipping(self, input_source: str) -> bool | None:
        """Get the clipping status of a specific input source.

        Args:
            input_source: The input source identifier.

        Returns:
            The clipping status of the specified input source as a boolean, or None if the status is not available.

        """
        if input_source:
            return self.get_data(
                f"Device.InputSources.Inputs.{input_source}.IsClippingDetected"
            )

    def get_zone_tone_profile(self, zone_output: str) -> str | None:
        """Get the tone profile of a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The tone profile of the specified zone output as a string, or None if the tone profile is not available.

        """
        return self.get_data(
            f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.ToneProfile"
        )

    def get_zone_test_tone(self, zone_output: str) -> bool | None:
        """Get the test tone status of a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The test tone status of the specified zone output as a boolean, or None if the status is not available.

        """
        return self.get_data(
            f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.IsTestToneActive"
        )

    def get_zone_night_modes(self) -> list[str] | None:
        """Get the available night modes for a zone output.

        Returns:
            A list of available night modes as strings, or None if the night modes are not available.

        """
        return ["Off", "Low", "Medium", "High"]

    def get_zone_night_mode(self, zone_output: str) -> str | None:
        """Get the night mode of a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The night mode of the specified zone output as a string, or None if the night mode is not available.

        """
        return self.get_data(
            f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.NightMode"
        )

    async def set_zone_night_mode(self, zone_output: str, mode: str) -> None:
        """Set the night mode of a specific zone output.

        Args:
            zone_output: The zone output identifier.
            mode: The night mode to set.

        Raises:
            ValueError: If an invalid night mode is provided.

        """
        if mode not in self.get_zone_night_modes():
            raise ValueError(f"Invalid Night Mode '{mode}'")
        json_data = {
            "Device": {
                "ZoneOutputs": {
                    "Zones": {
                        zone_output: {
                            "ZoneAudio": {
                                "NightMode": mode,
                            }
                        }
                    }
                }
            }
        }
        await self.put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.NightMode",
            json_data=json_data,
        )

    def get_zone_loudness(self, zone_output: str) -> bool | None:
        """Get the loudness status of a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            The loudness status of the specified zone output as a boolean, or None if the status is not available.

        """
        return self.get_data(
            f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.IsLoudnessEnabled"
        )

    def get_zone_amplification_supported(self, zone_output: str) -> bool | None:
        """Check if amplification is supported for a specific zone output.

        Args:
            zone_output: The zone output identifier.

        Returns:
            A boolean indicating if amplification is supported for the specified zone output, or None if the information is not available.

        """
        return self.get_data(
            f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.IsAmplificationSupported"
        )

    async def set_zone_loudness(self, zone_output: str, active: bool) -> None:
        """Set the loudness status of a specific zone output.

        Args:
            zone_output: The zone output identifier.
            active: The loudness status to set.

        """
        json_data = {
            "Device": {
                "ZoneOutputs": {
                    "Zones": {
                        zone_output: {
                            "ZoneAudio": {
                                "IsLoudnessEnabled": active,
                            }
                        }
                    }
                }
            }
        }
        await self.put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.IsLoudnessEnabled",
            json_data=json_data,
        )

    def get_chimes(self) -> list[dict[str, str]] | None:
        """Get the list of available chimes.

        Returns:
            A list of dictionaries containing the ID and name of each chime, or None if the information is not available.

        """
        result = []
        chimes = self.get_data("Device.DoorChimes.DefaultChimes")
        for chime in chimes:
            result.append({"id": chime, "name": chimes[chime]["Name"]})  # noqa: PERF401
        return result

    async def play_chime(self, chime_id: str) -> None:
        """Play a chime with the specified chime ID.

        Args:
            chime_id: The ID of the chime to play.

        Returns:
            None

        """
        json_data = {
            "Device": {
                "DoorChimes": {
                    "DefaultChimes": {
                        chime_id: {
                            "Play": True,
                        }
                    }
                }
            }
        }
        await self.put_data(
            data_path=f"Device.DoorChimes.DefaultChimes.{chime_id}.Play",
            json_data=json_data,
        )

    async def set_zone_test_tone(self, zone_output: str, active: bool) -> None:
        """Set the test tone status of a specific zone output.

        Args:
            zone_output: The zone output identifier.
            active: The test tone status to set.

        Returns:
            None

        """
        json_data = {
            "Device": {
                "ZoneOutputs": {
                    "Zones": {
                        zone_output: {
                            "ZoneAudio": {
                                "IsTestToneActive": active,
                            }
                        }
                    }
                }
            }
        }
        await self.put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.IsTestToneActive",
            json_data=json_data,
        )

    async def set_zone_tone_profile(self, zone_output: str, tone_profile: str) -> None:
        """Set the tone profile of a specific zone output.

        Args:
            zone_output: The zone output identifier.
            tone_profile: The tone profile to set.

        Returns:
            None

        """
        json_data = {
            "Device": {
                "ZoneOutputs": {
                    "Zones": {
                        zone_output: {
                            "ZoneAudio": {
                                "ToneProfile": tone_profile,
                            }
                        }
                    }
                }
            }
        }
        await self.put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.ToneProfile",
            json_data=json_data,
        )

    async def set_zone_volume(self, zone_output: str, volume: float) -> None:
        """Set the volume of a specific zone output.

        Args:
            zone_output: The zone output identifier.
            volume: The volume level to set.

        Returns:
            None

        """
        json_data = {
            "Device": {
                "ZoneOutputs": {
                    "Zones": {
                        zone_output: {
                            "ZoneAudio": {
                                "Volume": volume,
                            }
                        }
                    }
                }
            }
        }
        await self.put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.Volume",
            json_data=json_data,
        )

    async def set_zone_mute(self, zone_output: str, mute: bool) -> None:
        """Set the mute status of a specific zone output.

        Args:
            zone_output: The zone output identifier.
            mute: The mute status to set.

        Returns:
            None

        """
        json_data = {
            "Device": {
                "ZoneOutputs": {
                    "Zones": {
                        zone_output: {
                            "ZoneAudio": {
                                "IsMuted": mute,
                            }
                        }
                    }
                }
            }
        }
        await self.put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.IsMuted",
            json_data=json_data,
        )

    async def set_zone_audio_source(self, zone_output: str, route: str) -> None:
        """Set the audio source of a specific zone output.

        Args:
            zone_output: The zone output identifier.
            route: The audio source to set.

        Returns:
            None

        """
        json_data = {
            "Device": {
                "AvMatrixRouting": {
                    "Routes": {
                        zone_output: {"AudioSource": route},
                    },
                }
            }
        }
        await self.put_data(
            data_path=f"Device.AvMatrixRouting.Routes.{zone_output}.AudioSource",
            json_data=json_data,
        )
