import asyncio
import aiohttp
import time
import logging
from datetime import datetime, timedelta
from threading import Thread
from models import get_session, Character, LocationCache, CharacterSkill
from auth import refresh_access_token
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ESIPoller:
    """Background poller for ESI data."""

    def __init__(self):
        self.running = False
        self.thread = None
        self.name_cache = {}  # Cache for system and type names

    def start(self):
        """Start the poller in a background thread."""
        if not self.running:
            self.running = True
            self.thread = Thread(target=self._run_loop, daemon=True)
            self.thread.start()
            logger.info("ESI poller started")

    def stop(self):
        """Stop the poller."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("ESI poller stopped")

    def _run_loop(self):
        """Main polling loop (runs in background thread)."""
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Initial poll
        loop.run_until_complete(self.poll_all_characters())
        loop.run_until_complete(self.poll_all_skills())

        # Continuous polling
        last_skill_poll = time.time()

        while self.running:
            try:
                # Poll locations every cycle
                loop.run_until_complete(self.poll_all_characters())

                # Poll skills if interval has passed
                if time.time() - last_skill_poll > Config.SKILLS_POLL_INTERVAL:
                    loop.run_until_complete(self.poll_all_skills())
                    last_skill_poll = time.time()

                # Sleep until next poll
                time.sleep(Config.LOCATION_POLL_INTERVAL)

            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                time.sleep(10)  # Wait before retrying

        loop.close()

    async def poll_all_characters(self):
        """Poll location data for all characters."""
        session = get_session()
        characters = session.query(Character).all()

        if not characters:
            session.close()
            return

        logger.info(f"Polling location data for {len(characters)} characters")

        async with aiohttp.ClientSession() as http_session:
            tasks = [
                self.poll_character_location(http_session, char, session)
                for char in characters
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        session.close()

    async def poll_character_location(self, http_session, character, db_session):
        """Poll a single character's location, online status, and ship."""
        try:
            # Refresh token if needed
            if character.token_expiry and character.token_expiry < datetime.utcnow():
                logger.info(f"Refreshing token for {character.name}")
                tokens = refresh_access_token(character.refresh_token)
                character.access_token = tokens['access_token']
                character.refresh_token = tokens['refresh_token']
                character.token_expiry = tokens['token_expiry']
                db_session.commit()

            headers = {'Authorization': f'Bearer {character.access_token}'}

            # Fetch location, online status, ship, and public char info in parallel
            location_task = self.fetch_json(
                http_session,
                f'https://esi.evetech.net/latest/characters/{character.id}/location/',
                headers
            )
            online_task = self.fetch_json(
                http_session,
                f'https://esi.evetech.net/latest/characters/{character.id}/online/',
                headers
            )
            ship_task = self.fetch_json(
                http_session,
                f'https://esi.evetech.net/latest/characters/{character.id}/ship/',
                headers
            )
            # Public endpoint — no auth needed, fetches corporation_id
            corp_task = self.fetch_json(
                http_session,
                f'https://esi.evetech.net/latest/characters/{character.id}/',
                None
            )

            location_data, online_data, ship_data, corp_data = await asyncio.gather(
                location_task, online_task, ship_task, corp_task, return_exceptions=True
            )

            if isinstance(location_data, Exception) or isinstance(ship_data, Exception):
                logger.error(f"Error fetching data for {character.name}")
                return

            # Get names for IDs
            system_id = location_data.get('solar_system_id')
            ship_type_id = ship_data.get('ship_type_id')
            station_id = location_data.get('station_id')

            system_name = await self.get_system_name(http_session, system_id)
            ship_name = await self.get_type_name(http_session, ship_type_id)

            is_online = online_data.get('online', False) if not isinstance(online_data, Exception) else False

            # Update corporation_id if available
            if not isinstance(corp_data, Exception) and corp_data:
                new_corp_id = corp_data.get('corporation_id')
                if new_corp_id and new_corp_id != character.corporation_id:
                    character.corporation_id = new_corp_id
                    db_session.commit()

            # Update or create location cache
            location_cache = db_session.query(LocationCache).filter_by(
                character_id=character.id
            ).first()

            if location_cache:
                location_cache.solar_system_id = system_id
                location_cache.solar_system_name = system_name
                location_cache.ship_type_id = ship_type_id
                location_cache.ship_name = ship_name
                location_cache.station_id = station_id
                location_cache.is_online = is_online
                location_cache.last_updated = datetime.utcnow()
            else:
                location_cache = LocationCache(
                    character_id=character.id,
                    solar_system_id=system_id,
                    solar_system_name=system_name,
                    ship_type_id=ship_type_id,
                    ship_name=ship_name,
                    station_id=station_id,
                    is_online=is_online,
                    last_updated=datetime.utcnow()
                )
                db_session.add(location_cache)

            db_session.commit()
            logger.debug(f"Updated location for {character.name}: {system_name} in {ship_name}")

        except Exception as e:
            logger.error(f"Error polling {character.name}: {e}", exc_info=True)

    async def poll_all_skills(self):
        """Poll skills for all characters."""
        session = get_session()
        characters = session.query(Character).all()

        if not characters:
            session.close()
            return

        logger.info(f"Polling skills for {len(characters)} characters")

        async with aiohttp.ClientSession() as http_session:
            tasks = [
                self.poll_character_skills(http_session, char, session)
                for char in characters
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        session.close()

    async def poll_character_skills(self, http_session, character, db_session):
        """Poll a single character's skills."""
        try:
            # Refresh token if needed
            if character.token_expiry and character.token_expiry < datetime.utcnow():
                tokens = refresh_access_token(character.refresh_token)
                character.access_token = tokens['access_token']
                character.refresh_token = tokens['refresh_token']
                character.token_expiry = tokens['token_expiry']
                db_session.commit()

            headers = {'Authorization': f'Bearer {character.access_token}'}

            skills_data = await self.fetch_json(
                http_session,
                f'https://esi.evetech.net/latest/characters/{character.id}/skills/',
                headers
            )

            if isinstance(skills_data, Exception):
                logger.error(f"Error fetching skills for {character.name}")
                return

            # Delete existing skills
            db_session.query(CharacterSkill).filter_by(character_id=character.id).delete()

            # Add new skills
            for skill in skills_data.get('skills', []):
                character_skill = CharacterSkill(
                    character_id=character.id,
                    skill_id=skill['skill_id'],
                    skill_level=skill['trained_skill_level'],
                    last_updated=datetime.utcnow()
                )
                db_session.add(character_skill)

            db_session.commit()
            logger.info(f"Updated {len(skills_data.get('skills', []))} skills for {character.name}")

        except Exception as e:
            logger.error(f"Error polling skills for {character.name}: {e}", exc_info=True)

    async def fetch_json(self, session, url, headers=None):
        """Fetch JSON from a URL."""
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"HTTP {response.status} for {url}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return e

    async def get_system_name(self, session, system_id):
        """Get system name from ID (with caching)."""
        if system_id in self.name_cache:
            return self.name_cache[system_id]

        data = await self.fetch_json(
            session,
            f'https://esi.evetech.net/latest/universe/systems/{system_id}/'
        )

        if data and 'name' in data:
            name = data['name']
            self.name_cache[system_id] = name
            return name

        return f"System {system_id}"

    async def get_type_name(self, session, type_id):
        """Get type name from ID (with caching)."""
        if type_id in self.name_cache:
            return self.name_cache[type_id]

        data = await self.fetch_json(
            session,
            f'https://esi.evetech.net/latest/universe/types/{type_id}/'
        )

        if data and 'name' in data:
            name = data['name']
            self.name_cache[type_id] = name
            return name

        return f"Type {type_id}"


# Global poller instance
poller = ESIPoller()
