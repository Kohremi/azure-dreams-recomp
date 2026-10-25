"""Extract every file from a raw MODE2/2352 PS1 disc image (ISO9660) into a folder."""
import struct, sys, os

def main(bin_path, out_dir):
    f = open(bin_path, 'rb')
    def sec(n):
        f.seek(n * 2352)
        return f.read(2352)[24:24 + 2048]
    pvd = sec(16)
    root = pvd[156:156 + 34]
    def walk(lba, size, path):
        data = b''.join(sec(lba + i) for i in range((size + 2047) // 2048))
        i = 0
        while i < len(data):
            l = data[i]
            if l == 0:
                i = (i // 2048 + 1) * 2048
                continue
            rec = data[i:i + l]
            i += l
            elba = struct.unpack('<I', rec[2:6])[0]
            esize = struct.unpack('<I', rec[10:14])[0]
            flags, nl = rec[25], rec[32]
            name = rec[33:33 + nl]
            if name in (b'\x00', b'\x01'):
                continue
            n = name.decode().split(';')[0]
            if flags & 2:
                walk(elba, esize, os.path.join(path, n))
                continue
            dst = os.path.join(out_dir, path, n)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'wb') as o:
                left = esize
                for s in range(elba, elba + (esize + 2047) // 2048):
                    chunk = sec(s)[:min(2048, left)]
                    o.write(chunk)
                    left -= len(chunk)
            print(f'{elba:7d} {esize:10d}  {os.path.join(path, n)}')
    walk(struct.unpack('<I', root[2:6])[0], struct.unpack('<I', root[10:14])[0], '')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
