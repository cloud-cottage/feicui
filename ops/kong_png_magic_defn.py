"""造一张**真 PNG**（含 CRC、可由 `file` 识别），用于 PNG 魔数嗅探定性。"""
import struct
import zlib

OUT = '/tmp/kong-real.png'


def chunk(tag, data):
    body = tag + data
    return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xFFFFFFFF)


def main():
    w = h = 8
    rows = []
    for y in range(h):
        row = b'\x00'
        for x in range(w):
            row += bytes([(x * 31) % 256, (y * 17) % 256, 40])
        rows.append(row)
    raw = b''.join(rows)
    png = (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw))
        + chunk(b'IEND', b'')
    )
    with open(OUT, 'wb') as fh:
        fh.write(png)
    print('wrote', OUT, len(png), 'bytes  head12=', png[:12].hex())


if __name__ == '__main__':
    main()
