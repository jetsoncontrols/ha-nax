from typing import Any, Tuple
import requests
import json

class NaxApi:
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
        self.loginResponse.headers["X-CREST-XSRF-TOKEN"] = self.loginResponse.headers['CREST-XSRF-TOKEN']
        self.loginResponse.cookies.set("TRACKID", userLoginGetResponse.cookies['TRACKID'])
        return True, "Connected successfully"

    def logout(self) -> None:
        """Logs out of the NAX system."""
        self.get_request(path="/logout")
        self.loginResponse = None
    
    def get_logged_in(self) -> bool:
        """Returns True if logged in, False if not."""
        return self.loginResponse is not None and self.loginResponse.status_code == 200

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

    def get_request(self, path: str):
        if self.get_logged_in():
            get_request = requests.get(url=self.get_base_url() + path, headers=self.loginResponse.headers, cookies=self.loginResponse.cookies, verify=False)
            if get_request.status_code == 200:
                try:
                    return json.loads(get_request.text)
                except json.JSONDecodeError:
                    return get_request.text
            else:
                print(f"Get request for {get_request.url} failed: {get_request.status_code}")
    
    def post_request(self, path: str, json_data: Any | None) -> Any:
        if self.get_logged_in():
            post_request = requests.post(url=self.get_base_url() + path, headers=self.loginResponse.headers, cookies=self.loginResponse.cookies, json=json_data, verify=False)
            if post_request.status_code == 200:
                try:
                    return json.loads(post_request.text)
                except json.JSONDecodeError:
                    return post_request.text
            else:
                print(f"Post request for {post_request.url} failed: {post_request.status_code}")