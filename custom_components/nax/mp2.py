"""Media Player 2.0 (MP2) client for Crestron DM-NAX devices."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from cresnextws import CresNextWSClient

_LOGGER = logging.getLogger(__name__)

# Provider key for the Generic/Connected Speakers provider
PROVIDER_KEY_GENERIC = "Provider1"


class NaxMP2Client:
    """Helper that builds MP2 command payloads and sends them via CresNextWSClient."""

    def __init__(
        self,
        client: CresNextWSClient,
        player_id: str,
        profile_key: str,
    ) -> None:
        """Initialize the MP2 client.

        Args:
            client: Existing CresNextWSClient instance (from DataEventManager).
            player_id: Player identifier, e.g. "Player01".
            profile_key: User profile key, e.g. "Profile1".
        """
        self._client = client
        self._player_id = player_id
        self._profile_key = profile_key

    # ------------------------------------------------------------------
    # Detection (static, called before instantiation)
    # ------------------------------------------------------------------

    @staticmethod
    async def detect(
        client: CresNextWSClient,
        zone_outputs: dict[str, Any],
        input_sources: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Detect MP2 availability and build zone-to-player mapping.

        Returns a dict with keys ``profile_key``, ``player_map``, and
        ``streaming_input_map`` on success, or ``None`` when MP2 is not
        available.

        ``player_map``  : {zone_key: player_id}  e.g. {"Zone1": "Player01"}
        ``streaming_input_map``: {zone_key: input_key} e.g. {"Zone1": "Input09"}
        """
        # Check media player mode
        mode_resp = await client.http_get(
            "/Device/StreamingServices/MediaplayerMode"
        )
        mode = (
            (mode_resp or {})
            .get("content", {})
            .get("Device", {})
            .get("StreamingServices", {})
            .get("MediaplayerMode")
        )
        if mode != "MP2":
            _LOGGER.debug("Device not in MP2 mode (mode=%s), skipping MP2 setup", mode)
            return None

        # Find the first enabled user profile
        profiles_resp = await client.http_get(
            "/Device/StreamingServices/UserProfiles"
        )
        profiles = (
            (profiles_resp or {})
            .get("content", {})
            .get("Device", {})
            .get("StreamingServices", {})
            .get("UserProfiles", {})
        )
        profile_key: str | None = None
        for key, data in profiles.items():
            if data.get("IsEnabled", False):
                profile_key = key
                break

        if profile_key is None:
            _LOGGER.debug("No enabled user profiles found, skipping MP2 setup")
            return None

        # Build ordered list of MediaPlayer-type inputs
        media_inputs = sorted(
            key
            for key, data in input_sources.items()
            if data.get("AudioType") == "MediaPlayer"
        )

        if not media_inputs:
            _LOGGER.debug("No MediaPlayer inputs found, skipping MP2 setup")
            return None

        # Map each input to its player by index position
        input_to_player = {
            inp: f"Player{str(idx + 1).zfill(2)}"
            for idx, inp in enumerate(media_inputs)
        }

        # Build zone → player and zone → streaming input maps
        player_map: dict[str, str] = {}
        streaming_input_map: dict[str, str] = {}
        for zone_key, zone_data in zone_outputs.items():
            reserved_player = (
                zone_data.get("ZoneBasedProviders", {}).get("ReservedPlayer", "")
            )
            if reserved_player in input_to_player:
                player_map[zone_key] = input_to_player[reserved_player]
                streaming_input_map[zone_key] = reserved_player

        if not player_map:
            _LOGGER.debug("No zone-to-player mappings resolved, skipping MP2 setup")
            return None

        _LOGGER.info(
            "MP2 detected: profile=%s, mappings=%s",
            profile_key,
            player_map,
        )
        return {
            "profile_key": profile_key,
            "player_map": player_map,
            "streaming_input_map": streaming_input_map,
        }

    # ------------------------------------------------------------------
    # Playback commands
    # ------------------------------------------------------------------

    async def load_source(self, url: str, auto_play: bool = True) -> None:
        """Play an audio URL via the Connected Speakers (Generic) provider."""
        await self._send_action(
            "LoadSource",
            {
                "ProfileKey": self._profile_key,
                "ProviderKey": PROVIDER_KEY_GENERIC,
                "AutoPlay": auto_play,
                "AudioSourceUrl": url,
            },
        )

    async def play(self) -> None:
        """Resume playback."""
        await self._send_action("Play")

    async def pause(self) -> None:
        """Pause playback."""
        await self._send_action("Pause")

    async def next_track(self) -> None:
        """Skip to next track."""
        await self._send_action("NextTrack")

    async def previous_track(self) -> None:
        """Skip to previous track."""
        await self._send_action("PreviousTrack")

    async def seek(self, position: float) -> None:
        """Seek to *position* seconds."""
        await self._send_action("Seek", {"Position": int(position)})

    async def shuffle(self, enabled: bool) -> None:
        """Set shuffle state."""
        await self._send_action("Shuffle", {"ShufState": enabled})

    async def repeat(self, mode: int) -> None:
        """Set repeat mode (0=off, 1=track, 2=playlist)."""
        await self._send_action("Repeat", {"RepState": mode})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_action(
        self,
        action_id: str,
        options: dict[str, Any] | None = None,
    ) -> None:
        """Build and send an MP2 RequestAction envelope."""
        await self._client.ws_post(
            payload={
                "Device": {
                    "MediaPlayerNeXt": {
                        "RequestAction": {
                            "RcSessionId": "",
                            "MsgId": str(uuid.uuid1()),
                            "PlayerId": self._player_id,
                            "ActionId": action_id,
                            "ActionIdOptions": options or {},
                        }
                    }
                }
            }
        )
