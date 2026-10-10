#!/usr/bin/env python3
"""Gate verifikasi UI modul geprekyukss_dashboard.

Jalankan dari mana saja:  python3 scripts/check_dashboard_ui.py
Exit code 0 = lulus, 1 = ada masalah.

Cek statis yang tidak bisa ditangkap Odoo saat build:
 1. 4 template XML well-formed.
 2. 2 file SCSS compile (libsass) + brace seimbang.
 3. class yang dipakai XML punya definisi CSS (atau hook selector di JS).
 4. class CSS tanpa rujukan XML/JS (CSS yatim).
 5. helper yang dipanggil template ada definisinya di JS.
 6. state.<key> di template ada di useState() komponen terkait. 7.  t-call menunjuk template yang benar-benar ada.
 8.  a11y: canvas / th scope / ikon / tooltip / tombol ikon-saja.
 9.  rantai cabang t-if/t-elif/t-else vs t-foreach (aturan asli Owl normalizeTIf).


Dependensi: libsass (`pip install libsass`). Tanpa libsass poin 2 dilewati
sebagai kegagalan.
"""
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO / "addons/geprekyukss_dashboard/static/src"
if not ROOT.exists():  # fallback bila dipanggil dari dalam addon
    ROOT = Path("static/src").resolve()
APP = ROOT / "app"
SCSS = ROOT / "scss"

XML_FILES = [
    APP / "dashboard/dashboard.xml",
    APP / "report/report_shell.xml",
    APP / "report/report_table.xml",
    APP / "report/report_matrix.xml",
]
SCSS_FILES = [SCSS / "dashboard.scss", SCSS / "report.scss"]
JS_FILES = sorted(APP.rglob("*.js"))

fails = []


def ok(msg):
    print(f"  OK   {msg}")


def bad(msg):
    fails.append(msg)
    print(f"  FAIL {msg}")


# ---------- 1. XML well-formed ----------
print("[1] XML well-formed")
for f in XML_FILES:
    if not f.exists():
        bad(f"{f.name}: tidak ditemukan")
        continue
    try:
        ET.parse(f)
        ok(f"{f.name}")
    except ET.ParseError as e:
        bad(f"{f.name}: {e}")

# ---------- 2. SCSS compile ----------
print("[2] SCSS compile (libsass)")
try:
    import sass
except ImportError:
    bad("libsass tidak tersedia")
    sass = None

compiled_css = {}
if sass:
    for f in SCSS_FILES:
        src = f.read_text()
        if src.count("{") != src.count("}"):
            bad(f"{f.name}: brace tidak seimbang {src.count('{')}/{src.count('}')}")
        try:
            css = sass.compile(filename=str(f))
        except Exception as e:  # noqa: BLE001
            bad(f"{f.name}: compile error {e}")
            continue
        compiled_css[f.name] = css
        ok(f"{f.name} → {len(css.splitlines())} baris CSS ({src.count('{')} blok)")

# ---------- kumpulkan class ----------
ATTR_RE = re.compile(r'(?:class|t-att-class)\s*=\s*"([^"]*)"')
# literal class di dalam ekspresi JS OWL: 'gk-badge ' + x
LIT_RE = re.compile(r"['\"]([^'\"]*)['\"]")

PREFIXES = set()  # literal class yang berakhir '-' → prefiks dinamis


def add_tokens(found, val):
    for lit in LIT_RE.findall(val):
        for tok in lit.split():
            if not tok.startswith("gk-"):
                continue
            if tok.endswith("-"):
                PREFIXES.add(tok)
            else:
                found.add(tok)


xml_classes = {}
for f in XML_FILES:
    if not f.exists():
        continue
    text = f.read_text()
    found = set()
    for m in ATTR_RE.finditer(text):
        val = m.group(1)
        if "'" in val or '"' in val or "?" in val or "+" in val or "{" in val:
            add_tokens(found, val)
            continue
        for tok in val.split():
            if tok.startswith("gk-"):
                found.add(tok)
    xml_classes[f.name] = found

js_classes = set()
for f in JS_FILES:
    for m in re.finditer(r"(?<![\w-])(\.?gk-[A-Za-z0-9_-]+)", f.read_text()):
        tok = m.group(1)
        if tok.endswith("-"):
            PREFIXES.add(tok)
        else:
            js_classes.add(tok.lstrip("."))

