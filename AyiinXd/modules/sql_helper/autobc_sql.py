from sqlalchemy import Column, Integer, Boolean, String, BigInteger, PickleType
from AyiinXd.modules.sql_helper import BASE, SESSION

# =============================
# MODELS
# =============================
class AutoBC(BASE):
    __tablename__ = "autobc"
    id = Column(Integer, primary_key=True)
    delay = Column(Integer, default=60)
    is_active = Column(Boolean, default=False)
    last_chat_id = Column(BigInteger, nullable=True)
    last_msg_id = Column(BigInteger, nullable=True)
    is_media = Column(Boolean, default=False)
    mode = Column(String(16), default="Basic")  # "send" or "fw"
    blacklist = Column(PickleType, default=list)

class AutoFW(BASE):
    __tablename__ = "autofw"
    id = Column(Integer, primary_key=True)
    delay = Column(Integer)
    chat_id = Column(String)  # string supaya aman, bisa username atau id
    msg_id = Column(Integer)
    is_active = Column(Boolean, default=False)

BASE.metadata.create_all(SESSION.bind)

# =============================
# AUTOBC HELPERS
# =============================
def get_autobc():
    return SESSION.query(AutoBC).first()

def add_or_update_autobc(delay, chat_id, msg_id, is_media, mode="send"):
    data = get_autobc()
    if not data:
        data = AutoBC(
            delay=delay,
            last_chat_id=int(chat_id),
            last_msg_id=int(msg_id),
            is_media=is_media,
            mode=mode,
            is_active=True
        )
        SESSION.add(data)
    else:
        data.delay = delay
        data.last_chat_id = int(chat_id)
        data.last_msg_id = int(msg_id)
        data.is_media = is_media
        data.mode = mode
        data.is_active = True
    SESSION.commit()
    return data

# =============================
# BLACKLIST HELPERS
# =============================
def add_blacklist(gid):
    data = get_autobc()
    if not data:
        data = AutoBC()
        SESSION.add(data)
    bl = set(map(int, data.blacklist or []))
    bl.add(int(gid))
    data.blacklist = list(bl)
    SESSION.commit()

def remove_blacklist(gid):
    data = get_autobc()
    if not data or not data.blacklist:
        return
    bl = set(map(int, data.blacklist))
    bl.discard(int(gid))
    data.blacklist = list(bl)
    SESSION.commit()

def get_blacklist():
    data = get_autobc()
    if data and data.blacklist:
        return [int(x) for x in data.blacklist]
    return []

# =============================
# STOP/DELETE HELPERS
# =============================
def stop_autobc():
    data = get_autobc()
    if data:
        data.is_active = False
        SESSION.commit()

def delete_autobc():
    data = get_autobc()
    if data:
        SESSION.delete(data)
        SESSION.commit()

# =============================
# AUTOFW HELPERS
# =============================
def add_autofw(delay, chat_id, msg_id):
    # Hapus record lama supaya cuma ada 1 autofw
    SESSION.query(AutoFW).delete()
    data = AutoFW(
        delay=delay,
        chat_id=str(chat_id),  # aman, string
        msg_id=int(msg_id),
        is_active=True
    )
    SESSION.add(data)
    SESSION.commit()
    return data

def get_autofw():
    return SESSION.query(AutoFW).first()

def stop_autofw():
    data = get_autofw()
    if data:
        data.is_active = False
        SESSION.commit()

def delete_autofw():
    SESSION.query(AutoFW).delete()
    SESSION.commit()
