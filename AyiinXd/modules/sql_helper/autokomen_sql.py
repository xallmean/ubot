# modules/sql_helper/autokomen_sql.py

from sqlalchemy import Column, String, Text, Boolean, Integer, UniqueConstraint
from AyiinXd.modules.sql_helper import BASE, SESSION

class AutoKomen(BASE):
    __tablename__ = "autokomen"
    channel_id = Column(String(100), primary_key=True)
    trigger = Column(String(100), primary_key=True)
    reply = Column(Text, nullable=True)
    msg_chat = Column(String(100), nullable=True)
    msg_id = Column(Integer, nullable=True)
    active = Column(Boolean, default=True)
    last_msg_id = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("channel_id", "trigger", name="autokomen_channel_trigger_uc"),
    )

    def __init__(self, channel_id, trigger, reply=None, msg_chat=None, msg_id=None):
        self.channel_id = channel_id
        self.trigger = trigger
        self.reply = reply
        self.msg_chat = msg_chat
        self.msg_id = msg_id


# ===== BLOCKWORD TABLE =====

class AutoKomenBlockWord(BASE):
    __tablename__ = "autokomen_blockword"
    # format:
    # channel_id = None → GLOBAL BLOCKWORD
    channel_id = Column(String(100), primary_key=True)
    word = Column(String(100), primary_key=True)

    def __init__(self, channel_id, word):
        self.channel_id = channel_id
        self.word = word


AutoKomen.__table__.create(checkfirst=True)
AutoKomenBlockWord.__table__.create(checkfirst=True)


# =============================
#           FUNCTIONS
# =============================

def add_filter(channel_id, trigger):
    row = SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).first()
    if not row:
        row = AutoKomen(channel_id, trigger)
        SESSION.add(row)
    SESSION.commit()


def set_reply(channel_id, trigger, reply=None, msg_chat=None, msg_id=None):
    row = SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).first()
    if row:
        row.reply = reply
        row.msg_chat = msg_chat
        row.msg_id = msg_id
        SESSION.commit()


def get_triggers(channel_id):
    return SESSION.query(AutoKomen).filter_by(channel_id=channel_id).all()


def update_last_msg(channel_id, trigger, last_id):
    row = SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).first()
    if row:
        row.last_msg_id = last_id
        SESSION.commit()


def delete_trigger(channel_id, trigger):
    SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).delete()
    SESSION.commit()


def delete_channel(channel_id):
    SESSION.query(AutoKomen).filter_by(channel_id=channel_id).delete()
    SESSION.commit()


def get_all_channels():
    rows = SESSION.query(AutoKomen.channel_id).distinct().all()
    return [r for r in rows]


def get_all_komen():
    return SESSION.query(AutoKomen).all()


def deactivate_channel(channel_id):
    rows = SESSION.query(AutoKomen).filter_by(channel_id=channel_id).all()
    for r in rows:
        r.active = False
    SESSION.commit()


def activate_channel(channel_id):
    rows = SESSION.query(AutoKomen).filter_by(channel_id=channel_id).all()
    for r in rows:
        r.active = True
    SESSION.commit()


# ============ BLOCKWORDS ============

def add_blockword(channel_id, word):
    row = AutoKomenBlockWord(channel_id, word.lower())
    SESSION.add(row)
    SESSION.commit()


def del_blockword(channel_id, word):
    SESSION.query(AutoKomenBlockWord).filter_by(channel_id=channel_id, word=word.lower()).delete()
    SESSION.commit()


def get_blockwords(channel_id):
    rows = SESSION.query(AutoKomenBlockWord).filter_by(channel_id=channel_id).all()
    return [r.word for r in rows]


# Global blockwords:
def add_blockwords_global(words):
    count = 0
    for w in words.split():
        row = AutoKomenBlockWord("global", w.lower())
        SESSION.add(row)
        count += 1
    SESSION.commit()
    return count


def get_blockwords_global():
    return get_blockwords("global")


def del_blockword_global(word):
    SESSION.query(AutoKomenBlockWord).filter_by(channel_id="global", word=word.lower()).delete()
    SESSION.commit()
