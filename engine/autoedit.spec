a = Analysis(
    ["autoedit/__main__.py"],
    pathex=["."],
    datas=[("../agent", "agent"), ("assets", "assets")],
    hiddenimports=["claude_agent_sdk"],
)
# The 353MB Claude Code CLI is downloaded on first run (autoedit setup), never shipped.
a.datas = [d for d in a.datas if "_bundled" not in d[0]]
a.binaries = [b for b in a.binaries if "_bundled" not in b[0]]
pyz = PYZ(a.pure)
# UTF-8 mode: on Windows open(), pipes and subprocess text default to cp1252 otherwise.
exe = EXE(pyz, a.scripts, [("X utf8", None, "OPTION")], exclude_binaries=True, name="autoedit", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="autoedit")
