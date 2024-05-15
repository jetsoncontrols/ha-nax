import logging
from websockets import WebSocketClientProtocol
import websockets
from websockets.extensions import permessage_deflate
import asyncio
from typing import Any
from collections.abc import Callable, Awaitable
from urllib3.exceptions import MaxRetryError
import requests
from requests import ConnectTimeout
import json
import ssl
from .misc.custom_merger import nax_custom_merger

_LOGGER = logging.getLogger(__name__)


class NaxApi:
    _ip: str = None
    _username: str = None
    _password: str = None
    _loginResponse: requests.Response = None
    _ws_task: asyncio.Task = None
    _ws_client: WebSocketClientProtocol = None

    _ws_client_connected: bool = False
    _json_state: dict[str, Any] = {}
    _data_subscriptions: dict[str, list[Callable[[str, Any], None]]] = {}
    _connection_subscriptions: list[list[Callable[[bool], None]]] = []

    def __init__(self, ip: str, username: str, password: str) -> None:
        """Initializes the NaxApi class."""
        requests.packages.urllib3.disable_warnings()  # Disable SSL warnings for self signed certificates
        self._ip = ip
        self._username = username
        self._password = password

    def get_websocket_connected(self) -> bool:
        """Returns True if logged in, False if not."""
        return self._ws_client_connected

    def get_base_url(self) -> str | None:
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

    def http_login(self) -> tuple[bool, str]:
        """Logs in to the NAX system."""
        try:
            userLoginGetResponse = requests.get(
                url=self.__get_login_url(), verify=False, timeout=5
            )
        except (ConnectTimeout, MaxRetryError) as e:
            return False, f"Could not connect: {e.reason}"
        self._loginResponse = requests.post(
            url=self.__get_login_url(),
            cookies={"TRACKID": userLoginGetResponse.cookies["TRACKID"]},
            headers={
                "Origin": self.get_base_url(),
                "Referer": self.__get_login_url(),
            },
            data={"login": self._username, "passwd": self._password},
            verify=False,
            timeout=5,
        )
        if (
            self._loginResponse.status_code != 200
            or "CREST-XSRF-TOKEN" not in self._loginResponse.headers
        ):
            return False, "Login failed"
        self._loginResponse.headers["X-CREST-XSRF-TOKEN"] = self._loginResponse.headers[
            "CREST-XSRF-TOKEN"
        ]
        self._loginResponse.cookies.set(
            "TRACKID", userLoginGetResponse.cookies["TRACKID"]
        )
        return True, "Connected successfully"

    def logout(self) -> None:
        """Logs out of the NAX system."""
        self.__get_request(path="/logout")
        self._loginResponse = None
        self._ws_client_connected = False
        self._json_state = {}
        if self._ws_task is not None:
            self._ws_task.cancel()
            self._ws_task = None
        if self._ws_client is not None:
            self._ws_client.close()
            self._ws_client = None

    def __get_request(self, path: str):
        get_request = requests.get(
            url=self.get_base_url() + path,
            headers=self.loginResponse.headers,
            cookies=self.loginResponse.cookies,
            verify=False,
            timeout=5,
        )
        if get_request.ok:
            try:
                return json.loads(get_request.text)
            except json.JSONDecodeError:
                return get_request.text
        else:
            print(
                f"Get request for {get_request.url} failed: {get_request.status_code}"
            )

    def __post_request(self, path: str, json_data: Any | None) -> Any:
        post_request = requests.post(
            url=self.get_base_url() + path,
            headers=self._loginResponse.headers,
            cookies=self._loginResponse.cookies,
            json=json_data,
            verify=False,
            timeout=5,
        )
        if post_request.ok:
            try:
                return json.loads(post_request.text)
            except json.JSONDecodeError:
                return post_request.text
        else:
            print(
                f"Post request for {post_request.url} failed: {post_request.status_code}"
            )

    async def async_upgrade_websocket(self) -> None:
        """Upgrade previously http_login to websocket."""
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        headers = {
            "Origin": self.get_base_url(),
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
            "Cookie": "; ".join(
                [
                    "%s=%s" % (i, j)
                    for i, j in self._loginResponse.cookies.get_dict().items()
                ]
            ),
        }

        try:
            client: WebSocketClientProtocol = await websockets.connect(
                self.__get_websocket_url(),
                ssl=ssl_context,
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
        except ssl.SSLCertVerificationError as sslcve:
            _LOGGER.exception(sslcve)
        except websockets.exceptions.InvalidStatusCode as isc:
            _LOGGER.exception(isc)
        if self._ws_client is not None:
            self._ws_task = asyncio.create_task(self.__ws_handler(self._ws_client))

    async def __ws_handler(self, client: WebSocketClientProtocol) -> None:
        receive_buffer = ""
        json_raw_messages = []
        await client.send("/Device/")  # Request all device data

        while True:
            try:
                receive_buffer += await client.recv()
                while "\n" in receive_buffer:
                    json_raw_message, receive_buffer = receive_buffer.split("\n", 1)
                    if not json_raw_message.isspace():
                        json_raw_messages.append(json_raw_message)
            except websockets.exceptions.ConnectionClosedOK:
                _LOGGER.warning("Connection closed (OK)")
                self._ws_client_connected = False
                for callback in self._connection_subscriptions:
                    callback(self._ws_client_connected)
                return
            except websockets.exceptions.ConnectionClosedError:
                _LOGGER.warning("Connection closed (Error)")
                self._ws_client_connected = False
                for callback in self._connection_subscriptions:
                    callback(self._ws_client_connected)
                return
            try:
                while json_raw_messages:
                    new_message_json = json.loads(json_raw_messages.pop(0))
                    self.__process_received_json_message(new_message_json)
            except json.JSONDecodeError as e:
                _LOGGER.error(e)

    def __process_received_json_message(self, json_message: dict[str, Any]) -> None:
        if "Actions" in json_message:
            for action in json_message["Actions"]:
                for result in action["Results"]:
                    if result["StatusInfo"] != "OK":
                        _LOGGER.error(
                            f"Error in action: Path: {result['Path']}, Property: {result['Property']}, StatusId: {result['StatusId']}, StatusInfo: {result['StatusInfo']}"
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
        trigger_current_value: bool = True,
    ) -> None:
        self._connection_subscriptions.append(callback)
        if trigger_current_value:
            callback(self.get_websocket_connected())

    def unsubscribe_connection_updates(self, callback: Callable[[bool], None]) -> None:
        self._connection_subscriptions.remove(callback)

    def subscribe_data_updates(
        self,
        path: str,
        callback: Callable[[str, Any], None],
        trigger_current_value: bool = True,
    ) -> None:
        if path not in self._data_subscriptions:
            self._data_subscriptions[path] = []
        self._data_subscriptions[path].append(callback)
        if trigger_current_value and self._json_state:
            matching_path_value = self.__get_value_by_json_path(self._json_state, path)
            if matching_path_value is not None:
                callback(path, matching_path_value)

    def unsubscribe_data_updates(self, path: str, callback: Callable[[str, Any], None]):
        if path in self._data_subscriptions:
            self._data_subscriptions[path].remove(callback)

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
            if isinstance(json_obj, dict) and part in json_obj:
                json_obj = json_obj[part]
            else:
                return json_obj  # Was none previously
        return json_obj

    def __get_data(
        self, data_path: str
    ) -> dict[str, Any] | str | bool | int | float | None:
        get_data = None

        if self.get_websocket_connected():
            get_data = self.__get_value_by_json_path(self._json_state, data_path)
        else:
            # check login?
            get_data = self.__get_request(path=f"/{data_path.replace('.', '/')}")
        return self.__get_value_by_json_path(get_data, data_path)

    async def __put_data(self, data_path: str, json_data: Any) -> None:
        if self.get_websocket_connected():
            await self._ws_client.send(json.dumps(json_data))
        else:
            # check login?
            await self.__post_request(
                path=f"/{data_path.replace('.', '/')}", json_data=json_data
            )

    def get_device_name(self) -> str | None:
        return self.__get_data("Device.DeviceInfo.Name")

    def get_device_mac_address(self) -> str | None:
        return self.__get_data("Device.DeviceInfo.MacAddress")

    def get_device_manufacturer(self) -> str | None:
        return self.__get_data("Device.DeviceInfo.Manufacturer")

    def get_device_model(self) -> str | None:
        return self.__get_data("Device.DeviceInfo.Model")

    def get_device_firmware_version(self) -> str | None:
        return self.__get_data("Device.DeviceInfo.DeviceVersion")

    def get_device_serial_number(self) -> str | None:
        return self.__get_data("Device.DeviceInfo.SerialNumber")

    def __get_zone_outputs(self) -> dict[str:Any] | None:
        return self.__get_data("Device.ZoneOutputs.Zones")

    def get_all_zone_outputs(self) -> list[str]:
        result = []
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            for zone_output in zone_outputs_json:
                result.append(zone_output)
        return result

    def get_zone_name(self, zone_output: str) -> str | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["Name"]

    def get_zone_audio_source(self, zone_output: str) -> str | None:
        zone_routes = self.__get_data("Device.AvMatrixRouting.Routes")
        if zone_routes and zone_output in zone_routes:
            if "AudioSource" in zone_routes[zone_output]:
                if zone_routes[zone_output]["AudioSource"] != "":
                    return zone_routes[zone_output]["AudioSource"]
        return None

    def get_zone_volume(self, zone_output: str) -> float | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Volume"]

    def get_zone_muted(self, zone_output: str) -> bool | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["IsMuted"]

    def get_zone_signal_detected(self, zone_output: str) -> bool | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["IsSignalDetected"]

    def get_zone_signal_clipping(self, zone_output: str) -> bool | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["IsSignalClipping"]

    def get_zone_speaker_clipping(self, zone_output: str) -> bool | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsClippingDetected"
            ]

    def get_zone_speaker_critical_fault(self, zone_output: str) -> bool | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsCriticalFaultDetected"
            ]

    def get_zone_speaker_dc_fault(self, zone_output: str) -> bool | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsDcFaultDetected"
            ]

    def get_zone_speaker_over_current(self, zone_output: str) -> bool | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsOverCurrentConditionDetected"
            ]

    def get_zone_speaker_over_temperature(self, zone_output: str) -> bool | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsOverTemperatureConditionDetected"
            ]

    def get_zone_speaker_voltage_fault(self, zone_output: str) -> bool | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Speaker"]["Faults"][
                "IsVoltageFaultDetected"
            ]

    def get_input_sources(self) -> list[str] | None:
        inputs = self.__get_data("Device.InputSources.Inputs")
        return [input_source for input_source in inputs.keys()]

    def get_input_source_name(self, input_source: str) -> str | None:
        if input_source:
            return self.__get_data(f"Device.InputSources.Inputs.{input_source}.Name")

    def get_input_source_signal_present(self, input_source: str) -> bool | None:
        if input_source:
            return self.__get_data(
                f"Device.InputSources.Inputs.{input_source}.IsSignalPresent"
            )

    def get_input_source_clipping(self, input_source: str) -> bool | None:
        if input_source:
            return self.__get_data(
                f"Device.InputSources.Inputs.{input_source}.IsClippingDetected"
            )

    def get_zone_tone_profile(self, zone_output: str) -> str | None:
        return self.__get_data(
            f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.ToneProfile"
        )

    def get_zone_test_tone(self, zone_output: str) -> bool | None:
        return self.__get_data(
            f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.IsTestToneActive"
        )

    def get_zone_night_modes(self) -> list[str] | None:
        return ["Off", "Low", "Medium", "High"]

    def get_zone_night_mode(self, zone_output: str) -> str | None:
        return self.__get_data(
            f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.NightMode"
        )

    async def set_zone_night_mode(self, zone_output: str, mode: str) -> None:
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
        await self.__put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.NightMode",
            json_data=json_data,
        )

    def get_zone_loudness(self, zone_output: str) -> bool | None:
        return self.__get_data(
            f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.IsLoudnessEnabled"
        )

    async def set_zone_loudness(self, zone_output: str, active: bool) -> None:
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
        await self.__put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.IsLoudnessEnabled",
            json_data=json_data,
        )

    def get_chimes(self) -> list[dict[str, str]] | None:
        result = []
        chimes = self.__get_data(f"Device.DoorChimes.DefaultChimes")
        for chime in chimes.keys():
            result.append({"id": chime, "name": chimes[chime]["Name"]})
        return result

    async def play_chime(self, chime_id: str) -> None:
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
        await self.__put_data(
            data_path=f"Device.DoorChimes.DefaultChimes.{chime_id}.Play",
            json_data=json_data,
        )

    async def set_zone_test_tone(self, zone_output: str, active: bool) -> None:
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
        await self.__put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.IsTestToneActive",
            json_data=json_data,
        )

    async def set_zone_tone_profile(self, zone_output: str, tone_profile: str) -> None:
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
        await self.__put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.ToneProfile",
            json_data=json_data,
        )

    async def set_zone_volume(self, zone_output: str, volume: float) -> None:
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
        await self.__put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.Volume",
            json_data=json_data,
        )

    async def set_zone_mute(self, zone_output: str, mute: bool) -> None:
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
        await self.__put_data(
            data_path=f"Device.ZoneOutputs.Zones.{zone_output}.ZoneAudio.IsMuted",
            json_data=json_data,
        )

    async def set_zone_audio_source(self, zone_output: str, route: str) -> None:
        json_data = {
            "Device": {
                "AvMatrixRouting": {
                    "Routes": {
                        zone_output: {"AudioSource": route},
                    },
                }
            }
        }
        await self.__put_data(
            data_path=f"Device.AvMatrixRouting.Routes.{zone_output}.AudioSource",
            json_data=json_data,
        )
