from sqlalchemy import Column, String, BigInteger, Integer, Boolean, ARRAY, inspect, text
from AyiinXd.modules.sql_helper import BASE, SESSION


class AutoKomen(BASE):
    __tablename__ = "auto_komen"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String, index=True)
    trigger = Column(String)
    reply = Column(String, nullable=True)
    msg_id = Column(BigInteger, nullable=True)
    msg_chat = Column(String, nullable=True)
    last_msg_id = Column(BigInteger, nullable=True)
    active = Column(Boolean, default=True)
    blockwords = Column(ARRAY(String), default=[])

    def __init__(self, channel_id, trigger, reply=None, msg_id=None, msg_chat=None):
        self.channel_id = channel_id
        self.trigger = trigger
        self.reply = reply
        self.msg_id = msg_id
        self.msg_chat = msg_chat


# --- AUTO MIGRATE ---
def auto_migrate():
    inspector = inspect(SESSION.bind)
    try:
        tables = inspector.get_table_names()
        if "auto_komen" not in tables:
            BASE.metadata.create_all(SESSION.bind)
            return

        columns = [col["name"] for col in inspector.get_columns("auto_komen")]
        if "active" not in columns:
            SESSION.execute(text("ALTER TABLE auto_komen ADD COLUMN active BOOLEAN DEFAULT TRUE"))
        if "blockwords" not in columns:
            SESSION.execute(text("ALTER TABLE auto_komen ADD COLUMN blockwords TEXT[] DEFAULT '{}'::text[]"))
        SESSION.commit()
    except Exception as e:
        print(f"[ERROR MIGRATE AUTOKOMEN] {e}")
        SESSION.rollback()


auto_migrate()


# --- FUNGSI AUTO KOMEN ---
def add_filter(channel_id, trigger):
    trigger = trigger.lower().strip()
    exist = SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).first()
    if not exist:
        data = AutoKomen(channel_id, trigger)
        SESSION.add(data)
        SESSION.commit()


def set_reply(channel_id, trigger, reply=None, msg_id=None, msg_chat=None):
    trigger = trigger.lower().strip()
    data = SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).first()
    if data:
        data.reply = reply
        data.msg_id = msg_id
        data.msg_chat = msg_chat
        SESSION.commit()


def update_last_msg(channel_id, trigger, last_id):
    data = SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).first()
    if data:
        data.last_msg_id = last_id
        SESSION.commit()


def get_triggers(channel_id):
    return SESSION.query(AutoKomen).filter_by(channel_id=channel_id).all()


def get_all_komen():
    return SESSION.query(AutoKomen).all()


def get_all_channels():
    return SESSION.query(AutoKomen.channel_id).distinct().all()


def delete_channel(channel_id):
    try:
        SESSION.query(AutoKomen).filter_by(channel_id=channel_id).delete()
        SESSION.commit()
    except Exception:
        SESSION.rollback()
        raise


def delete_trigger(channel_id, trigger):
    try:
        SESSION.query(AutoKomen).filter_by(channel_id=channel_id, trigger=trigger).delete()
        SESSION.commit()
    except Exception:
        SESSION.rollback()
        raise


# --- BLOCKWORDS GLOBAL ---
def add_blockwords_global(words):
    """
    Tambah banyak kata block sekaligus (dipisah spasi)
    Contoh: add_blockwords_global("sfs auto viu prem jaseb telegram")
    """
    try:
        word_list = [w.lower().strip() for w in words.split() if w.strip()]
        if not word_list:
            return 0

        rows = SESSION.query(AutoKomen).all()
        for row in rows:
            existing = set(row.blockwords or [])
            existing.update(word_list)
            row.blockwords = list(existing)

        SESSION.commit()
        return len(word_list)
    except Exception as e:
        print(f"[SQL] add_blockwords_global error: {e}")
        SESSION.rollback()
        return 0


def del_blockword_global(word):
    """Hapus satu kata block dari semua channel"""
    try:
        word = word.lower().strip()
        rows = SESSION.query(AutoKomen).all()
        for row in rows:
            if row.blockwords and word in row.blockwords:
                updated = [w for w in row.blockwords if w != word]
                row.blockwords = updated
        SESSION.commit()
    except Exception as e:
        print(f"[SQL] del_blockword_global error: {e}")
        SESSION.rollback()


def get_blockwords():
    """Ambil semua blockword global"""
    try:
        rows = SESSION.query(AutoKomen.blockwords).all()
        words = set()
        for row in rows:
            if row.blockwords:
                words.update([w.lower() for w in row.blockwords])
        return list(words)
    except Exception as e:
        print(f"[SQL] get_blockwords error: {e}")
        return []
