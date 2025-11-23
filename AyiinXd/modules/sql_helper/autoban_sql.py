from sqlalchemy import Column, String, BigInteger, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from AyiinXd.modules.sql_helper import BASE, SESSION


# ---------------- MODEL ---------------- #

class AutoBanChannel(BASE):
    __tablename__ = "autoban_channels"
    channel_id = Column(BigInteger, primary_key=True)
    channel_username = Column(String(255), nullable=False)
    members = relationship("PrevMember", cascade="all, delete-orphan")


class PrevMember(BASE):
    __tablename__ = "autoban_prev_members"
    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(BigInteger, ForeignKey("autoban_channels.channel_id"))
    user_id = Column(BigInteger, nullable=False)   # Ganti dari username ke user_id


class BannedUser(BASE):
    __tablename__ = "autoban_banned_users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_username = Column(String(255), nullable=False)
    user_id = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("channel_username", "user_id", name="_channel_user_uc"),
    )


# ---------------- HELPER ---------------- #

def add_channel(channel_id, username):
    chan = AutoBanChannel(channel_id=channel_id, channel_username=username)
    SESSION.merge(chan)
    SESSION.commit()


def remove_channel(channel_id):
    chan = SESSION.query(AutoBanChannel).get(channel_id)
    if chan:
        SESSION.delete(chan)
        SESSION.commit()


def add_or_update_channel(channel_id, username, members_list):
    chan = AutoBanChannel(channel_id=channel_id, channel_username=username)
    SESSION.merge(chan)
    SESSION.commit()

    SESSION.query(PrevMember).filter(PrevMember.channel_id == channel_id).delete()
    for uid in members_list:
        SESSION.add(PrevMember(channel_id=channel_id, user_id=uid))
    SESSION.commit()


def get_all_channels():
    return SESSION.query(AutoBanChannel).all()


def get_prev_members(channel_id):
    q = SESSION.query(PrevMember).filter(PrevMember.channel_id == channel_id).all()
    return [m.user_id for m in q]


def add_banned_user(channel_username, user_id):
    user = BannedUser(channel_username=channel_username, user_id=user_id)
    SESSION.merge(user)
    SESSION.commit()


def get_banned_users():
    q = SESSION.query(BannedUser).all()
    return {(u.channel_username, u.user_id) for u in q}
