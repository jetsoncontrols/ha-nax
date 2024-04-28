from .nax_api import NaxApi
import json

naxApi = NaxApi(ip="192.168.1.59", username="admin", password="password")
connected, message = naxApi.login()
print(f"Login {str(connected)}: " + message)

if (connected):
    # print(json.dumps(naxApi.get_request(path="/Device/InputSources"), indent=2))
    # print(json.dumps(naxApi.get_request(path="/Device/ZoneOutputs"), indent=2))
    print(json.dumps(naxApi.get_request(path="/Device/SystemClock"), indent=2))
    
    # include_data = {"Device":{"Ethernet":{"HostName":"MyDevice"}}}
    include_data = {
        "Device": {
            "SystemClock": {
                "Ntp": {
                    "IsEnabled": True,
                },
            }
        }
    }
    print(json.dumps(naxApi.post_request(path="/Device/SystemClock", json_data=include_data)))
    naxApi.logout()
