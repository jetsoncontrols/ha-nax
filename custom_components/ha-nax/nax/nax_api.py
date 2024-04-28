from typing import Tuple
import requests
import ssl
from requests.cookies import RequestsCookieJar
import websockets
import asyncio


class NaxApi:
    # ws: websocket.WebSocket = None
    loginResponse: requests.Response = None
    ip: str = None
    username: str = None
    password: str = None

    def __init__(self, ip: str, username: str, password: str) -> None:
        """Initializes the NaxApi class."""
        requests.packages.urllib3.disable_warnings() # Disable SSL warnings
        self.ip = ip
        self.username = username
        self.password = password
    
    def login(self) -> Tuple[bool, str]:
        """Logs in to the NAX system."""
        userLoginGetResponse = requests.get(url=self.get_login_url(), verify=False)
        if userLoginGetResponse.status_code != 200:
            return False, "Could not access Login"

        self.loginResponse = requests.post(
            url=self.get_login_url(), 
            cookies={"TRACKID": userLoginGetResponse.cookies['TRACKID']},
            headers={"Origin": self.get_base_url(), "Referer": self.get_login_url()},
            data={"login": self.username, "passwd": self.password},
            verify=False)
        if self.loginResponse.status_code != 200:
            return False, "Login failed"
        
        self.loginResponse.cookies.set("TRACKID", userLoginGetResponse.cookies['TRACKID'])

        print(self.loginResponse.headers)
        print(self.loginResponse.cookies.get_dict())
        

        # asyncio.run(self.ws_client())

        return True, "Connected successfully"

    async def ws_client(self):
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        headers = {
            'Upgrade': 'websocket',
            'Connection': 'Upgrade',
            'Host': self.ip,
            'User-Agent': 'advanced-rest-client',
            'Origin': self.get_base_url(),
            'Referer': self.get_login_url(),
            'Sec-WebSocket-Version': '13',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            # 'Sec-WebSocket-Key': self.loginResponse.cookies['TRACKID'],
            # 'Sec-WebSocket-Extensions': 'permessage-deflate; client_max_window_bits',
            'Cookie': "; ".join(["%s=%s" %(i, j) for i, j in self.loginResponse.cookies.get_dict().items()]) ,
        }

        print(headers)

        try:
            await websockets.connect(self.get_websocket_url(), ssl=ssl_context, extra_headers=headers)  #, ssl=ssl_context , extra_headers=headers
        except ssl.SSLCertVerificationError as sslcve:
            print(f"Exception: {sslcve}")
        except websockets.exceptions.InvalidStatusCode as isc:
            print(f"InvalidStatusCode: {isc}")
            print(isc.headers)

        # print(headers)

        # async with websockets.connect(self.get_websocket_url(), ssl=ssl_context, extra_headers=headers) as websocket:
        #     print("Connected to websocket")
        #     websocket.send("/Device/DiscoveryConfig/DiscoveryAgent")
        #     greeting = await websocket.recv()
        #     print(f"Received: {greeting}")

        # async for websocket in websockets.connect(self.get_websocket_url(), ssl=ssl_context, extra_headers=headers):
        #     try:
        #         # await websocket.send("Hello there!")
        #         print("Connected to websocket")
        #         greeting = await websocket.recv()
        #         print(f"Received: {greeting}")
        #     except websockets.exceptions.InvalidStatusCode as isc:
        #         print(f"InvalidStatusCode: {isc}")
        #     #     # continue
        #     except Exception as e:
        #         print(f"Exception: {e}")
        #     #     # continue

    def logout(self) -> None:
        """Logs out of the NAX system."""
        requests.get(url=f"https://{self.ip}/logout.html", verify=False)
        self.loginResponse = None
        self.ip = None
        self.username = None
        self.password = None
        # todo: disconnect/cleanup ws

    def get_token(self) -> str | None:
        if self.loginResponse is None:
            return None
        return self.loginResponse.headers['CREST-XSRF-TOKEN']
    
    def get_base_url(self) -> str | None:
        if self.ip is None:
            return None
        return f"https://{self.ip}"
    
    def get_login_url(self) -> str | None:
        if self.get_base_url() is None:
            return None
        return f"{self.get_base_url()}/userlogin.html"

    def get_websocket_url(self) -> str | None:
        if self.ip is None:
            return None
        return f"wss://{self.ip}/websockify"

    # def on_message(ws, message):
    #     print(f"Received message: {message}")

    # def on_error(ws, error):
    #     print(f"Encountered error: {error}")

    # def on_close(ws, close_status_code, close_msg):
    #     print("Connection closed")

    # def on_open(ws):
    #     print("Connection opened")
    #     # ws.send("Hello, Server!")