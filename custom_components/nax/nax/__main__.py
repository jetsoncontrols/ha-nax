from config.custom_components.nax.nax.nax_api import NaxApi
import json
import asyncio


async def test(api: NaxApi):
    connected, message = await naxApi.http_login()
    print(f"Login {str(connected)}: " + message)
    if connected:
        print(json.dumps(naxApi.get_data(data_path="Device"), indent=2))
        # print(json.dumps(naxApi.get_data(data_path="Device.MediaNavigation"), indent=2))
        # print(json.dumps(naxApi.get_data(data_path="Device.NaxAudio"), indent=2))

        # print(
        #     json.dumps(
        #         naxApi.post_request(
        #             path="/Device/ZoneOutputs/Zones/Zone01/ZoneAudio",
        #             json_data={
        #                 "Device": {
        #                     "ZoneOutputs": {
        #                         "Zones": {
        #                             "Zone01": {
        #                                 "ZoneAudio": {
        #                                     "Volume": 50,
        #                                 }
        #                             }
        #                         }
        #                     }
        #                 }
        #             },
        #         )
        #     )
        # )

        # zoneOutputsJson = naxApi.get_request(path="/Device/ZoneOutputs")
        # for zoneOutput in zoneOutputsJson["Device"]["ZoneOutputs"]["Zones"]:
        #     print(
        #         json.dumps(
        #             zoneOutputsJson["Device"]["ZoneOutputs"]["Zones"][zoneOutput]["Name"],
        #             indent=2,
        #         )
        #     )

        naxApi.logout()


naxApi = NaxApi(
    ip="192.168.1.195", username="admin", password="password", http_fallback=True
)
asyncio.run(test(naxApi))
