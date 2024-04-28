from .nax_api import NaxApi

naxApi = NaxApi(ip="192.168.1.59", username="admin", password="password")
connected, message = naxApi.login()
if connected:
    print("Login Success: " + message)
else:
    print("Login Failed: " + message)
naxApi.logout()