css_classes = set()
for css in compiled_css.values():
    css_classes |= set(re.findall(r"\.(gk-[A-Za-z0-9_-]+)", css))

xml_all = set()
for s in xml_classes.values():
    xml_all |= s
referenced = xml_all | js_classes

# ---------- 3. XML class tanpa CSS ----------
print("[3] class XML tanpa definisi CSS")
# class yang hanya jadi selector hook di JS (querySelector) tidak butuh CSS
missing = sorted((xml_all - js_classes) - css_classes)
if missing:
    bad("tanpa CSS: " + ", ".join(missing))
else:
    ok("semua class yang dipakai punya definisi CSS (atau hook JS)")

# ---------- 4. CSS class tanpa rujukan ----------
print("[4] class CSS tanpa rujukan (XML/JS)")
prefixed = {c for c in css_classes if any(c.startswith(p) for p in PREFIXES)}
renamed = prefixed | {c for c in css_classes if any(c.startswith(p) for p in ("gk-rtable-row-",))}
orphan = sorted((css_classes - referenced) - renamed)
if orphan:
    print(f"  WARN tidak dirujuk ({len(orphan)}): " + ", ".join(orphan))
else:
    ok("tidak ada class CSS yatim")

# ---------- 5. helper template ada di JS ----------
print("[5] helper template ↔ definisi JS")
EXPR_ATTRS = re.compile(r"t-(?:esc|out|if|elif|foreach|key|as|value|options|on-[\w.]+)\s*=\s*\"([^\"]*)\"")
CALL_RE = re.compile(r"(?<![\w.])([a-zA-Z_][\w]*)\(")
BUILTIN = {"formatRp", "formatSigned", "formatPct", "markup", "Number", "Math", "String"}
KEYWORDS = {"if", "for", "while", "return", "typeof", "function"}

tpl_calls = {}
for f in XML_FILES:
    if not f.exists():
        continue
    calls = set()
    for m in EXPR_ATTRS.finditer(f.read_text()):
        expr = m.group(1)
        for name in CALL_RE.findall(expr):
            if name in KEYWORDS:
                continue
            calls.add(name)
    tpl_calls[f.name] = calls

js_text = {f.name: f.read_text() for f in JS_FILES}
ALL_JS = "\n".join(js_text.values())
METHOD_RE = re.compile(r"^\s{4}(?:async\s+)?([a-zA-Z_][\w]*)\s*\(", re.M)
GETTER_RE = re.compile(r"^\s{4}get\s+([a-zA-Z_][\w]*)", re.M)
FUNC_RE = re.compile(r"^(?:export\s+)?function\s+([a-zA-Z_][\w]*)", re.M)
defined = set(METHOD_RE.findall(ALL_JS)) | set(GETTER_RE.findall(ALL_JS)) | set(FUNC_RE.findall(ALL_JS))
defined |= {"write"}  # OWL internals yang bisa muncul di t-on-*
# import dari modul lain (nama lokal setelah 'as')
for grp in re.findall(r"import\s*\{([^}]*)\}", ALL_JS):
    for item in grp.split(","):
        item = item.strip()
        if item:
            defined.add(item.split(" as ")[-1].strip())
default_imports = re.findall(r"^import\s+([a-zA-Z_][\w]*)\s+from", ALL_JS, re.M)
defined |= set(default_imports)

for name, calls in tpl_calls.items():
    unknown = sorted(c for c in calls if c not in defined and c not in BUILTIN)
    if unknown:
        bad(f"{name}: helper tanpa definisi JS → {', '.join(unknown)}")
    else:
        ok(f"{name}: {len(calls)} helper terverifikasi")

# ---------- 6. state.<key> ada di JS ----------
print("[6] state.<key> di template")
STATE_RE = re.compile(r"state\.([a-zA-Z_][\w]*)")
PAIRS = [
    (APP / "dashboard/dashboard.xml", APP / "dashboard/dashboard.js"),
    (APP / "report/report_shell.xml", APP / "report/report_shell.js"),
    (APP / "report/report_table.xml", APP / "report/report_table.js"),
    (APP / "report/report_matrix.xml", APP / "report/report_matrix.js"),
]
def state_keys(src):
    """Ambil key tingkat-1 dari objek pertama useState({ ... })."""
    i = src.find("useState({")
    if i < 0:
        return None
    j = src.index("{", i)
    depth = 0
    end = j
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                end = k
                break
    body = src[j + 1:end]
    keys, depth = set(), 0
    for line in body.splitlines():
        stripped = re.sub(r"//.*", "", line)
        if depth == 0:
            m = re.match(r"\s*([a-zA-Z_][\w]*)\s*:", stripped)
            if m:
                keys.add(m.group(1))
        depth += stripped.count("{") + stripped.count("[") - stripped.count("}") - stripped.count("]")
    return keys


