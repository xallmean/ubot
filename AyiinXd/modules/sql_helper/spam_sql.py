try:
    from AyiinXd.modules.sql_helper import BASE, SESSION
except ImportError:
    raise AttributeError("Gagal import SQL Helper")

from sqlalchemy import Column, String, Integer, BigInteger, Boolean, inspect, text
class SpamList(BASE):
    __tablename__ = "spam_list"
    name = Column(String, primary_key=True)
    type = Column(String)  # "biasa" atau "fw"
    content = Column(String)
    delay = Column(Integer)
    is_active = Column(Boolean, default=False)
    loop_count = Column(BigInteger, default=0)
    media = Column(LargeBinary, nullable=True)

class SpamGroup(BASE):
    __tablename__ = "spam_group"
    id = Column(Integer, primary_key=True)
    list_name = Column(String)
    group_username = Column(String)

BASE.metadata.create_all(bind=SESSION.get_bind())

def update_media(name, data):
    entry = SESSION.query(SpamList).get(name)
    entry.media = data
    SESSION.commit()
    
def get_loop(name):
    data = SESSION.query(SpamList).get(name)
    return data.loop_count if data else 0

def set_loop(name, value):
    data = SESSION.query(SpamList).get(name)
    if data:
        data.loop_count = value
        SESSION.commit()

def increment_loop(name):
    data = SESSION.query(SpamList).get(name)
    if data:
        data.loop_count += 1
        SESSION.commit()

def add_list(name, type, content, delay):
    data = SESSION.query(SpamList).filter_by(name=name).first()
    if data:
        data.type = type
        data.content = content
        data.delay = delay
    else:
        data = SpamList(name=name, type=type, content=content, delay=delay)
        SESSION.add(data)
    SESSION.commit()

def get_list(name):
    return SESSION.query(SpamList).filter_by(name=name).first()

def get_all_lists():
    return SESSION.query(SpamList).all()

def delete_list(name):
    SESSION.query(SpamList).filter_by(name=name).delete()
    SESSION.query(SpamGroup).filter_by(list_name=name).delete()
    SESSION.commit()

def add_groups_to_list(name, groups):
    for g in groups:
        if not SESSION.query(SpamGroup).filter_by(list_name=name, group_username=g).first():
            SESSION.add(SpamGroup(list_name=name, group_username=g))
    SESSION.commit()

def get_groups(name):
    return [g.group_username for g in SESSION.query(SpamGroup).filter_by(list_name=name).all()]

def delete_group(name, group):
    SESSION.query(SpamGroup).filter_by(list_name=name, group_username=group).delete()
    SESSION.commit()

def update_list(name, type, delay, content):
    data = SESSION.query(SpamList).filter_by(name=name).first()
    if data:
        data.type = type
        data.delay = delay
        data.content = content
        SESSION.commit()


def alter_table_if_needed():
    engine = SESSION.get_bind()
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns("spam_list")]

    with engine.connect() as conn:
        if "type" not in columns:
            conn.execute(text("ALTER TABLE spam_list ADD COLUMN type VARCHAR"))
        if "delay" not in columns:
            conn.execute(text("ALTER TABLE spam_list ADD COLUMN delay INTEGER"))
        if "content" not in columns:
            conn.execute(text("ALTER TABLE spam_list ADD COLUMN content TEXT"))
        if "is_active" not in columns:
            conn.execute(text("ALTER TABLE spam_list ADD COLUMN is_active BOOLEAN DEFAULT FALSE"))
        if "loop_count" not in columns:
            conn.execute(text("ALTER TABLE spam_list ADD COLUMN loop_count BIGINT DEFAULT 0"))
            
BASE.metadata.create_all(bind=SESSION.get_bind())
alter_table_if_needed()
BASE.metadata.create_all(bind=SESSION.get_bind())
alter_table_if_needed()
