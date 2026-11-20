a = Analysis(["probe_agent.py"], datas=[("agent", "agent")], hiddenimports=["claude_agent_sdk"])
a.datas = [d for d in a.datas if "_bundled" not in d[0]]   # never ship the 353MB CLI
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="probe", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="probe")
