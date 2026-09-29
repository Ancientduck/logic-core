import sqlite3, os, re, time, shlex
from datetime import datetime, timedelta
from contextlib import closing

VALID_TYPES = ("episodic", "semantic", "procedural", "plan")
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "also", "am", "an", "and",
    "any", "are", "aren't", "arrive", "as", "ask", "asked", "at", "be", "because", "been",
    "before", "being", "below", "between", "both", "but", "by", "can", "can't", "cannot",
    "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "even", "few", "for", "from", "further", "get", "got", "had", "hadn't",
    "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll",
    "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "just",
    "know", "let", "like", "look", "looking", "looked", "make", "made", "many", "me", "might",
    "more", "most", "must", "my", "myself", "need", "no", "nor", "not", "now", "of", "off",
    "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over",
    "own", "please", "really", "said", "same", "say", "saying", "see", "seen", "shall",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "sure", "tell", "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've",
    "thing", "things", "think", "this", "those", "through", "to", "too", "told", "try",
    "trying", "under", "until", "up", "very", "want", "was", "wasn't", "we", "we'd", "we'll",
    "we're", "we've", "were", "weren't", "what", "what's", "when", "when's", "where",
    "where's", "which", "while", "who", "who's", "whom", "why", "why's", "will", "with",
    "won't", "would", "wouldn't", "yeah", "yes", "yet", "you", "you'd", "you'll", "you're",
    "you've", "your", "yours", "yourself", "yourselves"
}
CORE_THRESHOLD = 0.8
PASSIVE_INJECTION = True
DECAY_BELOW = 0.3
DECAY_DAYS = 30

WINDOW = 20
UBIQUITY_RATIO = 0.5
MIN_MEMORIES_FOR_UBIQUITY = 3

def _tokens(text):
    return [w for w in re.findall(r"[a-zA-Z0-9]+", text.lower())
            if len(w) > 2 and w not in STOPWORDS]

def _jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

def _is_consonant(w, i):
    c = w[i]
    if c in "aeiou":
        return False
    if c == "y":
        return True if i == 0 else not _is_consonant(w, i - 1)
    return True

def _measure(w):
    n = 0
    i = 0
    L = len(w)
    while i < L and _is_consonant(w, i):
        i += 1
    while i < L:
        while i < L and not _is_consonant(w, i):
            i += 1
        if i >= L:
            break
        n += 1
        while i < L and _is_consonant(w, i):
            i += 1
    return n

def _contains_vowel(w):
    return any(not _is_consonant(w, i) for i in range(len(w)))

def _ends_double_consonant(w):
    return len(w) >= 2 and w[-1] == w[-2] and _is_consonant(w, len(w) - 1)

def _cvc(w):
    if len(w) < 3:
        return False
    i = len(w) - 1
    if not (_is_consonant(w, i) and not _is_consonant(w, i - 1) and _is_consonant(w, i - 2)):
        return False
    return w[i] not in "wxy"

