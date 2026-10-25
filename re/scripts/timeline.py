r"""Frame-exact action timelines from the running dev build.

read_frame_ram only answers for the 4 snapshot regions (128 bytes each) the runtime copies every
frame, so the tracker points them at: Koh's sprite object, Koh's unit (+0x28 HP .. +0x9A state),
and two monsters' unit tails (+0x90: state +0x9A, sprite object +0xD4 inside the actor struct).
Sequence pointers are turned into (sequence index, step) with each unit's sprite bank.

    from timeline import Tracker
    t = Tracker(mon1=0x801EC920, mon2=0x801EC490)   # call before acting: regions record from now on
    f0 = g.frame(); ...act...; t.dump(f0, g.frame())
"""
import struct
from psx import Game

g = Game()
KOH = 0x800834B8
KOH_SPRITE = 0x80082E80


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


class Tracker:
    def __init__(self, mon1=None, mon2=None):
        self.regions = [('koh_spr', KOH_SPRITE), ('koh', KOH + 0x28)]
        self.units = {'koh': (KOH, KOH_SPRITE)}
        for name, u in (('m1', mon1), ('m2', mon2)):
            if u:
                self.regions.append((name, u + 0x90))
                self.units[name] = (u, u + 0xD4)
        for slot, (_, addr) in enumerate(self.regions):
            g.cmd('set_snapshot', slot=slot, addr='0x%08X' % addr, size=128)
        self.bank = {}
        for name, (u, spr) in self.units.items():
            bank = g.u32(g.u32(spr + 0x28))
            n = g.u32(bank + 4)
            table = g.read(g.u32(bank), n * 4)
            self.bank[name] = sorted((u32(table, i * 4), i) for i in range(n))

    def seq_of(self, name, ptr):
        best = None
        for s, i in self.bank[name]:
            if s <= ptr:
                best = (i, (ptr - s) // 8)
            else:
                break
        return best

    def _read(self, addr, n, frame):
        r = g.cmd('read_frame_ram', addr='0x%08X' % addr, len=n, frame=frame)
        return bytes.fromhex(r['hex'])

    def sample(self, frame):
        out = {}
        ks = self._read(KOH_SPRITE, 0x2C, frame)
        ku = self._read(KOH + 0x28, 0x74, frame)
        out['koh'] = dict(hp=ku[0], state=ku[0x72], sub=ku[0x73], seq=self.seq_of('koh', u32(ks, 0)),
                          mirror=ks[0x14] & 1, frame_ptr=u32(ks, 8))
        for name in ('m1', 'm2'):
            if name not in self.units:
                continue
            u, spr = self.units[name]
            b = self._read(u + 0x90, 0x70, frame)
            s = b[0x44:]
            out[name] = dict(hp=-1, state=b[0x0A], sub=b[0x0B], seq=self.seq_of(name, u32(s, 0)),
                             mirror=s[0x14] & 1, frame_ptr=u32(s, 8))
        return out

    def dump(self, f0, f1, quiet=False):
        prev = {}
        rows = []
        for f in range(f0, f1):
            smp = self.sample(f)
            for name, v in smp.items():
                key = (v['hp'], v['state'], v['sub'], v['seq'])
                if prev.get(name) != key:
                    rows.append((f, name, v))
                    prev[name] = key
        if not quiet:
            for f, name, v in rows:
                print('%6d +%4d %-4s hp %3d st %02x.%02x seq %s m%d' % (f, f - f0, name, v['hp'], v['state'],
                                                                      v['sub'], v['seq'], v['mirror']))
        return rows
