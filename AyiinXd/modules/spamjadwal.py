# spamjadwal.py
# Single-file spamjadwal with PostgreSQL + autoresume + repeat
import os
import asyncio
from datetime import datetime, timedelta
import pytz
import asyncpg

from AyiinXd.ayiin import ayiin_cmd
from AyiinXd import CMD_HANDLER as cmd, CMD_HELP, BOTLOG_CHATID, LOOP
from telethon.errors.rpcerrorlist import FloodWaitError
from telethon.utils import get_display_name

# ----------------- Config -----------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL environment variable for PostgreSQL")

# Map zona -> tz name
ZONA_MAP = {
    "WIB": "Asia/Jakarta",
    "WITA": "Asia/Makassar",
    "WIT": "Asia/Jayapura",
}

# Active running tasks per list
ACTIVE_SPAM = {}  # name -> [asyncio.Task, ...]

# ----------------- DB helpers -----------------
async def pg_connect():
    return await asyncpg.connect(DATABASE_URL)

async def ensure_tables():
    conn = await pg_connect()
    # spam lists / groups
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS spam_list (
            name TEXT PRIMARY KEY
        );
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS spam_groups (
            id SERIAL PRIMARY KEY,
            list_name TEXT NOT NULL REFERENCES spam_list(name) ON DELETE CASCADE,
            group_username TEXT NOT NULL
        );
    """)
    # user tz
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_timezone (
            user_id TEXT PRIMARY KEY,
            timezone TEXT NOT NULL
        );
    """)
    # schedules: stop_time stored as timestamptz (UTC)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS spam_schedules (
            id SERIAL PRIMARY KEY,
            list_name TEXT NOT NULL,
            mode TEXT NOT NULL, -- "unspam" or "unfw"
            delay INTEGER NOT NULL,
            stop_time TIMESTAMPTZ NOT NULL,
            text TEXT,
            link TEXT,
            is_repeat BOOLEAN DEFAULT FALSE,
            start_time TEXT, -- "HH:MM" or NULL (for repeat)
            user_id TEXT
        );
    """)
    await conn.close()

# group/list helpers
async def add_group_to_list(namalist: str, group: str):
    conn = await pg_connect()
    await conn.execute("INSERT INTO spam_list(name) VALUES($1) ON CONFLICT DO NOTHING", namalist)
    await conn.execute("INSERT INTO spam_groups(list_name, group_username) VALUES($1, $2)", namalist, group)
    await conn.close()

async def remove_group_from_list(namalist: str, group: str):
    conn = await pg_connect()
    await conn.execute("DELETE FROM spam_groups WHERE list_name=$1 AND group_username=$2", namalist, group)
    # delete list if empty
    count = await conn.fetchval("SELECT COUNT(*) FROM spam_groups WHERE list_name=$1", namalist)
    if count == 0:
        await conn.execute("DELETE FROM spam_list WHERE name=$1", namalist)
    await conn.close()

async def get_groups_by_list(namalist: str):
    conn = await pg_connect()
    rows = await conn.fetch("SELECT group_username FROM spam_groups WHERE list_name=$1", namalist)
    await conn.close()
    return [r["group_username"] for r in rows] if rows else []

async def get_all_lists():
    conn = await pg_connect()
    rows = await conn.fetch("SELECT name FROM spam_list")
    await conn.close()
    return [type("ListObj", (object,), {"name": r["name"]})() for r in rows]

async def remove_list(namalist: str):
    conn = await pg_connect()
    await conn.execute("DELETE FROM spam_groups WHERE list_name=$1", namalist)
    await conn.execute("DELETE FROM spam_list WHERE name=$1", namalist)
    await conn.close()

# timezone
async def set_user_timezone(user_id: str, timezone: str):
    conn = await pg_connect()
    await conn.execute("""
        INSERT INTO user_timezone(user_id, timezone) VALUES($1, $2)
        ON CONFLICT (user_id) DO UPDATE SET timezone = EXCLUDED.timezone
    """, user_id, timezone)
    await conn.close()

async def get_user_timezone(user_id: str):
    conn = await pg_connect()
    row = await conn.fetchrow("SELECT timezone FROM user_timezone WHERE user_id=$1", user_id)
    await conn.close()
    return row["timezone"] if row else None

# schedule helpers
async def add_schedule(list_name: str, mode: str, delay: int, stop_time_utc: datetime,
                       text: str = None, link: str = None, is_repeat: bool = False,
                       start_time: str = None, user_id: str = None):
    """stop_time_utc must be timezone-aware UTC datetime"""
    if stop_time_utc.tzinfo is None:
        # assume UTC if naive
        stop_time_utc = stop_time_utc.replace(tzinfo=pytz.utc)
    conn = await pg_connect()
    await conn.execute("""
        INSERT INTO spam_schedules(list_name, mode, delay, stop_time, text, link, is_repeat, start_time, user_id)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
    """, list_name, mode, delay, stop_time_utc, text, link, is_repeat, start_time, user_id)
    await conn.close()

async def get_active_schedules():
    conn = await pg_connect()
    rows = await conn.fetch("SELECT * FROM spam_schedules")
    await conn.close()
    # asyncpg returns stop_time as datetime with tzinfo if timestamptz used
    return [dict(r) for r in rows]

async def get_schedules_for_list(list_name: str):
    conn = await pg_connect()
    rows = await conn.fetch("SELECT * FROM spam_schedules WHERE list_name=$1", list_name)
    await conn.close()
    return [dict(r) for r in rows]

async def delete_schedule_by_id(sid: int):
    conn = await pg_connect()
    await conn.execute("DELETE FROM spam_schedules WHERE id=$1", sid)
    await conn.close()

async def delete_nonrepeat(list_name: str, mode: str):
    conn = await pg_connect()
    await conn.execute("DELETE FROM spam_schedules WHERE list_name=$1 AND mode=$2 AND is_repeat=false", list_name, mode)
    await conn.close()

async def remove_schedules_by_list(list_name: str):
    conn = await pg_connect()
    await conn.execute("DELETE FROM spam_schedules WHERE list_name=$1", list_name)
    await conn.close()

# ----------------- Time helpers -----------------
def parse_hhmm(s: str):
    return datetime.strptime(s, "%H:%M").time()

def get_tz_for_user(user_id: str):
    """Return tz object and zona code (WIB/WITA/WIT). Caller must await get_user_timezone"""
    # helper wrapper used by commands below (they await DB)
    raise RuntimeError("Use await get_user_tz(user_id) instead")

async def get_user_tz(user_id: str):
    zona_input = await get_user_timezone(user_id) or "WIB"
    tzname = ZONA_MAP.get(zona_input, "Asia/Jakarta")
    return pytz.timezone(tzname), zona_input

def ensure_aware(dt: datetime, tz):
    if dt.tzinfo is None:
        return tz.localize(dt)
    return dt.astimezone(tz)

# ----------------- Command implementations -----------------

@ayiin_cmd(pattern=f"szone(?:\\s+|$)(.*)")
async def cmd_szone(event):
    zona_input = event.pattern_match.group(1).strip().upper()
    if zona_input not in ZONA_MAP:
        return await event.reply("Zona gak valid. Pilih: WIB, WITA, WIT")
    await set_user_timezone(str(event.sender_id), zona_input)
    await event.reply(f"Zona waktu berhasil di-set ke {zona_input}.")

@ayiin_cmd(pattern=r"sgrup\s+(\S+)\s+(.+)")
async def cmd_sgrup(event):
    namalist = event.pattern_match.group(1)
    raw = event.pattern_match.group(2).split()
    success, failed = [], []
    for item in raw:
        g = item.strip()
        if g.startswith("https://t.me/"):
            suffix = g.split("https://t.me/")[-1].strip("/")
            # if joinchat etc we'll just store suffix as handle (user intended)
            if suffix.startswith("joinchat") or suffix.startswith("+"):
                failed.append(f"{g} ➜ unsupported joinchat in this command. Please convert to @username or use client to join first.")
                continue
            g = f"@{suffix}"
        elif not g.startswith("@"):
            g = f"@{g}"
        try:
            await event.client.get_entity(g)
            await add_group_to_list(namalist, g)
            success.append(g)
        except Exception as e:
            failed.append(f"{g} ➜ {e}")
    msg = ""
    if success:
        msg += "✅ Grup berhasil ditambahkan ke `{}`:\n{}".format(namalist, "\n".join(success))
    if failed:
        msg += ("\n\n❌ Gagal:\n" + "\n".join(failed)) if msg else ("❌ Gagal:\n" + "\n".join(failed))
    await event.reply(msg)

@ayiin_cmd(pattern=f"dgrup(?:\\s+)(.*)")
async def cmd_dgrup(event):
    args = event.pattern_match.group(1).split()
    if len(args) < 2:
        return await event.reply(f"Format salah! {cmd}dgrup <namalist> <@grup1> [@grup2 ...]")
    namalist = args[0]
    groups = args[1:]
    for g in groups:
        await remove_group_from_list(namalist, g)
    await event.reply(f"Berhasil menghapus grup dari list {namalist}:\n" + "\n".join(groups))

@ayiin_cmd(pattern=f"nspam(?:\\s*)$")
async def cmd_nspam(event):
    lists = await get_all_lists()
    if not lists:
        return await event.reply("Tidak ada nama list spam yang disetting.")
    teks = "Nama list spam dan grup yang terdaftar:\n\n"
    for l in lists:
        teks += f"- Nama List : {l.name}\n"
        groups = await get_groups_by_list(l.name)
        teks += f"  • List Grup : {' '.join(groups) if groups else '-'}\n\n"
    await event.reply(teks.strip())

@ayiin_cmd(pattern=f"rlist(?:\\s+)(.*)")
async def cmd_rlist(event):
    namalist = event.pattern_match.group(1).strip()
    if not namalist:
        return await event.reply(f"Format salah! {cmd}rlist <namalist>")
    await remove_list(namalist)
    await event.reply(f"Nama list {namalist} dan grupnya berhasil dihapus.")

# unspam: text or reply media; pattern accepts trailing text (maybe empty)
@ayiin_cmd(pattern=r"unspam\s+(\d{1,2}:\d{2})\s+(\d+)\s+(\S+)\s*([\s\S]*)")
async def cmd_unspam(event):
    jam_henti = event.pattern_match.group(1)
    delay = int(event.pattern_match.group(2))
    namalist = event.pattern_match.group(3)
    teks = event.pattern_match.group(4).strip() or None

    tz, zona_code = await get_user_tz(str(event.sender_id))
    now = datetime.now(tz)

    try:
        jam_stop_local = datetime.combine(now.date(), parse_hhmm(jam_henti))
        jam_stop_local = ensure_aware(jam_stop_local, tz)
        if jam_stop_local < now:
            jam_stop_local += timedelta(days=1)
    except Exception:
        return await event.reply("Format jam salah! Contoh: 12:30")

    groups = await get_groups_by_list(namalist)
    if not groups:
        return await event.reply(f"List `{namalist}` kosong atau tidak ditemukan.")

    reply_msg = await event.get_reply_message()
    if not teks and not reply_msg:
        return await event.reply("Kamu harus kirim teks atau reply ke media!")

    # save schedule for autoresume (non-repeat)
    await add_schedule(namalist, "unspam", delay, jam_stop_local.astimezone(pytz.utc),
                       text=teks, link=None, is_repeat=False, start_time=None, user_id=str(event.sender_id))

    await event.reply(f"🚀 Mulai spam ke list `{namalist}` dengan delay {delay}s. Stop jam {jam_henti} ({zona_code})")

    async def spam_task():
        counter = 0
        while True:
            now_local = datetime.now(tz)
            if now_local >= jam_stop_local:
                # remove non-repeat schedule(s) for this list/mode
                await delete_nonrepeat(namalist, "unspam")
                if BOTLOG_CHATID:
                    log_msg = (
                        f"**SPAM SELESAI**\n\n"
                        f"Nama List : `{namalist}`\n"
                        f"Waktu Berhenti : `{jam_henti} ({zona_code})`\n"
                        f"Total Pesan : `{counter}`\n"
                    )
                    if teks:
                        log_msg += f"\nTeks :\n{teks}"
                    await event.client.send_message(BOTLOG_CHATID, log_msg)
                break

            sukses, gagal, alasan = [], [], []
            for group in groups:
                try:
                    if reply_msg:
                        if teks:
                            await reply_msg.copy_to(group, caption=teks, parse_mode="Markdown")
                        else:
                            await reply_msg.copy_to(group)
                    else:
                        await event.client.send_message(group, teks, parse_mode="Markdown", link_preview=False)
                    sukses.append(group)
                    counter += 1
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                    gagal.append(group)
                    alasan.append(f"- {group} : FloodWait {e.seconds}s")
                except Exception as e:
                    gagal.append(group)
                    alasan.append(f"- {group} : {str(e).split(':')[0]}")

            if BOTLOG_CHATID:
                jenis = "Media + Caption" if reply_msg else "Teks"
                status_msg = (
                    f"**⎋ Spam Jadwal Info :**\n"
                    f"    Status : {'Berhasil ✓' if sukses else 'Gagal ✘'}\n"
                    f"    Jenis : {jenis}\n"
                    f"    Grup : {', '.join(sukses) if sukses else '-'}\n"
                    f"    List : {namalist}\n"
                )
                if gagal:
                    status_msg += (
                        f"\n    Status : Gagal ✘\n"
                        f"    Grup : {', '.join(gagal)}\n"
                        f"    Alasan :\n" + "\n".join(alasan)
                    )
                await event.client.send_message(BOTLOG_CHATID, status_msg)

            await asyncio.sleep(delay)

    t = asyncio.create_task(spam_task())
    ACTIVE_SPAM.setdefault(namalist, []).append(t)

# unfw: forward a specific message
@ayiin_cmd(pattern=f"unfw(?:\\s+)(.*)")
async def cmd_unfw(event):
    args = event.pattern_match.group(1).split(" ", 3)
    if len(args) < 4:
        return await event.reply(f"Format salah!\nGunakan:\n`{cmd}unfw <jam_berhenti> <delay> <namalist> <link pesan channel>`")
    jam_henti, delay, namalist, link = args[0], int(args[1]), args[2], args[3]

    tz, zona_code = await get_user_tz(str(event.sender_id))
    now = datetime.now(tz)
    try:
        jam_stop_local = datetime.combine(now.date(), parse_hhmm(jam_henti))
        jam_stop_local = ensure_aware(jam_stop_local, tz)
        if jam_stop_local < now:
            jam_stop_local += timedelta(days=1)
    except Exception:
        return await event.reply("Format jam salah, harus HH:MM")

    groups = await get_groups_by_list(namalist)
    if not groups:
        return await event.reply(f"List `{namalist}` kosong atau tidak ditemukan.")

    try:
        if "t.me/" not in link:
            raise ValueError("Link harus berupa https://t.me/username/123")
        parts = link.split("/")
        if len(parts) < 5:
            raise ValueError("Format link salah, harus https://t.me/channel/1234")
        channel_username = parts[3]
        message_id = int(parts[4])
        message = await event.client.get_messages(channel_username, ids=message_id)
    except Exception as e:
        return await event.reply(f"Gagal ambil pesan dari link: {e}")

    # save schedule
    await add_schedule(namalist, "unfw", delay, jam_stop_local.astimezone(pytz.utc),
                       text=None, link=link, is_repeat=False, start_time=None, user_id=str(event.sender_id))

    await event.reply(f"🚀 Mulai spam forward ke grup list `{namalist}` setiap {delay}s. Stop jam {jam_henti} ({zona_code})")

    async def fw_task():
        counter = 0
        while True:
            now_local = datetime.now(tz)
            if now_local >= jam_stop_local:
                await delete_nonrepeat(namalist, "unfw")
                if BOTLOG_CHATID:
                    log_msg = (
                        f"**SPAM FORWARD SELESAI**\n\n"
                        f"Nama List : `{namalist}`\n"
                        f"Waktu Berhenti : `{jam_henti} ({zona_code})`\n"
                        f"Total Pesan : `{counter}`\n"
                        f"Link : {link}"
                    )
                    await event.client.send_message(BOTLOG_CHATID, log_msg)
                break

            sukses, gagal, alasan = [], [], []
            tasks = [event.client.forward_messages(g, message) for g in groups]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for idx, result in enumerate(results):
                group = groups[idx]
                if isinstance(result, Exception):
                    gagal.append(group)
                    alasan.append(f"- {group} : {str(result).split(':')[0]}")
                else:
                    sukses.append(group)
                    counter += 1

            if BOTLOG_CHATID:
                jenis = "Forward"
                status_msg = (
                    f"**⎋ Spam Jadwal Info :**\n"
                    f"    Status : {'Berhasil ✓' if sukses else 'Gagal ✘'}\n"
                    f"    Jenis : {jenis}\n"
                    f"    Grup : {', '.join(sukses) if sukses else '-'}\n"
                    f"    List : {namalist}\n"
                )
                if gagal:
                    status_msg += (
                        f"\n    Status : Gagal ✘\n"
                        f"    Grup : {', '.join(gagal)}\n"
                        f"    Alasan :\n" + "\n".join(alasan)
                    )
                await event.client.send_message(BOTLOG_CHATID, status_msg)

            await asyncio.sleep(delay)

    t = asyncio.create_task(fw_task())
    ACTIVE_SPAM.setdefault(namalist, []).append(t)

# repeat command: create daily repeat based on last non-repeat schedule for that list
@ayiin_cmd(pattern=r"respam\s+(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})\s+(\S+)")
async def cmd_repeat(event):
    start = event.pattern_match.group(1)
    stop = event.pattern_match.group(2)
    namalist = event.pattern_match.group(3)

    schedules = await get_schedules_for_list(namalist)
    if not schedules:
        return await event.reply("Tidak ada schedule sebelumnya untuk list ini. Jalankan `.unspam` atau `.unfw` dulu untuk menyimpan konfigurasi.")

    tmpl = None
    for s in schedules:
        if not s["is_repeat"]:
            tmpl = s
            break
    if not tmpl:
        return await event.reply("Tidak menemukan schedule valid untuk dijadikan template repeat.")

    # compute stop_time as today at stop time in user's tz, then store UTC
    tz, zona_code = await get_user_tz(str(event.sender_id))
    now = datetime.now(tz)
    stop_local = datetime.combine(now.date(), parse_hhmm(stop))
    stop_local = ensure_aware(stop_local, tz)
    if stop_local < now:
        stop_local += timedelta(days=1)

    await add_schedule(namalist, tmpl["mode"], tmpl["delay"], stop_local.astimezone(pytz.utc),
                       text=tmpl["text"], link=tmpl["link"], is_repeat=True, start_time=start, user_id=str(event.sender_id))
    await event.reply(f"✅ Repeat harian untuk `{namalist}` diset. Akan mulai tiap hari jam {start} dan berhenti jam {stop}.")

@ayiin_cmd(pattern=f"dnspam(?:\\s+)(.*)")
async def cmd_dnspam(event):
    namalist = event.pattern_match.group(1).strip()
    if not namalist:
        return await event.reply(f"Format salah! {cmd}dnspam <namalist>")
    # cancel tasks
    tasks = ACTIVE_SPAM.get(namalist, [])
    for t in tasks:
        try:
            t.cancel()
        except Exception:
            pass
    ACTIVE_SPAM.pop(namalist, None)
    # remove schedules and list
    await remove_schedules_by_list(namalist)
    await remove_list(namalist)
    await event.reply(f"Berhasil menghentikan semua spam dan menghapus list `{namalist}`.")

# ----------------- Schedule manager (autoresume + repeat) -----------------
async def start_schedule_manager(client):
    """
    Call this once after bot is ready (client available).
    It ensures DB tables, spawns tasks for stored schedules (autoresume),
    and runs a background monitor for repeat schedules.
    """
    await ensure_tables()

    async def spawn_schedule(row):
        # row is dict from DB
        list_name = row["list_name"]
        mode = row["mode"]
        delay = row["delay"]
        stop_time = row["stop_time"]  # asyncpg should return aware datetime (tzinfo)
        text = row["text"]
        link = row["link"]
        is_repeat = row["is_repeat"]
        start_time = row["start_time"]
        user_id = row["user_id"]
        # convert stop_time to aware UTC
        if stop_time.tzinfo is None:
            stop_time = stop_time.replace(tzinfo=pytz.utc)
        stop_dt_utc = stop_time.astimezone(pytz.utc)

        if mode == "unspam":
            async def resume_unspam():
                tz, zona_code = await get_user_tz(user_id or "")
                counter = 0
                # if repeat: manage start/stop window locally
                while True:
                    now_local = datetime.now(tz)
                    # stop condition for non-repeat (compare now in UTC >= stop_dt_utc)
                    if not is_repeat and datetime.now(pytz.utc) >= stop_dt_utc:
                        await delete_nonrepeat(list_name, "unspam")
                        break
                    # for repeat: check daily start/stop window
                    if is_repeat and start_time:
                        st_local = ensure_aware(datetime.combine(now_local.date(), parse_hhmm(start_time)), tz)
                        stp_local = stop_dt_utc.astimezone(tz)
                        if not (st_local <= now_local <= stp_local):
                            await asyncio.sleep(30)
                            continue
                    # run sending (text-only; can't reconstruct original reply media reliably)
                    groups = await get_groups_by_list(list_name)
                    if not groups:
                        await asyncio.sleep(60)
                        continue
                    sukses, gagal, alasan = [], [], []
                    for g in groups:
                        try:
                            if text:
                                await client.send_message(g, text, parse_mode="Markdown", link_preview=False)
                            counter += 1
                            sukses.append(g)
                        except Exception as e:
                            gagal.append(g)
                            alasan.append(f"- {g} : {str(e).split(':')[0]}")
                    # log
                    if BOTLOG_CHATID:
                        jenis = "Repeat (unspam)" if is_repeat else "Resume (unspam)"
                        status_msg = (
                            f"**⎋ Spam Jadwal Info :**\n"
                            f"    Status : {'Berhasil ✓' if sukses else 'Gagal ✘'}\n"
                            f"    Jenis : {jenis}\n"
                            f"    Grup : {', '.join(sukses) if sukses else '-'}\n"
                            f"    List : {list_name}\n"
                        )
                        if gagal:
                            status_msg += (
                                f"\n    Status : Gagal ✘\n"
                                f"    Grup : {', '.join(gagal)}\n"
                                f"    Alasan :\n" + "\n".join(alasan)
                            )
                        await client.send_message(BOTLOG_CHATID, status_msg)
                    await asyncio.sleep(delay)
            t = asyncio.create_task(resume_unspam())
            ACTIVE_SPAM.setdefault(list_name, []).append(t)

        elif mode == "unfw":
            async def resume_unfw():
                tz, zona_code = await get_user_tz(user_id or "")
                # reconstruct message object from link
                try:
                    if not link:
                        return
                    parts = link.split("/")
                    channel_username = parts[3]
                    message_id = int(parts[4])
                    message = await client.get_messages(channel_username, ids=message_id)
                except Exception:
                    return
                counter = 0
                while True:
                    now_local = datetime.now(tz)
                    if not is_repeat and datetime.now(pytz.utc) >= stop_dt_utc:
                        await delete_nonrepeat(list_name, "unfw")
                        break
                    if is_repeat and start_time:
                        st_local = ensure_aware(datetime.combine(now_local.date(), parse_hhmm(start_time)), tz)
                        stp_local = stop_dt_utc.astimezone(tz)
                        if not (st_local <= now_local <= stp_local):
                            await asyncio.sleep(30)
                            continue
                    groups = await get_groups_by_list(list_name)
                    if not groups:
                        await asyncio.sleep(60)
                        continue
                    sukses, gagal, alasan = [], [], []
                    tasks = [client.forward_messages(g, message) for g in groups]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for idx, res in enumerate(results):
                        g = groups[idx]
                        if isinstance(res, Exception):
                            gagal.append(g)
                            alasan.append(f"- {g} : {str(res).split(':')[0]}")
                        else:
                            sukses.append(g)
                            counter += 1
                    if BOTLOG_CHATID:
                        jenis = "Repeat (unfw)" if is_repeat else "Resume (unfw)"
                        status_msg = (
                            f"**⎋ Spam Jadwal Info :**\n"
                            f"    Status : {'Berhasil ✓' if sukses else 'Gagal ✘'}\n"
                            f"    Jenis : {jenis}\n"
                            f"    Grup : {', '.join(sukses) if sukses else '-'}\n"
                            f"    List : {list_name}\n"
                        )
                        if gagal:
                            status_msg += (
                                f"\n    Status : Gagal ✘\n"
                                f"    Grup : {', '.join(gagal)}\n"
                                f"    Alasan :\n" + "\n".join(alasan)
                            )
                        await client.send_message(BOTLOG_CHATID, status_msg)
                    await asyncio.sleep(delay)
            t = asyncio.create_task(resume_unfw())
            ACTIVE_SPAM.setdefault(list_name, []).append(t)

    # load active schedules and spawn if needed
    rows = await get_active_schedules()
    for row in rows:
        stop_time = row["stop_time"]
        # spawn if is_repeat or stop_time in future
        if row["is_repeat"] or stop_time > datetime.now(pytz.utc):
            await spawn_schedule(row)

    # background monitor for repeat schedules (minute loop)
    async def monitor_repeat():
        while True:
            rows = await get_active_schedules()
            for row in rows:
                if not row["is_repeat"]:
                    continue
                list_name = row["list_name"]
                # if already active, skip
                if ACTIVE_SPAM.get(list_name):
                    continue
                tz, zona_code = await get_user_tz(row["user_id"] or "")
                now_local = datetime.now(tz)
                start_time = row["start_time"]
                if not start_time:
                    # always spawn repeat if not already active
                    await spawn_schedule(row)
                else:
                    st_local = ensure_aware(datetime.combine(now_local.date(), parse_hhmm(start_time)), tz)
                    stp_local = row["stop_time"].astimezone(tz)
                    if st_local <= now_local <= stp_local:
                        await spawn_schedule(row)
            await asyncio.sleep(60)
    LOOP.create_task(monitor_repeat())


CMD_HELP.update({
    "spamjadwal": f"""
