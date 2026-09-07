"""
IEEE C37.111-2013 CFG + ASCII DAT synthetic fixture (mixed analog/digital).
Validated for regression: channel counts, sample rate, ASCII ft.
"""

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "test_data" / "comtrade" / "ieee_2013"
OUT.mkdir(parents=True, exist_ok=True)


def write_fixture() -> None:
    cfg = """TestStation,IED-REL670,2013
6,4A,2D
1,IA,A,,A,1.0,0.0,0.0,-32767,32767,1.0,1.0,P
2,IB,B,,A,1.0,0.0,0.0,-32767,32767,1.0,1.0,P
3,IC,C,,A,1.0,0.0,0.0,-32767,32767,1.0,1.0,P
4,VA,A,,V,0.1,0.0,0.0,-32767,32767,1.0,1.0,P
5,50_PICKUP,,0
6,50_TRIP,,0
50.0
1
1000.0,40
01/01/2024,12:00:00.000000
01/01/2024,12:00:00.020000
ASCII
1.0
"""
    lines = []
    for n in range(1, 41):
        # Pre-fault then step change on IA
        ia = 100 if n < 20 else 5000
        ib, ic = 100, 100
        va = 5000 if n < 20 else 2000
        t = (n - 1) * 1000
        pu = 1 if n >= 22 else 0
        tr = 1 if n >= 28 else 0
        lines.append(f"{n},{t},{ia},{ib},{ic},{va},{pu}{tr}")
    dat = "\n".join(lines) + "\n"
    (OUT / "mixed_event.cfg").write_text(cfg, encoding="utf-8")
    (OUT / "mixed_event.dat").write_text(dat, encoding="utf-8")


if __name__ == "__main__":
    write_fixture()
    print("Wrote IEEE 2013 fixtures")
