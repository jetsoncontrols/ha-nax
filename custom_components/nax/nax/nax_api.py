import logging
from websockets import WebSocketClientProtocol
import websockets
from websockets.extensions import permessage_deflate
import asyncio
from typing import Any
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

    _json_state: dict[str, Any] = {}

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
            # "Upgrade": "websocket",
            # "Connection": "Upgrade",
            # "Host": self.ip,
            # "User-Agent": "advanced-rest-client",
            "Origin": self.get_base_url(),
            # "Referer": self.__get_login_url(),
            # "Sec-WebSocket-Version": "13",
            "Accept-Encoding": "gzip, deflate, br",
            # "Accept-Language": "en-US,en;q=0.9",
            # "X-CREST-XSRF-TOKEN": self.loginResponse.headers["X-CREST-XSRF-TOKEN"],
            # "Sec-WebSocket-Key": self.loginResponse.cookies["TRACKID"],  # ???
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
            return client
        except ssl.SSLCertVerificationError as sslcve:
            _LOGGER.exception(sslcve)
        except websockets.exceptions.InvalidStatusCode as isc:
            _LOGGER.exception(isc)
        return None

    async def ws_handler(self, client: WebSocketClientProtocol) -> None:
        receive_buffer = ""
        await client.send("/Device/")

        while True:
            try:
                receive_buffer += await client.recv()
                new_message_json = json.loads(receive_buffer)
                receive_buffer = ""
                self._json_state = deepmerge.always_merger.merge(
                    self._json_state, new_message_json
                )
            except json.JSONDecodeError:
                # Not a valid JSON message yet, keep receiving
                continue
            except websockets.exceptions.ConnectionClosedOK:
                break
            except websockets.exceptions.ConnectionClosedError:
                _LOGGER.warning("Connection closed")
                self.login()
                break
            except Exception as e:
                _LOGGER.exception(e)

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
        return self.loginResponse is not None and self.loginResponse.status_code == 200

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

    def post_request(self, path: str, json_data: Any | None) -> Any:
        return self.__post_request(path, json_data)

    def __post_request(self, path: str, json_data: Any | None) -> Any:
        if self.get_logged_in():
            post_request = requests.post(
                url=self.get_base_url() + path,
                headers=self.loginResponse.headers,
                cookies=self.loginResponse.cookies,
                json=json_data,
                verify=False,
                timeout=5,
            )
            if post_request.status_code == 200:
                try:
                    return json.loads(post_request.text)
                except json.JSONDecodeError:
                    return post_request.text
            else:
                print(
                    f"Post request for {post_request.url} failed: {post_request.status_code}"
                )

    def __get_device_info(self) -> Any:
        return self.__get_request("/Device/DeviceInfo")

    def get_device_name(self) -> str | None:
        device_info = self.__get_device_info()
        if device_info is not None:
            return device_info["Device"]["DeviceInfo"]["Name"]

    def get_device_mac_address(self) -> str | None:
        device_info = self.__get_device_info()
        if device_info is not None:
            return device_info["Device"]["DeviceInfo"]["MacAddress"]

    def get_device_manufacturer(self) -> str | None:
        device_info = self.__get_device_info()
        if device_info is not None:
            return device_info["Device"]["DeviceInfo"]["Manufacturer"]

    def get_device_model(self) -> str | None:
        device_info = self.__get_device_info()
        if device_info is not None:
            return device_info["Device"]["DeviceInfo"]["Model"]

    def get_device_firmware_version(self) -> str | None:
        device_info = self.__get_device_info()
        if device_info is not None:
            return device_info["Device"]["DeviceInfo"]["DeviceVersion"]

    def get_device_serial_number(self) -> str | None:
        device_info = self.__get_device_info()
        if device_info is not None:
            return device_info["Device"]["DeviceInfo"]["SerialNumber"]

    def __get_zone_outputs(self) -> Any:
        zone_outputs_json = self.__get_request("/Device/ZoneOutputs")
        if zone_outputs_json is not None:
            return zone_outputs_json["Device"]["ZoneOutputs"]["Zones"]

    def get_all_zone_outputs(self) -> list[str]:
        result = []
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            for zone_output in zone_outputs_json:
                result.append(zone_output)
        return result

    def get_all_zone_outputs_names(self) -> {str: str}:
        result = {}

        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            for zone_output in zone_outputs_json:
                result[zone_output] = zone_outputs_json[zone_output]["Name"]

        return result

    def set_zone_volume(self, zone_output: str, volume: float) -> None:
        self.__post_request(
            path=f"/Device/ZoneOutputs/Zones/{zone_output}/ZoneAudio",
            json_data={
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
            },
        )

    def get_zone_volume(self, zone_output: str) -> float | None:
        zone_outputs_json = self.__get_zone_outputs()
        if zone_outputs_json is not None:
            return zone_outputs_json[zone_output]["ZoneAudio"]["Volume"]
