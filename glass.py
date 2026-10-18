"""Shared neutral, translucent surfaces; background is softened on the GPU."""
from PySide6.QtGui import QColor

opacity=.58
def panel(extra=0):return QColor(19,19,24,max(12,min(235,int(255*opacity)+extra)))
def border():return QColor(255,255,255,27)
