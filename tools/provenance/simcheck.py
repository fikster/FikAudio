#!/usr/bin/env python3
"""Token-based source similarity checker for C/C++ (MOSS/JPlag style).

Usage:
  python3 -I simcheck.py --ours FILE... --theirs FILE... [--label NAME]
                         [--k 12 20] [--w 4] [--json OUT] [--show-runs N]

Pass 1 (normalised): comments, preprocessor lines removed; identifiers -> ID,
numeric/string/char literals -> LIT; keywords and operators kept. k-gram hashes
are winnowed (window w) into fingerprints. Per (ours, theirs) file pair it
reports
  fp%    fraction of our fingerprints that also occur among theirs (MOSS style)
  cov%   fraction of our tokens covered by some k-gram that occurs anywhere in
         theirs (stricter-to-fool coverage measure)
  LCR    longest common normalised token run, with line ranges on both sides.

Pass 2 (raw): shared distinctive identifiers, shared comment word 6-grams,
shared unusual numeric constants.

The script only reads the files it is given; it never runs or builds them.
"""
import argparse
import hashlib
import json
import os
import re
import sys

KEYWORDS = set("""
alignas alignof and and_eq asm auto bitand bitor bool break case catch char
char8_t char16_t char32_t class compl concept const consteval constexpr
constinit const_cast continue co_await co_return co_yield decltype default
delete do double dynamic_cast else enum explicit export extern false float for
friend goto if inline int long mutable namespace new noexcept not not_eq
nullptr operator or or_eq private protected public register reinterpret_cast
requires return short signed sizeof static static_assert static_cast struct
switch template this thread_local throw true try typedef typeid typename union
unsigned using virtual void volatile wchar_t while xor xor_eq override final
NULL
""".split())

OPS = sorted("""
>>= <<= <=> ->* ... :: -> ++ -- << >> <= >= == != && || += -= *= /= %= &= |= ^= .*
+ - * / % & | ^ ~ ! = < > ? : ; , . ( ) [ ] { } #
""".split(), key=len, reverse=True)

TOKEN_RE = re.compile(
    r"""(?P<ws>\s+)
      |(?P<str>[uUL]?R?"(?:\\.|[^"\\\n])*")
      |(?P<chr>[uUL]?'(?:\\.|[^'\\\n])+')
      |(?P<num>(?:0[xX][0-9a-fA-F']+|(?:\d[\d']*\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)[uUlLfF]*)
      |(?P<id>[A-Za-z_]\w*)
      |(?P<op>""" + "|".join(re.escape(o) for o in OPS) + r""")
      |(?P<other>.)""",
    re.X | re.S,
)


def strip_comments(src):
    """Return (code_with_comments_blanked, list of (line, comment_text)).
    Newlines are preserved so line numbers stay valid. Strings are respected."""
    out = []
    comments = []
    i, n, line = 0, len(src), 1
    while i < n:
        c = src[i]
        if c == '"' or c == "'":
            q = c
            j = i + 1
            while j < n and src[j] != q and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(src[i:j])
            i = j
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            comments.append((line, src[i + 2:j]))
            out.append(" ")
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            body = src[i + 2:j - 2]
            comments.append((line, body))
            nl = body.count("\n")
            out.append(" " + "\n" * nl)
            line += nl
            i = j
        else:
            if c == "\n":
                line += 1
            out.append(c)
            i += 1
    return "".join(out), comments


def strip_preprocessor(code):
    lines = code.split("\n")
    res = []
    cont = False
    for ln in lines:
        if cont or ln.lstrip().startswith("#"):
            cont = ln.rstrip().endswith("\\")
            res.append("")
        else:
            res.append(ln)
    return "\n".join(res)


