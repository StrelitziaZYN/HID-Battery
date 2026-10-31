import sys
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
scr = app.primaryScreen()
pm = scr.grabWindow(0)
out = sys.argv[1] if len(sys.argv) > 1 else "tools/shots/screen.png"
pm.save(out)
print("saved", out, pm.width(), pm.height())
