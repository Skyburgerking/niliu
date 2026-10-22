# -*- coding: utf-8 -*-
"""Read-only live-process organs: attach / scan / snapshot / diff / pointer chain / widget rects."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import struct
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", wt.LONG),
                ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_char * 260)]


class _MODULEENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD),
                ("th32ProcessID", wt.DWORD), ("GlblcntUsage", wt.DWORD),
                ("ProccntUsage", wt.DWORD), ("modBaseAddr", ctypes.c_void_p),
                ("modBaseSize", wt.DWORD), ("hModule", wt.HMODULE),
                ("szModule", ctypes.c_char * 256), ("szExePath", ctypes.c_char * 260)]


class _MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


class LiveProc(object):

    def __init__(self, name):
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        ent = _PROCESSENTRY32()
        ent.dwSize = ctypes.sizeof(_PROCESSENTRY32)
        self.pid = None
        if k32.Process32First(snap, ctypes.byref(ent)):
            while True:
                if ent.szExeFile.decode("mbcs", "ignore").lower() == name.lower():
                    self.pid = ent.th32ProcessID
                    break
                if not k32.Process32Next(snap, ctypes.byref(ent)):
                    break
        k32.CloseHandle(snap)
        if self.pid is None:
            raise RuntimeError("进程不在：%s" % name)
        self.h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                                 False, self.pid)
        if not self.h:
            raise RuntimeError("OpenProcess 失败：%d" % ctypes.get_last_error())
        self.name = name
        self.module, self.base, self.size = self._module(name)

    def _module(self, name):
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, self.pid)
        ent = _MODULEENTRY32()
        ent.dwSize = ctypes.sizeof(_MODULEENTRY32)
        out = (name, 0, 0)
        if k32.Module32First(snap, ctypes.byref(ent)):
            while True:
                if ent.szModule.decode("mbcs", "ignore").lower() == name.lower():
                    out = (name, int(ent.modBaseAddr or 0), int(ent.modBaseSize))
                    break
                if not k32.Module32Next(snap, ctypes.byref(ent)):
                    break
        k32.CloseHandle(snap)
        return out

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n,
                                     ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def i32(self, addr):
        d = self.read(addr, 4)
        return None if not d or len(d) < 4 else struct.unpack("<i", d)[0]

    def u32(self, addr):
        d = self.read(addr, 4)
        return None if not d or len(d) < 4 else struct.unpack("<I", d)[0]

    def regions(self, heap_only=False):
        out = []
        addr = 0
        mbi = _MBI()
        while addr < 0x7FFF0000:
            if not k32.VirtualQueryEx(self.h, ctypes.c_void_p(addr),
                                      ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            size = int(mbi.RegionSize)
            if (mbi.State == MEM_COMMIT and size > 0
                    and not (mbi.Protect & PAGE_GUARD)
                    and mbi.Protect != PAGE_NOACCESS):
                if not heap_only or mbi.Type == 0x20000:      # MEM_PRIVATE
                    out.append((int(mbi.BaseAddress or 0), size, mbi.Type))
            addr += max(size, 0x1000)
        return out


class Live(object):

    def __init__(self):
        self.proc = None
        self.snaps = {}
        self.n = 0

    def need(self):
        if self.proc is None:
            raise RuntimeError("先 live_attach")
        return self.proc

    def attach(self, name):
        self.proc = LiveProc(name)
        self.snaps = {}
        return self.proc

    def snap(self, limit_mb=96):
        p = self.need()
        data = {}
        for base, size, _t in p.regions(heap_only=True):
            if size > limit_mb * 1024 * 1024:
                continue
            d = p.read(base, size)
            if d:
                data[base] = d
        self.n += 1
        sid = "s%d" % self.n
        self.snaps[sid] = data
        for old in list(self.snaps)[:-3]:
            self.snaps.pop(old, None)
        return sid, len(data)

    def diff(self, sid, max_rows=60, align=4):
        old = self.snaps.get(sid)
        if old is None:
            raise RuntimeError("没有这个快照：%s" % sid)
        p = self.need()
        rows = []
        for base, before in old.items():
            after = p.read(base, len(before))
            if not after:
                continue
            k = 0
            n = min(len(before), len(after))
            while k + 4 <= n:
                a = before[k:k + 4]
                b = after[k:k + 4]
                if a != b:
                    va = struct.unpack("<i", a)[0]
                    vb = struct.unpack("<i", b)[0]
                    rows.append((base + k, va, vb))
                    if len(rows) >= max_rows * 4:
                        break
                k += align
            if len(rows) >= max_rows * 4:
                break
        return rows[:max_rows]


def _addr(v):
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s.startswith("0x") or s.startswith("0X"):
        return int(s, 16)
    return int(s, 10)


def _hex(v):
    return "0x%08x" % (v or 0)


def op_live_attach(self, req):
    t0 = time.time()
    name = req.get("exe") or req.get("process")
    if not name:
        return {"ok": False, "err": "要给 exe（进程名，如 PlantsVsZombies.exe）"}
    if not getattr(self, "live", None):
        self.live = Live()
    p = self.live.attach(name)
    return {"ok": True, "pid": p.pid, "module": p.module,
            "base": _hex(p.base), "size": p.size,
            "regions": len(p.regions()), "elapsed": round(time.time() - t0, 3)}


def op_live_scan(self, req):
    t0 = time.time()
    p = getattr(self, "live", None) and self.live.need()
    if not p:
        return {"ok": False, "err": "先 live_attach"}
    value = int(req.get("value"))
    width = int(req.get("width", 4))
    maxrows = int(req.get("max", 40))
    heap_only = bool(req.get("heap", True))
    fmt = {1: "<b", 2: "<h", 4: "<i"}[width]
    target = struct.pack(fmt, value)
    hits = []
    for base, size, _t in p.regions(heap_only=heap_only):
        if size > 48 * 1024 * 1024:
            continue
        data = p.read(base, size)
        if not data:
            continue
        i = data.find(target)
        while i >= 0:
            if i % 4 == 0:
                hits.append(base + i)
                if len(hits) >= maxrows:
                    break
            i = data.find(target, i + 1)
        if len(hits) >= maxrows:
            break
    return {"ok": True, "n": len(hits), "addrs": [_hex(a) for a in hits],
            "elapsed": round(time.time() - t0, 3)}


def op_live_snap(self, req):
    t0 = time.time()
    live = getattr(self, "live", None)
    if not live:
        return {"ok": False, "err": "先 live_attach"}
    sid, n = live.snap()
    return {"ok": True, "snap": sid, "regions": n,
            "elapsed": round(time.time() - t0, 3)}


def op_live_diff(self, req):
    t0 = time.time()
    live = getattr(self, "live", None)
    if not live:
        return {"ok": False, "err": "先 live_attach"}
    sid = req.get("snap")
    if not sid:
        ids = list(live.snaps)
        if not ids:
            return {"ok": False, "err": "没有快照，先 live_snap"}
        sid = ids[-1]
    rows = live.diff(sid, max_rows=int(req.get("max", 60)),
                     align=int(req.get("align", 4)))
    return {"ok": True, "snap": sid, "n": len(rows),
            "rows": [{"addr": _hex(a), "old": o, "new": n} for a, o, n in rows],
            "elapsed": round(time.time() - t0, 3)}


def op_live_read(self, req):
    p = getattr(self, "live", None) and self.live.need()
    if not p:
        return {"ok": False, "err": "先 live_attach"}
    addr = _addr(req["addr"])
    n = int(req.get("n", 64))
    data = p.read(addr, n) or b""
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        ints = []
        for k in range(0, len(chunk) - 3, 4):
            ints.append(str(struct.unpack("<i", chunk[k:k + 4])[0]))
        lines.append({"addr": _hex(addr + off),
                      "hex": " ".join("%02x" % b for b in chunk),
                      "i32": " ".join(ints)})
    return {"ok": True, "n": len(data), "lines": lines}


def op_live_chain(self, req):
    p = getattr(self, "live", None) and self.live.need()
    if not p:
        return {"ok": False, "err": "先 live_attach"}
    root = _addr(req["addr"])
    offs = [_addr(o) for o in req.get("offsets") or []]
    hop = [{"step": "root", "at": _hex(root)}]
    cur = p.u32(root)
    if not cur:
        return {"ok": False, "err": "根指针为空（进程基址变了？）", "hops": hop}
    hop.append({"step": "deref", "at": _hex(root), "to": _hex(cur)})
    for off in offs[:-1]:
        nxt = p.u32(cur + off)
        hop.append({"step": "deref", "at": _hex(cur), "off": hex(off),
                    "to": _hex(nxt or 0)})
        if not nxt:
            return {"ok": False, "err": "链断了", "hops": hop}
        cur = nxt
    final = cur + (offs[-1] if offs else 0)
    hop.append({"step": "value", "at": _hex(final)})
    d = p.read(final, 8) or b""
    i32 = struct.unpack("<i", d[:4])[0] if len(d) >= 4 else None
    f32 = struct.unpack("<f", d[:4])[0] if len(d) >= 4 else None
    return {"ok": True, "addr": _hex(final), "i32": i32,
            "f32": round(f32, 4) if f32 is not None else None, "hops": hop}


def _plausible_rect(x, y, w, h, px, py):
    return (0 <= x < 4000 and 0 <= y < 4000 and 0 < w <= 2000 and 0 < h <= 2000
            and x <= px < x + w and y <= py < y + h)


def op_live_rect(self, req):
    t0 = time.time()
    p = getattr(self, "live", None) and self.live.need()
    if not p:
        return {"ok": False, "err": "先 live_attach"}
    px, py = int(req["x"]), int(req["y"])
    span = int(req.get("span", 24))
    maxrows = int(req.get("max", 30))
    found = []
    for base, size, _t in p.regions(heap_only=True):
        if size > 48 * 1024 * 1024:
            continue
        data = p.read(base, size)
        if not data:
            continue
        for off in range(0, len(data) - 16, 4):
            x, y, w, h = struct.unpack("<iiii", data[off:off + 16])
            if not _plausible_rect(x, y, w, h, px, py):
                continue
            if abs(x - px) > 400 and abs(y - py) > 400:
                continue
            if w * h > 800 * 600:
                continue
            found.append((w * h, base + off, x, y, w, h))
        if len(found) > 2000:
            break
    found.sort(key=lambda r: r[0])
    rows = [{"at": _hex(a), "rect": [x, y, w, h], "center": [x + w // 2, y + h // 2],
             "area": ar} for ar, a, x, y, w, h in found[:maxrows]]
    return {"ok": True, "n": len(found), "rows": rows,
            "elapsed": round(time.time() - t0, 3)}


def op_live_widgets(self, req):
    p = getattr(self, "live", None) and self.live.need()
    if not p:
        return {"ok": False, "err": "先 live_attach"}
    addr = _addr(req["addr"])
    n = int(req.get("n", 8))
    stride = int(req.get("stride", 0x60))
    rows = []
    for i in range(n):
        a = addr + i * stride
        d = p.read(a, 0x20)
        if not d or len(d) < 0x18:
            break
        x, y, w, h = struct.unpack("<iiii", d[8:24])
        rows.append({"at": _hex(a), "rect": [x, y, w, h],
                     "center": [x + w // 2, y + h // 2]})
    return {"ok": True, "n": len(rows), "rows": rows}


def op_live_watch(self, req):
    p = getattr(self, "live", None) and self.live.need()
    if not p:
        return {"ok": False, "err": "先 live_attach"}
    out = {}
    for name, path in (req.get("keys") or {}).items():
        base, _, off = str(path).partition("+")
        addr = _addr(base) + (_addr(off) if off else 0)
        out[name] = {"addr": _hex(addr), "i32": p.i32(addr),
                     "f32": struct.unpack("<f", struct.pack("<i", p.i32(addr) or 0))[0]}
    return {"ok": True, "keys": out}


def op_live_rects_page(self, req):
    t0 = time.time()
    p = getattr(self, "live", None) and self.live.need()
    if not p:
        return {"ok": False, "err": "先 live_attach"}
    lo = int(req.get("min_area", 600))
    hi = int(req.get("max_area", 60000))
    seen = set()
    rows = []
    for base, size, _t in p.regions(heap_only=True):
        if size > 48 * 1024 * 1024:
            continue
        data = p.read(base, size)
        if not data:
            continue
        for off in range(0, len(data) - 16, 4):
            x, y, w, h = struct.unpack("<iiii", data[off:off + 16])
            if not (0 <= x < 800 and 0 <= y < 600 and 20 <= w <= 400 and 20 <= h <= 300):
                continue
            if not (lo <= w * h <= hi):
                continue
            key = (x, y, w, h)
            if key in seen:
                continue
            seen.add(key)
            rows.append({"rect": [x, y, w, h], "center": [x + w // 2, y + h // 2],
                         "at": _hex(base + off)})
    rows.sort(key=lambda r: (r["rect"][1], r["rect"][0]))
    return {"ok": True, "n": len(rows), "rows": rows[:int(req.get("max", 60))],
            "elapsed": round(time.time() - t0, 3)}


LIVE_OPS = ("live_attach", "live_scan", "live_snap", "live_diff", "live_read",
            "live_chain", "live_rect", "live_rects_page", "live_widgets",
            "live_watch")


def attach_live(engine_cls):
    for name in LIVE_OPS:
        setattr(engine_cls, "op_" + name, globals()["op_" + name])
    return LIVE_OPS
