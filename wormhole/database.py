from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Column, Integer

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
    def get(cls, guild_id: int) -> Optional[WormholeChannel]:
        """
        Retrieves the first WormholeChannel with the given guild_id.
        TODO: Change to return a list if multiple entries can exist.
        """
        query = (
            session.query(cls)
            .filter_by(
                guild_id=guild_id,
            )
            .one_or_none()
        )
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
        return session.query(cls).filter_by(channel_id=channel_id).first() is not None

    @classmethod
    def get_channel_ids(cls) -> list[int]:
        """
        Returns a list of all channel_ids currently stored.
        """
        results = session.query(cls.channel_id).all()
        return [r[0] for r in results]

    def save(self):
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
