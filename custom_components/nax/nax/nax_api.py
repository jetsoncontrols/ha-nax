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
import deepmerge

_LOGGER = logging.getLogger(__name__)


class NaxApi:

    ip: str = None
    username: str = None
    password: str = None
    loginResponse: requests.Response = None
    ws_task: asyncio.Task = None
    ws_client: WebSocketClientProtocol = None

    _ws_client_connected: bool = False
    _json_state: dict[str, Any] = {}
    _data_subscriptions: dict[str, list[Callable[[str, Any], None]]] = {}
    _connection_subscriptions: list[list[Callable[[bool], None]]] = []

    def __init__(self, ip: str, username: str, password: str) -> None:
        """Initializes the NaxApi class."""
        requests.packages.urllib3.disable_warnings()  # Disable SSL warnings for self signed certificates
        self.ip = ip
        self.username = username
        self.password = password

    def login(self) -> tuple[bool, str]:
        """Logs in to the NAX system."""
        try:
            userLoginGetResponse = requests.get(
                url=self.__get_login_url(), verify=False, timeout=5
            )
        except (ConnectTimeout, MaxRetryError) as e:
            return False, f"Could not connect: {e.reason}"
        self.loginResponse = requests.post(
            url=self.__get_login_url(),
            cookies={"TRACKID": userLoginGetResponse.cookies["TRACKID"]},
            headers={
                "Origin": self.get_base_url(),
                "Referer": self.__get_login_url(),
            },
            data={"login": self.username, "passwd": self.password},
            verify=False,
            timeout=5,
        )
        if (
            self.loginResponse.status_code != 200
            or "CREST-XSRF-TOKEN" not in self.loginResponse.headers
        ):
            return False, "Login failed"
        self.loginResponse.headers["X-CREST-XSRF-TOKEN"] = self.loginResponse.headers[
            "CREST-XSRF-TOKEN"
        ]
        self.loginResponse.cookies.set(
            "TRACKID", userLoginGetResponse.cookies["TRACKID"]
        )
        return True, "Connected successfully"

    async def start_websocket(self) -> None:
        self.ws_client = await self.get_ws_client()
        if self.ws_client is not None:
            self.ws_task = asyncio.create_task(self.ws_handler(self.ws_client))

    async def get_ws_client(self) -> WebSocketClientProtocol | None:
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
                    for i, j in self.loginResponse.cookies.get_dict().items()
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
            _LOGGER.info("Connected to websocket")
            self._ws_client_connected = True
            for callback in self._connection_subscriptions:
                callback(self._ws_client_connected)
            return client
        except ssl.SSLCertVerificationError as sslcve:
            _LOGGER.exception(sslcve)
        except websockets.exceptions.InvalidStatusCode as isc:
            _LOGGER.exception(isc)
        return None

    async def ws_handler(self, client: WebSocketClientProtocol) -> None:
        receive_buffer = ""
        await client.send("/Device/")  # Request all device data

        while True:
            try:
                receive_buffer += await client.recv()
                new_message_json = json.loads(receive_buffer)
                receive_buffer = ""
                self._json_state = deepmerge.always_merger.merge(
                    self._json_state, new_message_json
                )
                new_message_paths = self._get_json_paths(new_message_json)
                matching_paths = [
                    path
                    for path in new_message_paths
                    if path in self._data_subscriptions
                ]
                for path in matching_paths:
                    matching_path_value = self._get_value_by_json_path(
                        new_message_json, path
                    )
                    for callback in self._data_subscriptions[path]:
                        callback(path, matching_path_value)
            except json.JSONDecodeError:  # Not a valid JSON message yet, keep receiving
                continue
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
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.exception(e)

    def subscribe_connection_updates(
        self,
        callback: Callable[[bool], None],
        trigger_current_value: bool = True,
    ) -> None:
        self._connection_subscriptions.append(callback)
        if trigger_current_value:
            callback(self.get_logged_in())

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
            matching_path_value = self._get_value_by_json_path(self._json_state, path)
            if matching_path_value is not None:
                callback(path, matching_path_value)

    def unsubscribe_data_updates(self, path: str, callback: Callable[[str, Any], None]):
        if path in self._data_subscriptions:
            self._data_subscriptions[path].remove(callback)

    def _get_json_paths(self, json_obj, current_path="", paths=None) -> list[str]:
        if paths is None:
            paths = []
        for key, value in json_obj.items():
            new_path = f"{current_path}.{key}" if current_path else key
            paths.append(new_path)
            if isinstance(value, dict):
                self._get_json_paths(value, new_path, paths)
        return paths

    def _get_value_by_json_path(self, json_obj, path) -> Any | None:
        parts = path.split(".")
        for part in parts:
            if isinstance(json_obj, dict) and part in json_obj:
                json_obj = json_obj[part]
            else:
                return None
        return json_obj

    def logout(self) -> None:
        """Logs out of the NAX system."""
        self.__get_request(path="/logout")
        self.loginResponse = None
        if self.ws_task is not None:
            self.ws_task.cancel()
            self.ws_task = None
        if self.ws_client is not None:
            self.ws_client.close()
            self.ws_client = None

    def get_logged_in(self) -> bool:
        """Returns True if logged in, False if not."""
        return self._ws_client_connected

    def get_base_url(self) -> str | None:
        if self.ip is None:
            return None
        return f"https://{self.ip}"

    def __get_login_url(self) -> str | None:
        if self.get_base_url() is None:
            return None
        return f"{self.get_base_url()}/userlogin.html"

    def __get_websocket_url(self) -> str | None:
        if self.ip is None:
            return None
        return f"wss://{self.ip}/websockify"

    def __get_request(self, path: str):
        if self.get_logged_in():
            get_request = requests.get(
                url=self.get_base_url() + path,
                headers=self.loginResponse.headers,
                cookies=self.loginResponse.cookies,
                verify=False,
                timeout=5,
            )
            if get_request.status_code == 200:
                try:
                    return json.loads(get_request.text)
                except json.JSONDecodeError:
                    return get_request.text
            else:
                print(
                    f"Get request for {get_request.url} failed: {get_request.status_code}"
                )

    # def __post_request(self, path: str, json_data: Any | None) -> Any:
    #     if self.get_logged_in():
    #         post_request = requests.post(
    #             url=self.get_base_url() + path,
    #             headers=self.loginResponse.headers,
    #             cookies=self.loginResponse.cookies,
    #             json=json_data,
    #             verify=False,
    #             timeout=5,
    #         )
    #         if post_request.status_code == 200:
    #             try:
    #                 return json.loads(post_request.text)
    #             except json.JSONDecodeError:
    #                 return post_request.text
    #         else:
    #             print(
    #                 f"Post request for {post_request.url} failed: {post_request.status_code}"
    #             )

    def get_device_name(self) -> str | None:
        return self._json_state["Device"]["DeviceInfo"]["Name"]

    def get_device_mac_address(self) -> str | None:
        return self._json_state["Device"]["DeviceInfo"]["MacAddress"]

    def get_device_manufacturer(self) -> str | None:
        return self._json_state["Device"]["DeviceInfo"]["Manufacturer"]

    def get_device_model(self) -> str | None:
        return self._json_state["Device"]["DeviceInfo"]["Model"]

    def get_device_firmware_version(self) -> str | None:
        return self._json_state["Device"]["DeviceInfo"]["DeviceVersion"]

    def get_device_serial_number(self) -> str | None:
        return self._json_state["Device"]["DeviceInfo"]["SerialNumber"]

    def __get_zone_outputs(self) -> dict[str:Any] | None:
        return self._json_state["Device"]["ZoneOutputs"]["Zones"]

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
        if self._json_state is not None:
            # print(self._json_state["Device"]["AvMatrixRouting"]["Routes"])
            if zone_output in self._json_state["Device"]["AvMatrixRouting"]["Routes"]:
                return self._json_state["Device"]["AvMatrixRouting"]["Routes"][
                    zone_output
                ]["AudioSource"]
            return None

    def get_zone_volume(self, zone_output: str) -> float | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Volume"]

    def get_zone_muted(self, zone_output: str) -> bool | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["IsMuted"]

    def get_input_sources(self) -> list[str] | None:
        inputs = self._json_state["Device"]["InputSources"]["Inputs"]
        return [input_source for input_source in inputs.keys()]

    def get_input_source_name(self, input_source: str) -> str | None:
        if not input_source:
            return None
        return self._json_state["Device"]["InputSources"]["Inputs"][input_source][
            "Name"
        ]

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
        await self.ws_client.send(json.dumps(json_data))

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
        await self.ws_client.send(json.dumps(json_data))

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
        print("setting zone audio source")
        print(json.dumps(json_data))
        await self.ws_client.send(json.dumps(json_data))
