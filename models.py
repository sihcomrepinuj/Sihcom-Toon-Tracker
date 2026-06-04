from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Table
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from datetime import datetime
from config import Config

Base = declarative_base()

# Preset color palette for role tags
ROLE_PALETTE = [
    '#5865F2',  # blue
    '#ED4245',  # red
    '#3BA55C',  # green
    '#FAA61A',  # amber
    '#9B59B6',  # purple
    '#E91E8C',  # pink
    '#1ABC9C',  # teal
    '#E67E22',  # orange
    '#607D8B',  # blue-grey
    '#3498DB',  # sky
]

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
    total_sp = Column(Integer, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    account_id = Column(Integer, ForeignKey('accounts.id', ondelete='SET NULL'), nullable=True)

    # Relationships
    roles = relationship('Role', secondary=character_roles, back_populates='characters')
    location = relationship('LocationCache', back_populates='character', uselist=False, cascade='all, delete-orphan')
    skills = relationship('CharacterSkill', back_populates='character', cascade='all, delete-orphan')
    account = relationship('Account', back_populates='characters')

    def __repr__(self):
        return f"<Character(id={self.id}, name='{self.name}')>"


class Role(Base):
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    color = Column(String, nullable=True)  # hex color like '#5865F2'

    # Relationships
    characters = relationship('Character', secondary=character_roles, back_populates='roles')

    def __repr__(self):
        return f"<Role(id={self.id}, name='{self.name}')>"


class Account(Base):
    __tablename__ = 'accounts'

    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String, nullable=False, unique=True)
    subscription = Column(String, nullable=False, default='unknown')  # 'omega' | 'alpha' | 'unknown'
    notes        = Column(Text, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    characters = relationship('Character', back_populates='account')

    def __repr__(self):
        return f"<Account(id={self.id}, name='{self.name}', subscription='{self.subscription}')>"


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


from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Database initialization
def init_db():
    """Initialize the application database, applying any needed migrations."""
    engine = create_engine(f'sqlite:///{Config.DATABASE_PATH}')
    Base.metadata.create_all(engine)
    _migrate_add_account_id(engine)
    _migrate_add_total_sp(engine)
    _migrate_add_role_color(engine)
    return engine


def _migrate_add_account_id(engine):
    """Add characters.account_id if missing (idempotent)."""
    with engine.connect() as conn:
        from sqlalchemy import text
        result = conn.execute(text("PRAGMA table_info(characters)")).fetchall()
        cols = [row[1] for row in result]
        if 'account_id' not in cols:
            conn.execute(text(
                "ALTER TABLE characters ADD COLUMN account_id INTEGER "
                "REFERENCES accounts(id) ON DELETE SET NULL"
            ))
            conn.commit()


def _migrate_add_total_sp(engine):
    """Add characters.total_sp if missing (idempotent)."""
    with engine.connect() as conn:
        from sqlalchemy import text
        result = conn.execute(text("PRAGMA table_info(characters)")).fetchall()
        cols = [row[1] for row in result]
        if 'total_sp' not in cols:
            conn.execute(text(
                "ALTER TABLE characters ADD COLUMN total_sp INTEGER"
            ))
            conn.commit()


def _migrate_add_role_color(engine):
    """Add roles.color if missing (idempotent), and backfill NULL colors."""
    with engine.connect() as conn:
        from sqlalchemy import text
        result = conn.execute(text("PRAGMA table_info(roles)")).fetchall()
        cols = [row[1] for row in result]
        if 'color' not in cols:
            conn.execute(text(
                "ALTER TABLE roles ADD COLUMN color VARCHAR"
            ))
            conn.commit()

        # Backfill any roles that don't have a color yet
        null_roles = conn.execute(
            text("SELECT id FROM roles WHERE color IS NULL ORDER BY id")
        ).fetchall()
        if null_roles:
            for i, row in enumerate(null_roles):
                color = ROLE_PALETTE[i % len(ROLE_PALETTE)]
                conn.execute(
                    text("UPDATE roles SET color = :color WHERE id = :id"),
                    {'color': color, 'id': row[0]},
                )
            conn.commit()


def get_session():
    """Get a new database session."""
    engine = create_engine(f'sqlite:///{Config.DATABASE_PATH}')
    Session = sessionmaker(bind=engine)
    return Session()
