from sqlalchemy import Column, String, Integer, Boolean, Text
from AyiinXd.modules.sql_helper import BASE, SESSION


class AutoKomen(BASE):
    __tablename__ = "auto_komen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String(100))          # @username channel
    trigger = Column(String(100))             # selalu lowercase
    reply = Column(Text)                      # isi teks komen
    msg_id = Column(Integer, default=None)    # mode reply (kalau dari pesan)
    msg_chat = Column(String(100), default=None)
    last_msg_id = Column(Integer, default=0)
    active = Column(Boolean, default=True)    # status aktif/nonaktif


BASE.metadata.create_all(bind=SESSION.bind)

# ===================================================================
# UTILS
# ===================================================================

def _clean_trigger(t):
    return t.lower().strip()

def _clean_channel(c):
    if not c.startswith("@"):
        return "@" + c
    return c.lower().strip()


# ===================================================================
# ADD FILTER / CHANNEL
# ===================================================================

def add_filter(channel_id, trigger):
    channel_id = _clean_channel(channel_id)
    trigger = _clean_trigger(trigger)

    exist = SESSION.query(AutoKomen).filter_by(
        channel_id=channel_id,
        trigger=trigger
    ).first()

    if not exist:
        data = AutoKomen(channel_id=channel_id, trigger=trigger)
        SESSION.add(data)
        SESSION.commit()


# ===================================================================
# SET REPLY
# ===================================================================

def set_reply(channel_id, trigger, reply=None, msg_id=None, msg_chat=None):
    channel_id = _clean_channel(channel_id)
    trigger = _clean_trigger(trigger)

    data = SESSION.query(AutoKomen).filter_by(
        channel_id=channel_id,
        trigger=trigger
    ).first()

    if data:
        data.reply = reply
        data.msg_id = msg_id
        data.msg_chat = msg_chat
        SESSION.commit()


# ===================================================================
# DELETE
# ===================================================================

def delete_trigger(channel_id, trigger):
    channel_id = _clean_channel(channel_id)
    trigger = _clean_trigger(trigger)
    SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).delete()
    SESSION.commit()


def delete_channel(channel_id):
    channel_id = _clean_channel(channel_id)
    SESSION.query(AutoKomen).filter_by(channel_id=channel_id).delete()
    SESSION.commit()


# ===================================================================
# GETTERS
# ===================================================================

def get_triggers(channel_id):
    channel_id = _clean_channel(channel_id)
    return SESSION.query(AutoKomen).filter_by(channel_id=channel_id, active=True).all()


def get_all_channels():
    rows = SESSION.query(AutoKomen.channel_id).distinct().all()
    return [(c[0]) for c in rows]


def get_all_komen():
    return SESSION.query(AutoKomen).all()


# ===================================================================
# UPDATE LAST MSG
# ===================================================================

def update_last_msg(channel_id, trigger, msg_id):
    channel_id = _clean_channel(channel_id)
    trigger = _clean_trigger(trigger)

    row = SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).first()
    if row:
        row.last_msg_id = msg_id
        SESSION.commit()


# ===================================================================
# ACTIVE / DEACTIVE
# ===================================================================

def deactivate_channel(channel_id):
    channel_id = _clean_channel(channel_id)
    SESSION.query(AutoKomen).filter_by(channel_id=channel_id).update({"active": False})
    SESSION.commit()


def activate_channel(channel_id):
    channel_id = _clean_channel(channel_id)
    SESSION.query(AutoKomen).filter_by(channel_id=channel_id).update({"active": True})
    SESSION.commit()


# ===================================================================
# BLOCKWORDS GLOBAL
# ===================================================================

def get_blockwords():
    try:
        with open("blockwords.txt", "r") as f:
            return [w.strip() for w in f.readlines() if w.strip()]
    except FileNotFoundError:
        return []


def add_blockwords_global(words):
    words = words.split()
    exist = set(get_blockwords())
    new_words = []

    for w in words:
        w = w.lower().strip()
        if w not in exist:
            new_words.append(w)

    with open("blockwords.txt", "a") as f:
        for w in new_words:
            f.write(w + "\n")

    return len(new_words)


def del_blockword_global(word):
    word = word.lower().strip()
    existing = get_blockwords()

    with open("blockwords.txt", "w") as f:
        for w in existing:
            if w != word:
                f.write(w + "\n")