╭┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
│   **Plugin : spamjadwal**
│
│  »  **Perintah :** `{cmd}szone <WIB/WITA/WIT>`
│  »  **Kegunaan :** Menyetel zona waktu lokal kamu (default: WIB)
│
│  »  **Perintah :** `{cmd}sgrup <namalist> <@grup1> [@grup2]`
│  »  **Kegunaan :** Menambahkan banyak grup ke dalam satu list spam.
│
│  »  **Perintah :** `{cmd}dgrup <namalist> <@grup1> [@grup2]`
│  »  **Kegunaan :** Menghapus grup tertentu dari list.
│
│  »  **Perintah :** `{cmd}rlist <namalist>`
│  »  **Kegunaan :** Menghapus list dan semua grup di dalamnya.
│
│  »  **Perintah :** `{cmd}nspam`
│  »  **Kegunaan :** Menampilkan semua list dan grup yang tersimpan.
│
│  »  **Perintah :** `{cmd}dbspam`
│  »  **Kegunaan :** Menampilkan spam yang sedang berjalan.
│
│  »  **Perintah :** `{cmd}unspam <jam_henti> <delay> <namalist> <teks>`
│  »  **Kegunaan :** Spam teks (atau reply media) ke semua grup di list.
│
│  »  **Perintah :** `{cmd}unfw <jam_henti> <delay> <namalist> <link pesan>`
│  »  **Kegunaan :** Spam forward pesan dari channel ke semua grup di list.
│
│  »  **Perintah :** `{cmd}respam <jam_mulai> <jam_henti> <namalist>`
│  »  **Kegunaan :** Menjadwalkan spam agar otomatis jalan tiap hari.
│
│  »  **Perintah :** `{cmd}dnspam <namalist>`
│  »  **Kegunaan :** Menghentikan semua spam & repeat untuk list tersebut.
│
│  •  **NOTE :**
│     - Gunakan format jam 24 jam (contoh: `06:00`, `22:30`)
│     - Delay dalam detik (angka)
│     - Bisa kirim media (gunakan reply)
│     - Support zona waktu WIB / WITA / WIT
│     - Auto resume setelah restart
│     - Auto repeat sesuai jam yang diset
╰┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
"""
})
# ----------------- END -----------------
# NOTE:
# After importing this module you MUST call `await ensure_tables()` once (or call
# start_schedule_manager(client) after bot is ready) so DB tables exist and schedule manager starts.
#
# Example (in __main__.py after client is ready):
#   LOOP.run_until_complete(spamjadwal.ensure_tables())
#   LOOP.create_task(spamjadwal.start_schedule_manager(bot))
#
# Or if you prefer synchronous call:
#   LOOP.run_until_complete(spamjadwal.start_schedule_manager(bot))
#
# The module provides all commands and will resume or repeat schedules saved in DB.
