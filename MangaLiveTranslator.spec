from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

hiddenimports = collect_submodules("rapidocr") + collect_submodules("ctranslate2")
binaries = collect_dynamic_libs("onnxruntime") + collect_dynamic_libs("ctranslate2")

a = Analysis(["app.py"], pathex=["src"], binaries=binaries, hiddenimports=hiddenimports)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="MangaLiveTranslator", console=False)
