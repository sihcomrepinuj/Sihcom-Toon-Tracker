import sqlite3
from config import Config
from models import get_session, Character, CharacterSkill


class SkillChecker:
    """Check character skills against ship fitting requirements using SDE data."""

    def __init__(self):
        self.sde_conn = None
        self.type_name_cache = {}
        self.skill_cache = {}

    def connect_sde(self):
        """Connect to the SDE SQLite database."""
        if self.sde_conn is None:
            self.sde_conn = sqlite3.connect(Config.SDE_DATABASE_PATH)
        return self.sde_conn

    def get_type_id(self, type_name):
        """Get type ID from type name using SDE."""
        if type_name in self.type_name_cache:
            return self.type_name_cache[type_name]

        conn = self.connect_sde()
        cursor = conn.cursor()

        # Query invTypes for the type ID
        cursor.execute(
            "SELECT typeID FROM invTypes WHERE typeName = ? COLLATE NOCASE",
            (type_name,)
        )
        result = cursor.fetchone()

        if result:
            type_id = result[0]
            self.type_name_cache[type_name] = type_id
            return type_id

        return None

    def get_skill_requirements(self, type_id):
        """
        Get skill requirements for a given type ID from SDE.

        Returns:
            list[dict]: [{'skill_id': int, 'skill_name': str, 'level': int}, ...]
        """
        if type_id in self.skill_cache:
            return self.skill_cache[type_id]

        conn = self.connect_sde()
        cursor = conn.cursor()

        # Skill requirement attribute IDs in EVE SDE:
        # 182: requiredSkill1, 277: requiredSkill1Level
        # 183: requiredSkill2, 278: requiredSkill2Level
        # 184: requiredSkill3, 279: requiredSkill3Level
        # 1285: requiredSkill4, 1286: requiredSkill4Level
        # 1289: requiredSkill5, 1287: requiredSkill5Level
        # 1290: requiredSkill6, 1288: requiredSkill6Level

        skill_pairs = [
            (182, 277),  # Skill 1
            (183, 278),  # Skill 2
            (184, 279),  # Skill 3
            (1285, 1286),  # Skill 4
            (1289, 1287),  # Skill 5
            (1290, 1288),  # Skill 6
        ]

        skills = []

        for skill_attr_id, level_attr_id in skill_pairs:
            # Get skill type ID
            cursor.execute(
                "SELECT valueInt, valueFloat FROM dgmTypeAttributes WHERE typeID = ? AND attributeID = ?",
                (type_id, skill_attr_id)
            )
            skill_result = cursor.fetchone()

            if skill_result:
                skill_id = int(skill_result[0] or skill_result[1])

                # Get required level
                cursor.execute(
                    "SELECT valueInt, valueFloat FROM dgmTypeAttributes WHERE typeID = ? AND attributeID = ?",
                    (type_id, level_attr_id)
                )
                level_result = cursor.fetchone()

                if level_result:
                    level = int(level_result[0] or level_result[1])

                    # Get skill name
                    cursor.execute(
                        "SELECT typeName FROM invTypes WHERE typeID = ?",
                        (skill_id,)
                    )
                    name_result = cursor.fetchone()

                    if name_result:
                        skills.append({
                            'skill_id': skill_id,
                            'skill_name': name_result[0],
                            'level': level
                        })

        self.skill_cache[type_id] = skills
        return skills

    def get_fit_requirements(self, item_names):
        """
        Get all unique skill requirements for a list of item names.

        Args:
            item_names: List of item names (hull + modules)

        Returns:
            dict: {skill_id: {'skill_name': str, 'level': int}, ...}
                  Keys are skill_id, values contain the HIGHEST level required across all items
        """
        all_requirements = {}

        for item_name in item_names:
            type_id = self.get_type_id(item_name)
            if type_id:
                requirements = self.get_skill_requirements(type_id)
                for req in requirements:
                    skill_id = req['skill_id']
                    # Keep the highest level required
                    if skill_id not in all_requirements or req['level'] > all_requirements[skill_id]['level']:
                        all_requirements[skill_id] = {
                            'skill_name': req['skill_name'],
                            'level': req['level']
                        }

        return all_requirements

    def check_character_fit(self, character_id, fit_requirements):
        """
        Check if a character meets the skill requirements for a fit.

        Args:
            character_id: Character ID to check
            fit_requirements: Dict from get_fit_requirements()

        Returns:
            dict: {
                'can_fly': bool,
                'total_skills': int,
                'met_skills': int,
                'missing_skills': [{'skill_name': str, 'required_level': int, 'current_level': int}, ...]
            }
        """
        session = get_session()
        character = session.query(Character).filter_by(id=character_id).first()

        if not character:
            session.close()
            return None

        # Get character's skills
        character_skills = {skill.skill_id: skill.skill_level for skill in character.skills}

        missing_skills = []
        met_count = 0

        for skill_id, req in fit_requirements.items():
            current_level = character_skills.get(skill_id, 0)
            required_level = req['level']

            if current_level >= required_level:
                met_count += 1
            else:
                missing_skills.append({
                    'skill_name': req['skill_name'],
                    'required_level': required_level,
                    'current_level': current_level
                })

        session.close()

        return {
            'can_fly': len(missing_skills) == 0,
            'total_skills': len(fit_requirements),
            'met_skills': met_count,
            'missing_skills': missing_skills
        }

    def check_all_characters(self, fit_requirements):
        """
        Check all characters against fit requirements.

        Args:
            fit_requirements: Dict from get_fit_requirements()

        Returns:
            list[dict]: [{
                'character_id': int,
                'character_name': str,
                'can_fly': bool,
                'total_skills': int,
                'met_skills': int,
                'missing_skills': list
            }, ...]
        """
        session = get_session()
        characters = session.query(Character).all()

        results = []

        for character in characters:
            check_result = self.check_character_fit(character.id, fit_requirements)
            if check_result:
                results.append({
                    'character_id': character.id,
                    'character_name': character.name,
                    **check_result
                })

        session.close()

        # Sort: fully qualified first, then partially trained, then missing most
        results.sort(key=lambda x: (-x['can_fly'], -x['met_skills']))

        return results

    def close(self):
        """Close SDE database connection."""
        if self.sde_conn:
            self.sde_conn.close()
            self.sde_conn = None


# Global instance
skill_checker = SkillChecker()