def _porter_stem(w):
    w = w.lower()
    if len(w) <= 2:
        return w
    if w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("ies"):
        w = w[:-2]
    elif w.endswith("ss"):
        pass
    elif w.endswith("s"):
        w = w[:-1]
    flag = False
    if w.endswith("eed"):
        if _measure(w[:-3]) > 0:
            w = w[:-1]
    elif w.endswith("ed") and _contains_vowel(w[:-2]):
        w = w[:-2]
        flag = True
    elif w.endswith("ing") and _contains_vowel(w[:-3]):
        w = w[:-3]
        flag = True
    if flag:
        if w.endswith(("at", "bl", "iz")):
            w += "e"
        elif _ends_double_consonant(w) and w[-1] not in "lsz":
            w = w[:-1]
        elif _measure(w) == 1 and _cvc(w):
            w += "e"
    if w.endswith("y") and _contains_vowel(w[:-1]):
        w = w[:-1] + "i"
    for suf, rep in (("ational", "ate"), ("tional", "tion"), ("enci", "ence"), ("anci", "ance"),
                     ("izer", "ize"), ("bli", "ble"), ("alli", "al"), ("entli", "ent"), ("eli", "e"),
                     ("ousli", "ous"), ("ization", "ize"), ("ation", "ate"), ("ator", "ate"),
                     ("alism", "al"), ("iveness", "ive"), ("fulness", "ful"), ("ousness", "ous"),
                     ("aliti", "al"), ("iviti", "ive"), ("biliti", "ble"), ("logi", "log")):
        if w.endswith(suf) and _measure(w[:-len(suf)]) > 0:
            w = w[:-len(suf)] + rep
            break
    for suf, rep in (("icate", "ic"), ("ative", ""), ("alize", "al"), ("iciti", "ic"),
                     ("ical", "ic"), ("ful", ""), ("ness", "")):
        if w.endswith(suf) and _measure(w[:-len(suf)]) > 0:
            w = w[:-len(suf)] + rep
            break
    for suf in ("al", "ance", "ence", "er", "ic", "able", "ible", "ant", "ement", "ment", "ent",
                "ion", "ou", "ism", "ate", "iti", "ous", "ive", "ize"):
        if w.endswith(suf):
            stem = w[:-len(suf)]
            if suf == "ion" and (not stem or stem[-1] not in "st"):
                continue
            if _measure(stem) > 1:
                w = stem
            break
    if w.endswith("e"):
        stem = w[:-1]
        m = _measure(stem)
        if m > 1 or (m == 1 and not _cvc(stem)):
            w = stem
    if w.endswith("ll") and _measure(w) > 1:
        w = w[:-1]
    return w

def _tokenize_pos(text):
    out = []
    for w in re.findall(r"[a-zA-Z0-9]+", text.lower()):
        if len(w) <= 2 or w in STOPWORDS:
            continue
        s = _porter_stem(w)
        if s:
            out.append(s)
    return out

def _query_tokens(text):
    out, seen = [], set()
    for t in _tokenize_pos(text):
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "memory", "memory.db")