for tpl, js in PAIRS:
    if not (tpl.exists() and js.exists()):
        continue
    keys = state_keys(js.read_text())
    if keys is None:
        print(f"  SKIP {tpl.name}: useState() tidak terdeteksi")
        continue
    used = set(STATE_RE.findall(tpl.read_text()))
    unknown = sorted(used - keys)
    if unknown:
        bad(f"{tpl.name}: state key tak ada di JS → {', '.join(unknown)}")
    else:
        ok(f"{tpl.name}: {len(used)} state key cocok")

# ---------- 7. t-call template ada ----------
print("[7] t-call template terdefinisi")
defined_tpl = set()
for f in XML_FILES:
    if f.exists():
        defined_tpl |= set(re.findall(r't-name="([^"]+)"', f.read_text()))
for f in XML_FILES:
    if not f.exists():
        continue
    called = set(re.findall(r't-call="([^"]+)"', f.read_text()))
    unknown = sorted(c for c in called if c not in defined_tpl)
    if unknown:
        bad(f"{f.name}: t-call tanpa template → {', '.join(unknown)}")
    else:
        ok(f"{f.name}: {len(called)} t-call valid")

# ---------- 8. A11Y ----------
print("[8] a11y (aria / focus / fokus keyboard)")
ICON_ONLY_BTN = re.compile(
    r"<button([^>]*)>\s*(?:<i[^>]*/>|[‹›✕⟲])\s*</button>", re.S)
for f in XML_FILES:
    if not f.exists():
        continue
    text = f.read_text()
    problems = []

    # 8a. Setiap <canvas> harus punya role="img" + aria-label
    for tag in re.findall(r"<canvas[^>]*>", text):
        if 'role="img"' not in tag or "aria-label" not in tag:
            problems.append(f"canvas tanpa role/aria-label: {tag[:60]}")

    # 8b. Setiap <th> harus punya scope
    for tag in re.findall(r"<th\b[^>]*>", text):
        if "scope=" not in tag:
            problems.append(f"th tanpa scope: {tag[:60]}")

    # 8c. Ikon FontAwesome dekoratif harus aria-hidden
    for tag in re.findall(r'<i class="fa [^"]*"\s*/>', text):
        if "aria-hidden" not in tag:
            problems.append(f"ikon tanpa aria-hidden: {tag[:60]}")

    # 8d. Tooltip harus bisa dijangkau keyboard
    for tag in re.findall(r'<span class="gk-tip"[^>]*>', text):
        if "tabindex" not in tag:
            problems.append(f"tooltip tanpa tabindex: {tag[:60]}")

    # 8e. Tombol ikon-saja (label hanya ikon/simbol) harus punya nama aksesibel
    for attrs in ICON_ONLY_BTN.findall(text):
        if "aria-label" not in attrs and "title" not in attrs:
            problems.append(f"tombol tanpa nama aksesibel: <button{attrs[:60]}>")

    if problems:
        bad(f"{f.name}: {len(problems)} temuan a11y")
        for p in problems[:8]:
            print(f"        · {p}")
    else:
        ok(f"{f.name}: aria/focus lengkap")

# ---------- 9. Owl — t-foreach vs rantai cabang t-if/t-elif/t-else ----------
# Aturan ASLI normalizeTIf (dibaca langsung dari bundle Test1, bukan tebakan):
#   for node in el.querySelectorAll("[t-elif], [t-else]"):
#       prev = node.previousElementSibling
#       if prev && (prev["t-if"] || prev["t-elif"]):
#           if prev["t-foreach"]:  -> OwlError "t-if cannot stay at the same
#                                     level as t-foreach when using t-elif/t-else"
# Yang dilarang BUKAN "t-if + t-foreach sebaris" — itu legal dan dipakai luas
# di template core Odoo (mis. web.ListView, mail.AttachmentPanel). Yang dilarang:
# cabang t-elif/t-else yang didahului tepat elemen t-if/t-elif BER-t-foreach.
# Perbaikannya: bungkus cabangnya, loop turun satu level:
#   <t t-if="kondisi">
#       <t t-foreach="items" t-as="it" t-key="it.id">…</t>
#   </t>
#   <t t-else="">
#       <t t-foreach="lain()" t-as="it" t-key="it.id">…</t>
#   </t>
print("[9] Owl — t-foreach vs rantai cabang t-if/t-elif/t-else")
# start tag (bukan closing/komentar/decl), quote-aware agar '>' di nilai aman
START_TAG_RE = re.compile(r"<(?![!?/])([A-Za-z][\w.:-]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>")
ATTR_VALUE_RE = re.compile(r'"[^"]*"|\'[^\']*\'')
BRANCH_ATTRS = ("t-if", "t-elif", "t-else")


