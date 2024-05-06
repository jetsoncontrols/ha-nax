from .nax_api import NaxApi
import json

naxApi = NaxApi(ip="192.168.1.58", username="admin", password="password")
connected, message = naxApi.login()
print(f"Login {str(connected)}: " + message)

if connected:
    # print(json.dumps(naxApi.get_request(path="/Device/InputSources"), indent=2))
    print(json.dumps(naxApi.get_request(path="/Device/DeviceInfo"), indent=2))
    # print(json.dumps(naxApi.get_request(path="/Device/AvMatrixRouting"), indent=2))
    # include_data = {
    #     "Device": {
    #         "DeviceOperations": {
    #             "EnterStandby": False,
    #         }
    #     }
    # }

    # print(
    #     json.dumps(
    #         naxApi.post_request(path="/Device/DeviceOperations", json_data=include_data)
    #     )
    # )

    # print(json.dumps(naxApi.get_request(path="/Device/AvMatrixRouting/Longpoll"), indent=2))

    # zoneOutputsJson = naxApi.get_request(path="/Device/ZoneOutputs")
    # for zoneOutput in zoneOutputsJson["Device"]["ZoneOutputs"]["Zones"]:
    #     print(
    #         json.dumps(
    #             zoneOutputsJson["Device"]["ZoneOutputs"]["Zones"][zoneOutput]["Name"],
    #             indent=2,
    #         )
    #     )

    naxApi.logout()