class MemoryManager:
    def __init__(self, db_path=DEFAULT_DB_PATH):
        self.db_path = db_path
        self.sent_ids = set()
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

        with closing(self._conn()) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            self._init_schema(conn)
            self._migrate(conn)
            self._backfill_tokens(conn)
            self._purge(conn)

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _init_schema(self, conn):
        conn.execute("""CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            memory_type TEXT DEFAULT 'semantic',
            importance REAL DEFAULT 0.5,
            access_count INTEGER DEFAULT 0,
            expires_at TEXT,
            created_at TEXT DEFAULT (datetime('now')))""")
        conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(content, content='memories', content_rowid='id', tokenize='porter')""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
        END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content) VALUES ('delete', old.id, old.content);
        END""")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content) VALUES ('delete', old.id, old.content);
            INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
        END""")
        conn.execute("""CREATE TABLE IF NOT EXISTS memory_tokens (
            memory_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            token TEXT NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mt_token ON memory_tokens(token)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mt_mem ON memory_tokens(memory_id)")

    def _migrate(self, conn):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(memories)")}
        if "memory_type" not in cols:
            conn.execute("ALTER TABLE memories ADD COLUMN memory_type TEXT DEFAULT 'semantic'")
            conn.execute("ALTER TABLE memories ADD COLUMN importance REAL DEFAULT 0.5")
            conn.execute("ALTER TABLE memories ADD COLUMN access_count INTEGER DEFAULT 0")
            conn.execute("ALTER TABLE memories ADD COLUMN expires_at TEXT")
            conn.execute("UPDATE memories SET memory_type='episodic', importance=0.4")
            conn.execute("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')")
            print("[memory] migrated legacy rows -> episodic / context-tier")

    def _backfill_tokens(self, conn):
        have = {r[0] for r in conn.execute("SELECT DISTINCT memory_id FROM memory_tokens")}
        rows = conn.execute("SELECT id, content FROM memories").fetchall()
        added = 0
        for mid, content in rows:
            if mid in have:
                continue
            for pos, tok in enumerate(_tokenize_pos(content)):
                conn.execute("INSERT INTO memory_tokens(memory_id, position, token) VALUES (?,?,?)",
                             (mid, pos, tok))
            added += 1
        if added:
            print("[memory] tokenized " + str(added) + " memories")

    def _purge(self, conn):
        n1 = conn.execute("DELETE FROM memories WHERE expires_at IS NOT NULL AND date(expires_at) < date('now')").rowcount
        n2 = conn.execute("""DELETE FROM memories WHERE importance < ? AND access_count = 0
                             AND created_at < datetime('now', ?)""",
                          (DECAY_BELOW, "-" + str(DECAY_DAYS) + " days")).rowcount
        if n1 or n2:
            conn.execute("""DELETE FROM memory_tokens WHERE memory_id NOT IN
                            (SELECT id FROM memories)""")
            print("[memory] purged " + str(n1) + " expired, " + str(n2) + " decayed")

    def save(self, text, memory_type="semantic", importance=0.5, expires_days=None):
        text = text.strip()
        if not text:
            return ""
        if memory_type not in VALID_TYPES:
            return "Invalid type. Use: " + ", ".join(VALID_TYPES)
        importance = max(0.0, min(1.0, float(importance)))
        with closing(self._conn()) as conn, conn:
            dup = self._find_duplicate(conn, text)
            if dup:
                return "Rejected, near-duplicate of [" + str(dup[0]) + "]: " + dup[1][:60]
            exp = (datetime.now() + timedelta(days=float(expires_days))).isoformat() if expires_days else None
            cur = conn.execute("INSERT INTO memories (content, memory_type, importance, expires_at) VALUES (?,?,?,?)",
                               (text, memory_type, importance, exp))
            mid = cur.lastrowid
            for pos, tok in enumerate(_tokenize_pos(text)):
                conn.execute("INSERT INTO memory_tokens(memory_id, position, token) VALUES (?,?,?)",
                             (mid, pos, tok))
        return "Saved (" + memory_type + " | imp " + format(importance, ".1f") + "): " + text[:70]

    def _find_duplicate(self, conn, text, threshold=0.8):
        words = _tokens(text)
        if not words:
            return None
        q = " OR ".join('"' + w + '"' for w in words)
        try:
            rows = conn.execute("""SELECT memories.id, memories.content FROM memories_fts
                                   JOIN memories ON memories.id = memories_fts.rowid
                                   WHERE memories_fts MATCH ? LIMIT 8""", (q,)).fetchall()
        except sqlite3.OperationalError:
            return None
        for rid, content in rows:
            if _jaccard(words, _tokens(content)) >= threshold:
                return (rid, content)
        return None

    def delete(self, text):
        with closing(self._conn()) as conn, conn:
            ids = [r[0] for r in conn.execute("SELECT id FROM memories WHERE content LIKE ?",
                                              ("%" + text + "%",))]
            if ids:
                ph = ",".join("?" * len(ids))
                conn.execute("DELETE FROM memory_tokens WHERE memory_id IN (" + ph + ")", ids)
            cur = conn.execute("DELETE FROM memories WHERE content LIKE ?", ("%" + text + "%",))
        return "Deleted " + str(cur.rowcount) + " entries matching '" + text + "'"

    def search(self, query, limit=5, memory_type=None, min_importance=None):
        q_tokens = _query_tokens(query)
        if not q_tokens:
            return ""
        with closing(self._conn()) as conn, conn:
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            if total == 0:
                return ""
            ph = ",".join("?" * len(q_tokens))
            df = {t: c for t, c in conn.execute(
                "SELECT token, COUNT(DISTINCT memory_id) FROM memory_tokens "
                "WHERE token IN (" + ph + ") GROUP BY token", q_tokens).fetchall()}
            if total >= MIN_MEMORIES_FOR_UBIQUITY:
                meaningful = [t for t in q_tokens if 0 < df.get(t, 0) and df.get(t, 0) / total <= UBIQUITY_RATIO]
            else:
                meaningful = [t for t in q_tokens if df.get(t, 0) > 0]
            if not meaningful:
                return ""
            ph = ",".join("?" * len(meaningful))
            sql = ("SELECT DISTINCT mt.memory_id FROM memory_tokens mt "
                   "JOIN memories m ON m.id = mt.memory_id "
                   "WHERE mt.token IN (" + ph + ")")
            params = list(meaningful)
            if memory_type:
                sql += " AND m.memory_type = ?"
                params.append(memory_type)
            if min_importance is not None:
                sql += " AND m.importance >= ?"
                params.append(float(min_importance))
            cands = [r[0] for r in conn.execute(sql, params).fetchall()]
            if not cands:
                return ""
            ph2 = ",".join("?" * len(cands))
            rows = conn.execute("SELECT memory_id, token FROM memory_tokens WHERE memory_id IN ("
                                + ph2 + ") ORDER BY memory_id, position", cands).fetchall()
            streams = {}
            for mid, tok in rows:
                streams.setdefault(mid, []).append(tok)
            if len(meaningful) < 2 and df.get(meaningful[0], 0) != 1:
                return ""
            qset = set(meaningful)
            need = 2 if len(meaningful) >= 2 else 1
            scored = []
            for mid, toks in streams.items():
                distinct = {t for t in toks if t in qset}
                if len(distinct) < need:
                    continue
                best = 0
                for i in range(len(toks)):
                    win = {x for x in toks[i:i + WINDOW] if x in qset}
                    if len(win) > best:
                        best = len(win)
                        if best >= len(meaningful):
                            break
                if best < need:
                    continue
                scored.append((mid, best, len(distinct)))
            if not scored:
                return ""
            scored.sort(key=lambda x: (-x[1], -x[2]))
            picked, mark = [], []
            for mid, best, dist in scored:
                if mid in self.sent_ids:
                    continue
                picked.append((mid, best, dist))
                mark.append(mid)
                if len(picked) >= limit:
                    break
            if not picked:
                return ""
            idph = ",".join("?" * len(picked))
            info = {r[0]: r for r in conn.execute(
                "SELECT id, content, memory_type, importance FROM memories WHERE id IN ("
                + idph + ")", [p[0] for p in picked]).fetchall()}
            out = []
            for mid, best, dist in picked:
                row = info.get(mid)
                if not row:
                    continue
                _, content, mtype, imp = row
                out.append("[hit " + str(best) + "/" + str(len(meaningful)) + "] (" + mtype
                           + "|imp " + format(imp, ".1f") + ") " + content)
            conn.execute("UPDATE memories SET access_count = access_count + 1 WHERE id IN ("
                         + ",".join("?" * len(mark)) + ")", mark)
            self.sent_ids.update(mark)
        return out

    def get_core(self, limit=10, threshold=CORE_THRESHOLD):
        if not PASSIVE_INJECTION:
            return []
        with closing(self._conn()) as conn:
            rows = conn.execute("""SELECT memory_type, content FROM memories
                                   WHERE importance >= ?
                                   ORDER BY importance DESC, created_at DESC LIMIT ?""",
                                (threshold, limit)).fetchall()
        return ["(" + t + ") " + c for t, c in rows]

    def update(self, mid, importance=None, memory_type=None, expires_days=None, never_expires=False):
        sets, params = [], []
        if importance is not None:
            sets.append("importance=?")
            params.append(max(0.0, min(1.0, float(importance))))
        if memory_type:
            if memory_type not in VALID_TYPES:
                return "Invalid type."
            sets.append("memory_type=?")
            params.append(memory_type)
        if never_expires:
            sets.append("expires_at=NULL")
        elif expires_days is not None:
            sets.append("expires_at=?")
            params.append((datetime.now() + timedelta(days=float(expires_days))).isoformat())
        if not sets:
            return "Nothing to update."
        params.append(int(mid))
        with closing(self._conn()) as conn, conn:
            cur = conn.execute("UPDATE memories SET " + ", ".join(sets) + " WHERE id=?", params)
        return "Updated " + str(cur.rowcount) + " row(s)."

    def reset_sent(self):
        n = len(self.sent_ids)
        self.sent_ids.clear()
        return "Reset: " + str(n) + " memory ids cleared."

    def show_all(self):
        with closing(self._conn()) as conn:
            rows = conn.execute("""SELECT id, content, memory_type, importance, access_count,
                                          COALESCE(expires_at,'-'), created_at
                                   FROM memories ORDER BY importance DESC, created_at DESC""").fetchall()
        if not rows:
            return ["Memory is empty."]
        return ["[" + str(rid) + "] (" + t + "|imp " + format(imp, ".1f") + "|used " + str(ac)
                + "|exp " + exp + ") " + content
                for rid, content, t, imp, ac, exp, ts in rows]

    def stats(self):
        with closing(self._conn()) as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            by_type = conn.execute("SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type").fetchall()
            core = conn.execute("SELECT COUNT(*) FROM memories WHERE importance >= ?",
                                (CORE_THRESHOLD,)).fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM memory_tokens").fetchone()[0]
        lines = ["Total: " + str(total) + " | core (imp>=" + str(CORE_THRESHOLD) + "): " + str(core)
                 + " | tokens: " + str(chunks)]
        lines += ["  " + t + ": " + str(c) for t, c in by_type]
        return lines

def run_timed(label, func, *args):
    start = time.perf_counter()
    result = func(*args)
    elapsed = (time.perf_counter() - start) * 1000
    if isinstance(result, list):
        for line in result:
            print(line)
    elif result:
        print(result)
    print("--- " + label + " took " + format(elapsed, ".3f") + " ms ---")

def _parse_flags(arg):
    parts = shlex.split(arg)
    text, flags, i = [], {}, 0
    while i < len(parts):
        p = parts[i]
        if p == "--type" and i + 1 < len(parts):
            flags["memory_type"] = parts[i + 1]
            i += 2
        elif p == "--imp" and i + 1 < len(parts):
            flags["importance"] = float(parts[i + 1])
            i += 2
        elif p == "--exp" and i + 1 < len(parts):
            v = parts[i + 1]
            if v.lower() == "never":
                flags["never_expires"] = True
            elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                target = datetime.fromisoformat(v + "T23:59:59")
                flags["expires_days"] = max(0.0001, (target - datetime.now()).total_seconds() / 86400)
            else:
                flags["expires_days"] = float(v)
            i += 2
        elif p == "--min" and i + 1 < len(parts):
            flags["min_importance"] = float(parts[i + 1])
            i += 2
        else:
            text.append(p)
            i += 1
    return " ".join(text), flags

memorymanager = MemoryManager()

if __name__ == "__main__":
    mem = MemoryManager()
    print("Memory Manager v3 | save | delete | search | core | set <id> | stats | all | reset | exit")
    print("flags: --type episodic|semantic|procedural|plan  --imp 0.0-1.0  --exp <YYYY-MM-DD | days | never>  --min <float>")
    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw:
            continue
        parts = raw.split(" ", 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        if cmd == "exit":
            break
        elif cmd == "save" and arg:
            text, f = _parse_flags(arg)
            run_timed("save", mem.save, text, f.get("memory_type", "semantic"),
                      f.get("importance", 0.5), f.get("expires_days"))
        elif cmd == "delete" and arg:
            run_timed("delete", mem.delete, arg)
        elif cmd == "search" and arg:
            text, f = _parse_flags(arg)
            run_timed("search", mem.search, text, 5, f.get("memory_type"), f.get("min_importance"))
            mem.reset_sent()
        elif cmd == "core":
            run_timed("core", mem.get_core)
        elif cmd == "set" and arg:
            p2 = arg.split(" ", 1)
            _, flags = _parse_flags(p2[1] if len(p2) > 1 else "")
            run_timed("set", mem.update, int(p2[0]), flags.get("importance"),
                      flags.get("memory_type"), flags.get("expires_days"),
                      flags.get("never_expires", False))
        elif cmd == "stats":
            run_timed("stats", mem.stats)
        elif cmd == "reset":
            run_timed("reset_sent", mem.reset_sent)
        elif cmd == "all":
            run_timed("show_all", mem.show_all)
        else:
            print("Unknown command.")
