"""Per-niche look. Luma-only `eq` keeps product/clothing colour true (edit-video lesson)."""

LOOKS: dict[str, dict] = {
    "thoi-trang": {"gamma": 1.08, "brightness": 0.015, "contrast": 1.02, "saturation": 1.0,
                   "skin": {"smooth": 6, "lift": 0.015}},
    "my-pham": {"gamma": 1.04, "brightness": 0.010, "contrast": 1.00, "saturation": 1.0, "skin": None},
    "do-an": {"gamma": 1.06, "brightness": 0.012, "contrast": 1.03, "saturation": 1.06, "skin": None},
    "phu-kien": {"gamma": 1.04, "brightness": 0.010, "contrast": 1.02, "saturation": 1.0, "skin": None},
    "chung": {"gamma": 1.05, "brightness": 0.010, "contrast": 1.00, "saturation": 1.0, "skin": None},
}


def look_graph(niche: str, inp: str, out: str, scale: str | None = None) -> str:
    lk = LOOKS[niche]
    eq = (f"eq=gamma={lk['gamma']}:brightness={lk['brightness']}:"
          f"contrast={lk['contrast']}:saturation={lk['saturation']}")
    tail = f"scale={scale},format=yuv420p" if scale else "format=yuv420p"
    skin = lk["skin"]
    if not skin:
        return f"[{inp}]{eq},{tail}[{out}]"
    # Chroma-box skin mask (edit-video): smooth + lift luma only inside the mask.
    return (
        f"[{inp}]format=yuv444p,{eq}[lk0];"
        f"[lk0]split=3[sk0][sk1][sk2];"
        f"[sk1]geq=lum='255*between(cb(X,Y),80,125)*between(cr(X,Y),135,170)*gt(lum(X,Y),75)':cb=128:cr=128,"
        f"format=gray,gblur=sigma=5,format=yuv444p[skm];"
        f"[sk2]bilateral=sigmaS={skin['smooth']}:sigmaR=0.06:planes=1,eq=brightness={skin['lift']}[sks];"
        f"[sk0][sks][skm]maskedmerge=planes=1,{tail}[{out}]"
    )
