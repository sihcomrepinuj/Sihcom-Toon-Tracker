from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
from config import Config

Base = declarative_base()

# Many-to-many association table for characters and roles
character_roles = Table(
    'character_roles',
    Base.metadata,
    Column('character_id', Integer, ForeignKey('characters.id'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id'), primary_key=True)
)


class Character(Base):
    __tablename__ = 'characters'

    id = Column(Integer, primary_key=True)  # character_id from ESI
    name = Column(String, nullable=False)
    refresh_token = Column(String, nullable=False)
    access_token = Column(String)
    token_expiry = Column(DateTime)
    corporation_id = Column(Integer, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    roles = relationship('Role', secondary=character_roles, back_populates='characters')
    location = relationship('LocationCache', back_populates='character', uselist=False)
    skills = relationship('CharacterSkill', back_populates='character')

    def __repr__(self):
        return f"<Character(id={self.id}, name='{self.name}')>"


class Role(Base):
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)

    # Relationships
    characters = relationship('Character', secondary=character_roles, back_populates='roles')

    def __repr__(self):
        return f"<Role(id={self.id}, name='{self.name}')>"


class LocationCache(Base):
    __tablename__ = 'location_cache'

    character_id = Column(Integer, ForeignKey('characters.id'), primary_key=True)
    solar_system_id = Column(Integer)
    solar_system_name = Column(String)
    ship_type_id = Column(Integer)
    ship_name = Column(String)
    station_id = Column(Integer, nullable=True)
    is_online = Column(Boolean, default=False)
    last_updated = Column(DateTime, default=datetime.utcnow)

    # Relationships
    character = relationship('Character', back_populates='location')

    def __repr__(self):
        return f"<LocationCache(character_id={self.character_id}, system='{self.solar_system_name}')>"


class CharacterSkill(Base):
    __tablename__ = 'character_skills'

    character_id = Column(Integer, ForeignKey('characters.id'), primary_key=True)
    skill_id = Column(Integer, primary_key=True)
    skill_level = Column(Integer, nullable=False)  # 1-5
    last_updated = Column(DateTime, default=datetime.utcnow)

    # Relationships
    character = relationship('Character', back_populates='skills')

    def __repr__(self):
        return f"<CharacterSkill(character_id={self.character_id}, skill_id={self.skill_id}, level={self.skill_level})>"


class SavedFit(Base):
    __tablename__ = 'saved_fits'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    eft_text = Column(Text, nullable=False)
    hull_type_id = Column(Integer)
    saved_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<SavedFit(id={self.id}, name='{self.name}')>"


class Notepad(Base):
    __tablename__ = 'notepad'

    id = Column(Integer, primary_key=True)  # Always id=1 for global notepad
    content = Column(Text, nullable=False, default='')
    updated_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Notepad(id={self.id}, updated={self.updated_at})>"


# Database initialization
def init_db():
    """Initialize the application database."""
    engine = create_engine(f'sqlite:///{Config.DATABASE_PATH}')
    Base.metadata.create_all(engine)
    return engine


def get_session():
    """Get a new database session."""
    engine = create_engine(f'sqlite:///{Config.DATABASE_PATH}')
    Session = sessionmaker(bind=engine)
    return Session()