def has_tpl_attr(attrs, name):
    """True bila `name` dipakai sebagai nama atribut (isi nilai diabaikan)."""
    names = ATTR_VALUE_RE.sub(" ", attrs)
    return re.search(rf"(?<![\w-]){re.escape(name)}(?:\s*=|[\s]|$)", names) is not None


TPL_FLAGS = ("t-if", "t-elif", "t-else", "t-foreach")
CLOSE_TAG_RE = re.compile(r"</\s*[A-Za-z][\w.:-]*\s*>")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def _neutralize_comments(text):
    """Komentar → spasi (baris dipertahankan) agar isinya tidak dibaca sebagai tag."""
    return COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _attr_flags(attrs):
    """Set direktif Owl yang ada pada satu tag (hanya 4 nama ini yang relevan)."""
    return {name for name in TPL_FLAGS if has_tpl_attr(attrs, name)}


def iter_elements(text):
    """Telusuri elemen → dict(baris, name, flags, prev).

    `prev` = previousElementSibling ala Owl: elemen terakhir pada daftar anak
    yang sama (teks & komentar dilewati; tag penutup memundurkan posisi).
    """
    text = _neutralize_comments(text)
    events = [(m.start(), False, m) for m in START_TAG_RE.finditer(text)]
    events += [(m.start(), True, m) for m in CLOSE_TAG_RE.finditer(text)]
    events.sort(key=lambda e: e[0])
    stack = [[]]
    for _pos, is_close, m in events:
        if is_close:
            if len(stack) > 1:
                stack.pop()
            continue
        el = {
            "line": text.count("\n", 0, m.start()) + 1,
            "name": m.group(1),
            "flags": _attr_flags(m.group(2) or ""),
            "prev": stack[-1][-1] if stack[-1] else None,
        }
        stack[-1].append(el)
        if not m.group(0).rstrip().endswith("/>"):
            stack.append([])
        yield el


def owl_branch_conflicts(text):
    """Pelanggaran rantai cabang Owl → [(baris, nama tag, alasan)].

    Dua aturan dari normalizeTIf (keduanya menggagalkan compile):
      1. sibling sebelum t-elif/t-else memakai t-if/t-elif + t-foreach;
      2. satu node memuat lebih dari satu direktif t-if/t-elif/t-else.
    """
    out = []
    for el in iter_elements(text):
        flags = el["flags"]
        if not flags & {"t-elif", "t-else"}:
            continue
        prev = el["prev"]
        if not prev or not prev["flags"] & {"t-if", "t-elif"}:
            continue
        if "t-foreach" in prev["flags"]:
            out.append((el["line"], el["name"],
                        "sibling sebelumnya <{0}> memakai t-if/t-elif + t-foreach".format(prev["name"])))
        branches = flags & set(BRANCH_ATTRS)
        if len(branches) > 1:
            out.append((el["line"], el["name"],
                        "lebih dari satu direktif cabang: {0}".format(", ".join(sorted(branches)))))
    return out


for f in XML_FILES:
    if not f.exists():
        continue
    conflicts = owl_branch_conflicts(f.read_text())
    if conflicts:
        detail = "; ".join(f"baris {ln} <{tag}>: {why}" for ln, tag, why in conflicts)
        bad(f"{f.name}: {len(conflicts)} pelanggaran cabang Owl → {detail}")
    else:
        ok(f"{f.name}: rantai cabang t-if/t-elif/t-else aman")

print()
if fails:
    print(f"HASIL: {len(fails)} masalah")
    sys.exit(1)
print("HASIL: SEMUA GATE LULUS")
