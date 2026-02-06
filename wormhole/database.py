from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text

from pie.database import database, session


class WormholeChannel(database.base):
    __tablename__ = "wormhole_wormhole_wormholechannel"

    idx = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(BigInteger)
    channel_id = Column(BigInteger)

    @classmethod
    def add(cls, guild_id: int, channel_id: int) -> WormholeChannel:
        """
        Adds a new WormholeChannel entry to the database.
        """
        query = cls(guild_id=guild_id, channel_id=channel_id)
        session.add(query)
        session.commit()
        return query

    @classmethod
    def remove(cls, guild_id: int, channel_id: int) -> int:
        """
        Removes the WormholeChannel entry matching the given guild_id and channel_id.
        Returns the number of rows deleted.
        """
        query = (
            session.query(cls)
            .filter_by(
                guild_id=guild_id,
                channel_id=channel_id,
            )
            .delete()
        )
        session.commit()
        return query

    @classmethod
    def check_existence(cls, channel_id: int) -> bool:
        """
        Checks whether an entry exists with the given channel_id.
        Returns True if exists, False otherwise.
        """
        return (
            session.query(cls.channel_id)
            .filter_by(channel_id=channel_id)
            .limit(1)
            .scalar()
            is not None
        )

    @classmethod
    def get_channel_ids(cls) -> list[int]:
        """
        Returns a list of all channel_ids currently stored.
        """
        results = session.query(cls.channel_id).all()
        return [r[0] for r in results]

    @classmethod
    def get_guild_id_by_channel_id(cls, channel_id: int) -> int | None:
        """
        Returns the guild_id corresponding to the given channel_id.
        If not found, returns None.
        """
        result = session.query(cls.guild_id).filter_by(channel_id=channel_id).first()
        return result[0] if result else None

    def save(self) -> None:
        """
        Commits any changes made to the current instance to the database.
        """
        session.commit()

    def __repr__(self) -> str:
        """
        String representation for debugging/logging purposes.
        """
        return (
            f'<{self.__class__.__name__} idx="{self.idx}" '
            f'guild_id="{self.guild_id}" channel_id="{self.channel_id}" '
        )

    def dump(self) -> dict:
        """
        Returns a dictionary representation of the object.
        """
        return {
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
        }


class BanTimeout(database.base):
    __tablename__ = "wormhole_wormhole_bantimeout"

    idx = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    time = Column(DateTime)

    @classmethod
    def add(cls, name: str, time=None):
        """
        Add a new record to the database.

        Args:
            name (str): The name to insert.
            time (optional): An associated timestamp or value. Defaults to None.

        Returns:
            The newly created object after being committed to the database.
        """
        query = cls(name=name, time=time)
        session.add(query)
        session.commit()
        return query

    def delete(self):
        """
        Delete the current object from the database.
        """
        session.delete(self)
        session.commit()

    @classmethod
    def get(cls, user: str):
        """
        Retrieve all rows matching a given user name.

        Args:
            user (str): The name to filter by.

        Returns:
            list: A list of matching objects.
        """
        query = session.query(cls).filter_by(name=user)
        return query.all()

    @classmethod
    def get_all(cls):
        """
        Retrieve all rows from the database table.

        Returns:
            list: A list of all objects of this class.
        """
        query = session.query(cls).all()
        return query

    @classmethod
    def get_dict(cls):
        """
        Retrieve all rows and return them as a dictionary mapping name -> time.

        Returns:
            dict: A dictionary where keys are names and values are times.
        """
        ban_list = {}
        results = session.query(cls).all()
        for r in results:
            ban_list.update({r.name: r.time})
        return ban_list

    def __repr__(self) -> str:
        """
        Provide a developer-friendly string representation of the object.

        Returns:
            str: String representation including class name, idx, and name.
        """
        return (
            f'<{self.__class__.__name__} idx="{self.idx}" '
            f'name="{self.name}" time="{self.time}" '
        )

    def dump(self) -> dict:
        """
        Convert the object into a serializable dictionary.

        Returns:
            dict: A dictionary containing the 'name' and 'time' fields.
        """
        return {
            "name": self.name,
            "time": self.time,
        }


class WormholePatterns(database.base):
    __tablename__ = "wormhole_wormhole_wormholepatterns"

    idx = Column(Integer, primary_key=True, autoincrement=True)
    regex_pattern = Column(String(255), nullable=False)
    replacement = Column(Text, nullable=False)

    @classmethod
    def set_pattern(cls, regex_pattern: str, replacement: str):
        """
        Adds a new pattern only if it does not already exist.
        """
        existing_pattern = (
            session.query(cls).filter_by(regex_pattern=regex_pattern).first()
        )
        if existing_pattern:
            raise ValueError(f"Pattern with regex '{regex_pattern}' already exists.")
        new_pattern = cls(regex_pattern=regex_pattern, replacement=replacement)
        session.add(new_pattern)
        session.commit()
        return new_pattern

    @classmethod
    def update_pattern(cls, idx: int, regex_pattern: str, replacement: str):
        """
        Updates an existing pattern based on idx.
        """
        pattern = session.query(cls).filter_by(idx=idx).first()
        if not pattern:
            raise ValueError(f"No pattern found with idx {idx}.")

        pattern.regex_pattern = regex_pattern
        pattern.replacement = replacement

        session.commit()
        return pattern

    @classmethod
    def get_patterns_dict(cls) -> dict:
        """
        Fetches all WormholePatterns entries and returns a dict:
        { regex_pattern: replacement }
        """
        return {row.regex_pattern: row.replacement for row in session.query(cls).all()}

    @classmethod
    def get_patterns(cls):
        """
        Retrieve all wormhole patterns from the database.

        :param session: SQLAlchemy session object
        :return: List of WormholePatterns objects
        """
        return session.query(cls).all()

    @classmethod
    def get(cls, idx: int):
        """
        Retrieve all rows matching a given id.

        Args:
            idx (int): The id to filter by.

        Returns:
            list: A list of matching objects.
        """
        query = session.query(cls).filter_by(idx=idx)
        return query.all()

    def delete(self):
        """
        Delete the current object from the database.
        """
        session.delete(self)
        session.commit()

    def __repr__(self):
        return f"<WormholePatterns(id={self.idx}, regex_pattern='{self.regex_pattern}', replacement='{self.replacement}')>"
