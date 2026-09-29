from pathlib import Path
import py_compile

root = Path(__file__).parent
for path in [root/"app.py", root/"src"/"ai_engine.py", root/"src"/"record_utils.py", root/"src"/"excel_exporter.py"]:
    py_compile.compile(str(path), doraise=True)
print("IQAC Analyzer smoke test passed.")