def tokenize(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    code, comments = strip_comments(src)
    code = strip_preprocessor(code)
    toks = []  # (normalised, raw, line)
    line = 1
    for m in TOKEN_RE.finditer(code):
        kind = m.lastgroup
        text = m.group()
        if kind == "ws":
            line += text.count("\n")
            continue
        if kind in ("str", "chr", "num"):
            norm = "LIT"
        elif kind == "id":
            norm = text if text in KEYWORDS else "ID"
        else:
            norm = text
        toks.append((norm, text, line, kind))
    return toks, comments


def khashes(norm, k):
    hs = []
    for i in range(len(norm) - k + 1):
        h = hashlib.blake2b("\x1f".join(norm[i:i + k]).encode(), digest_size=8).digest()
        hs.append(int.from_bytes(h, "big"))
    return hs


def winnow(hs, w):
    """Standard winnowing: in each window of w hashes pick the minimum
    (rightmost on ties). Returns set of (hash, pos)."""
    fps = set()
    if not hs:
        return fps
    if len(hs) < w:
        m = min(range(len(hs)), key=lambda i: (hs[i], -i))
        return {(hs[m], m)}
    for s in range(len(hs) - w + 1):
        win = hs[s:s + w]
        best = min(range(w), key=lambda i: (win[i], -i))
        fps.add((win[best], s + best))
    return fps


def longest_common_run(a, b, seed=6):
    """Longest common contiguous run of normalised tokens a[i:i+L]==b[j:j+L].
    Seeds on shared `seed`-grams and extends both ways."""
    if len(a) < seed or len(b) < seed:
        return 0, 0, 0
    index = {}
    for j in range(len(b) - seed + 1):
        index.setdefault(tuple(b[j:j + seed]), []).append(j)
    best = (0, 0, 0)
    for i in range(len(a) - seed + 1):
        for j in index.get(tuple(a[i:i + seed]), ()):  # noqa
            if i > 0 and j > 0 and a[i - 1] == b[j - 1]:
                continue  # not the start of a maximal run on this diagonal
            s_i, s_j = i, j
            while s_i > 0 and s_j > 0 and a[s_i - 1] == b[s_j - 1]:
                s_i -= 1
                s_j -= 1
            e = 0
            while s_i + e < len(a) and s_j + e < len(b) and a[s_i + e] == b[s_j + e]:
                e += 1
            if e > best[0]:
                best = (e, s_i, s_j)
    return best


def all_common_runs(a, b, minlen, seed=6):
    """All maximal common runs >= minlen (diagonal-deduplicated)."""
    runs = {}
    if len(a) < seed or len(b) < seed:
        return []
    index = {}
    for j in range(len(b) - seed + 1):
        index.setdefault(tuple(b[j:j + seed]), []).append(j)
    for i in range(len(a) - seed + 1):
        for j in index.get(tuple(a[i:i + seed]), ()):  # noqa
            s_i, s_j = i, j
            while s_i > 0 and s_j > 0 and a[s_i - 1] == b[s_j - 1]:
                s_i -= 1
                s_j -= 1
            key = (s_i, s_j)
            if key in runs:
                continue
            e = 0
            while s_i + e < len(a) and s_j + e < len(b) and a[s_i + e] == b[s_j + e]:
                e += 1
            if e >= minlen:
                runs[key] = e
    return sorted(((L, i, j) for (i, j), L in runs.items()), reverse=True)


class Doc:
    def __init__(self, path):
        self.path = path
        self.toks, self.comments = tokenize(path)
        self.norm = [t[0] for t in self.toks]
        self.lines = [t[2] for t in self.toks]
        self._k = {}

    def kdata(self, k, w):
        if (k, w) not in self._k:
            hs = khashes(self.norm, k)
            self._k[(k, w)] = (hs, set(hs), winnow(hs, w))
        return self._k[(k, w)]

    def span(self, start, length):
        if length == 0:
            return "-"
        return "%d-%d" % (self.lines[start], self.lines[start + length - 1])


def compare(ours, theirs, k, w):
    o_hs, _, o_fp = ours.kdata(k, w)
    t_hs, t_set, t_fp = theirs.kdata(k, w)
    t_fph = {h for h, _ in t_fp}
    fp_frac = (sum(1 for h, _ in o_fp if h in t_fph) / len(o_fp)) if o_fp else 0.0
    covered = [False] * len(ours.norm)
    for i, h in enumerate(o_hs):
        if h in t_set:
            for x in range(i, i + k):
                covered[x] = True
    cov = sum(covered) / len(covered) if covered else 0.0
    return fp_frac, cov


# ---------- pass 2 ----------
COMMON_IDS = set("""
i j k n x y a b c s t h m p q r v e f l w out in buf data size len length
std math cmath sqrt cos sin pow exp log floor fabs abs min max fmod M_PI
printf fprintf memset memcpy malloc free vector resize begin end fill copy
""".split())


def identifiers(doc):
    return {t[1] for t in doc.toks if t[3] == "id" and t[1] not in KEYWORDS}


def numbers(doc):
    out = {}
    for t in doc.toks:
        if t[3] == "num":
            s = t[1].rstrip("uUlLfF").replace("'", "")
            try:
                v = float(int(s, 16)) if s.lower().startswith("0x") else float(s)
            except ValueError:
                continue
            out.setdefault(v, []).append(t[2])
    return out


def boring_number(v):
    if v in (0.0, 0.5, 0.25, 0.75, 1.5, 0.1, 0.01, 0.001, 1e-3, 1e-6, 10.0, 100.0, 1000.0):
        return True
    if v == int(v) and abs(v) <= 64:
        return True
    if v > 0 and v == int(v) and (int(v) & (int(v) - 1)) == 0:
        return True  # powers of two
    return False


def comment_ngrams(doc, n=6):
    grams = {}
    for line, text in doc.comments:
        words = re.findall(r"[a-z0-9]+", text.lower())
        for i in range(len(words) - n + 1):
            grams.setdefault(" ".join(words[i:i + n]), line)
    return grams


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ours", nargs="+", required=True)
    ap.add_argument("--theirs", nargs="+", required=True)
    ap.add_argument("--label", default="theirs")
    ap.add_argument("--k", nargs="+", type=int, default=[12, 20])
    ap.add_argument("--w", type=int, default=4)
    ap.add_argument("--min-pair-tokens", type=int, default=0)
    ap.add_argument("--show-runs", type=int, default=0,
                    help="list the N longest common runs (normalised) per our file")
    ap.add_argument("--run-min", type=int, default=12)
    ap.add_argument("--stop-ids-from", nargs="*", default=[],
                    help="files whose identifiers count as generic for pass 2")
    ap.add_argument("--raw", action="store_true", help="run pass 2")
    ap.add_argument("--show-covered", type=int, default=0,
                    help="list our regions covered by k-grams (this k) found in theirs")
    ap.add_argument("--json")
    a = ap.parse_args()

    ours = [Doc(p) for p in a.ours]
    theirs = [Doc(p) for p in a.theirs if os.path.getsize(p) > 0]
    theirs = [d for d in theirs if len(d.norm) >= a.min_pair_tokens]
    results = []
    print("== %s ==" % a.label)
    hdr = "%-26s %-26s %6s" % ("ours", "theirs", "toks")
    for k in a.k:
        hdr += "  fp%%k%-3d cov%%k%-3d" % (k, k)
    hdr += "   LCR  ours-lines  their-lines"
    print(hdr)
    for o in ours:
        best_for_o = None
        for t in theirs:
            row = {"ours": o.path, "theirs": t.path, "ours_tokens": len(o.norm)}
            line = "%-26s %-26s %6d" % (os.path.basename(o.path)[:26], os.path.basename(t.path)[:26], len(o.norm))
            for k in a.k:
                fp, cov = compare(o, t, k, a.w)
                row["fp_k%d" % k] = fp
                row["cov_k%d" % k] = cov
                line += "  %7.1f %8.1f" % (100 * fp, 100 * cov)
            L, i, j = longest_common_run(o.norm, t.norm)
            row.update(lcr=L, ours_lines=o.span(i, L), theirs_lines=t.span(j, L))
            line += "  %4d  %-10s  %-10s" % (L, o.span(i, L), t.span(j, L))
            print(line)
            results.append(row)
            if best_for_o is None or L > best_for_o[0]:
                best_for_o = (L, t)
        # aggregate: our file against all of theirs together
        agg = {}
        for k in a.k:
            cov_all = [False] * len(o.norm)
            fp_hit = set()
            o_hs, _, o_fp = o.kdata(k, a.w)
            for t in theirs:
                _, t_set, t_fp = t.kdata(k, a.w)
                t_fph = {h for h, _ in t_fp}
                for i, h in enumerate(o_hs):
                    if h in t_set:
                        for x in range(i, i + k):
                            cov_all[x] = True
                fp_hit |= {(h, p) for h, p in o_fp if h in t_fph}
            agg[k] = (len(fp_hit) / len(o_fp) if o_fp else 0.0,
                      sum(cov_all) / len(cov_all) if cov_all else 0.0)
        line = "%-26s %-26s %6d" % (os.path.basename(o.path)[:26], "*ALL*", len(o.norm))
        for k in a.k:
            line += "  %7.1f %8.1f" % (100 * agg[k][0], 100 * agg[k][1])
        print(line)
        results.append({"ours": o.path, "theirs": "*ALL*",
                        **{"fp_k%d" % k: agg[k][0] for k in a.k},
                        **{"cov_k%d" % k: agg[k][1] for k in a.k}})
        if a.show_runs:
            allruns = []
            for t in theirs:
                for L, i, j in all_common_runs(o.norm, t.norm, a.run_min):
                    allruns.append((L, i, j, t))
            allruns.sort(key=lambda r: -r[0])
            # keep runs that don't overlap an already listed one on our side
            used = []
            shown = 0
            for L, i, j, t in allruns:
                if any(not (i + L <= u0 or i >= u1) for u0, u1 in used):
                    continue
                used.append((i, i + L))
                print("    run %3d tok  ours %s:%s  theirs %s:%s" % (
                    L, os.path.basename(o.path), o.span(i, L), os.path.basename(t.path), t.span(j, L)))
                print("        ours  : " + " ".join(x[1] for x in o.toks[i:i + L]))
                shown += 1
                if shown >= a.show_runs:
                    break

    if a.show_covered:
        k = a.show_covered
        print("\n-- regions of ours covered by %d-grams present in theirs --" % k)
        for o in ours:
            o_hs, _, _ = o.kdata(k, a.w)
            src = {}
            for t in theirs:
                _, t_set, _ = t.kdata(k, a.w)
                for i, h in enumerate(o_hs):
                    if h in t_set:
                        src.setdefault(i, os.path.basename(t.path))
            starts = sorted(src)
            regions = []
            for i in starts:
                if regions and i <= regions[-1][1]:
                    regions[-1][1] = max(regions[-1][1], i + k)
                    regions[-1][2].add(src[i])
                else:
                    regions.append([i, i + k, {src[i]}])
            for s0, e0, files in regions:
                print("  %s:%s (%d tok) in %s" % (os.path.basename(o.path), o.span(s0, e0 - s0), e0 - s0, sorted(files)))
                print("      " + " ".join(x[1] for x in o.toks[s0:e0]))

    if a.raw:
        print("\n-- pass 2 (raw) --")
        stop = set(COMMON_IDS)
        for p in a.stop_ids_from:
            stop |= identifiers(Doc(p))
        t_ids, t_nums, t_com = {}, {}, {}
        for t in theirs:
            for x in identifiers(t):
                t_ids.setdefault(x, os.path.basename(t.path))
            for v, lines in numbers(t).items():
                t_nums.setdefault(v, (os.path.basename(t.path), lines[0]))
            for g, ln in comment_ngrams(t).items():
                t_com.setdefault(g, (os.path.basename(t.path), ln))
        for o in ours:
            ids = sorted(identifiers(o) & set(t_ids))
            dist = [x for x in ids if x not in stop]
            nums = numbers(o)
            shared_nums = sorted((v, nums[v][0], t_nums[v]) for v in nums if v in t_nums and not boring_number(v))
            com = sorted((g, ln, t_com[g]) for g, ln in comment_ngrams(o).items() if g in t_com)
            print("%s:" % os.path.basename(o.path))
            print("  shared identifiers (all): %d; distinctive (not in stoplist/baseline): %s" % (len(ids), dist))
            print("  shared unusual numeric constants: %s" % [
                ("%g" % v, "ours L%d" % l, "%s L%d" % tt) for v, l, tt in shared_nums])
            print("  shared comment 6-grams: %s" % [(g, "ours L%d" % l, "%s L%d" % tt) for g, l, tt in com])

    if a.json:
        with open(a.json, "w") as f:
            json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()
