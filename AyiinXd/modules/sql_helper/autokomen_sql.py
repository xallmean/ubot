# modules/sql_helper/autokomen_sql.py

from sqlalchemy import Column, String, Text, Boolean, Integer, UniqueConstraint
from AyiinXd.modules.sql_helper import BASE, SESSION

# -------------------------------------
#              TABLE MAIN
# -------------------------------------
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


# -------------------------------------
#              BLOCKWORD TABLE
# -------------------------------------
class AutoKomenBlockWord(BASE):
    __tablename__ = "autokomen_blockword"

    channel_id = Column(String(100), primary_key=True)   # None → global
    word = Column(String(100), primary_key=True)


AutoKomen.__table__.create(checkfirst=True)
AutoKomenBlockWord.__table__.create(checkfirst=True)

# =====================================
#               FUNCTIONS
# =====================================

def add_filter(channel_id, trigger):
    row = SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).first()
    if not row:
        row = AutoKomen(channel_id=channel_id, trigger=trigger)
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


def get_all_komen():
    return SESSION.query(AutoKomen).all()


def update_last_msg(channel_id, trigger, last_id):
    row = SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).first()
    if row:
        row.last_msg_id = last_id
        SESSION.commit()


def delete_trigger(channel_id, trigger):
    SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).delete()
    SESSION.commit()


# ----------------- BLOCKWORD -----------------

def add_blockword(channel_id, word):
    SESSION.add(AutoKomenBlockWord(channel_id, word.lower()))
    SESSION.commit()


def del_blockword(channel_id, word):
    SESSION.query(AutoKomenBlockWord).filter_by(channel_id=channel_id, word=word.lower()).delete()
    SESSION.commit()


def get_blockwords(channel_id):
    rows = SESSION.query(AutoKomenBlockWord).filter_by(channel_id=channel_id).all()
    return [r.word for r in rows]


# GLOBAL blockword: gunakan channel_id = "global"
def add_blockword_global(word):
    SESSION.add(AutoKomenBlockWord("global", word.lower()))
    SESSION.commit()


def del_blockword_global(word):
    SESSION.query(AutoKomenBlockWord).filter_by(channel_id="global", word=word.lower()).delete()
    SESSION.commit()


def get_blockwords_global():
    return get_blockwords("global")
