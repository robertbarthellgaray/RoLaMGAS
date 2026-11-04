# RoLaMGAS on managed lab computers

CrowdStrike Falcon prevented the released application from opening, before any RoLaMGAS UI appeared. The notification did not provide the detection name or ID. This is insufficient to conclude that it is a false positive or to identify the offending behavior.

RoLaMGAS is a local Python scientific application, packaged with PyInstaller. It starts a loopback-only HTTP interface, opens the default browser, uses Python multiprocessing for Lambert searches, and can download JPL Horizons ephemerides and communicate with the configured anonymous community API. Its source is available under GPLv3. Normal operation does not need administrator privileges.

The v0.2.2 Windows executable uses PyInstaller one-file packaging: its dependencies are extracted into a temporary directory before Python starts. The new local Windows folder preview stores those dependencies next to the executable instead. It also includes native logo icons and Windows product/version metadata and disables optional UPX packing. This changes ordinary distribution packaging; it is not a Falcon workaround, does not establish safety, and may still be blocked.

Ask the lab IT/security team to inspect the Falcon event and its process tree, hash, detection name/ID and policy. Provide the source repository, the exact downloaded release and SHA-256, this description of expected network/process behavior, and the unpacked preview if they want to examine it. Any approval or vendor false-positive escalation belongs to that team. Do not disable the sensor or bypass lab policy. Code signing is a future distribution improvement; these previews are unsigned and no signing identity is claimed.

Released v0.2.2 Windows SHA-256:

`84dcbc53794e03b13dfe96b1241cf6dc482c5f7c601db6970d672e9930af984b`

Source and checksums: https://github.com/robertbarthellgaray/RoLaMGAS/releases/tag/rolamgas-v0.2.2

References:
- PyInstaller's documented one-file and one-folder operation: https://pyinstaller.org/en/stable/operating-mode.html
- CrowdStrike technical-support portal and contact information: https://www.crowdstrike.com/en-us/contact-us/

Build a local folder preview without replacing released binaries:

```powershell
.\.venv\Scripts\python.exe -c "from build_release import ROOT,executable; executable(ROOT/'baseline_ephemerides.zip',windows_folder=True)"
```

Keep the entire `releases/testing/windows-folder/RoLaMGAS` folder together. Launch `RoLaMGAS.exe` inside it; copying that EXE alone will not work. New binaries require the author's local trial and approval before publication, as specified in AGENTS.md.
