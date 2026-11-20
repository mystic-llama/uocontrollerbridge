"""Compact controller silhouette with clickable controls."""
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen, QLinearGradient, QFont
from PySide6.QtWidgets import QWidget, QToolButton

CONTROLS = {
    'lt': (260, 40, 115, 56, 'LT'), 'rt': (740, 40, 115, 56, 'RT'),
    'lb': (245, 100, 140, 56, 'LB'), 'rb': (755, 100, 140, 56, 'RB'),
    'ls': (250, 255, 100, 100, 'L3'), 'rs': (640, 412, 100, 100, 'R3'),
    'back': (445, 246, 60, 36, '−'), 'start': (555, 246, 60, 36, '+'),
    'north': (765, 185, 66, 66, 'X'), 'west': (695, 255, 66, 66, 'Y'),
    'east': (835, 255, 66, 66, 'A'), 'south': (765, 325, 66, 66, 'B'),
    'dpad_up': (350, 355, 62, 62, '↑'), 'dpad_left': (300, 405, 62, 62, '←'),
    'dpad_right': (400, 405, 62, 62, '→'), 'dpad_down': (350, 455, 62, 62, '↓'),
    'p1': (205, 530, 84, 36, 'P1'), 'p2': (795, 530, 84, 36, 'P2'),
}


class ControllerDiagram(QWidget):
    controlSelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 200)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        self.buttons = {}
        self.selected = None
        self.available = set(CONTROLS) - {'p1', 'p2'}
        self.pressed = set()
        self.bindings = {}
        self.roles = ('Movement', 'Cursor')
        for name, (_, _, _, _, caption) in CONTROLS.items():
            button = QToolButton(self)
            button.setText(caption)
            button.setAccessibleName(name)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, control=name: self.controlSelected.emit(control))
            self.buttons[name] = button
        self.layout_buttons()

    def set_state(self, available=None, selected=None, pressed=None, bindings=None, roles=None):
        if available is not None:
            self.available = set(available)
        if selected is not None:
            self.selected = selected
        if pressed is not None:
            self.pressed = set(pressed)
        if bindings is not None:
            self.bindings = bindings
        if roles is not None:
            self.roles = roles
        self.layout_buttons()
        self.update()

    def scale(self):
        return min(self.width() / 1000.0, self.height() / 620.0)

    def layout_buttons(self):
        scale = self.scale()
        ox = (self.width() - 1000 * scale) / 2
        oy = (self.height() - 620 * scale) / 2
        for name, (x, y, w, h, caption) in CONTROLS.items():
            button = self.buttons[name]
            button.setGeometry(
                round(ox + (x - w / 2) * scale),
                round(oy + (y - h / 2) * scale),
                max(1, round(w * scale)),
                max(1, round(h * scale)),
            )
            button.setEnabled(name in self.available)
            if name in self.pressed:
                fill, border = '#1a3d2a', '#3FB950'
            elif name == self.selected:
                fill, border = '#14365c', '#3F91F4'
            else:
                fill, border = '#21262D', '#30363D'
            radius = min(10, round(min(w, h) * scale / 3)) if name in ('lb', 'rb', 'lt', 'rt') else round(min(w, h) * scale / 2)
            button.setStyleSheet(
                'QToolButton {background:%s;color:#E6EDF3;border:1px solid %s;border-radius:%dpx;'
                'font-size:%dpx;font-weight:600;padding:0;}'
                'QToolButton:hover {border-color:#63A8F7;background:#2a3644;}'
                'QToolButton:disabled {background:#161B22;color:#484f58;border-color:#21262D;}'
                % (fill, border, radius, max(9, round(22 * scale)))
            )
            text = self.bindings.get(name, 'Unassigned') if name in self.available else 'Not exposed separately by this controller'
            button.setToolTip(caption + ' · ' + text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_buttons()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = self.scale()
        p.translate((self.width() - 1000 * scale) / 2, (self.height() - 620 * scale) / 2)
        p.scale(scale, scale)
        shell = QPainterPath()
        shell.moveTo(275, 115)
        shell.cubicTo(200, 90, 130, 145, 110, 225)
        shell.cubicTo(75, 340, 35, 505, 100, 565)
        shell.cubicTo(150, 605, 225, 545, 300, 485)
        shell.cubicTo(365, 450, 635, 450, 700, 485)
        shell.cubicTo(775, 545, 850, 605, 900, 565)
        shell.cubicTo(965, 505, 925, 340, 890, 225)
        shell.cubicTo(870, 145, 800, 90, 725, 115)
        shell.cubicTo(620, 145, 380, 145, 275, 115)
        shell.closeSubpath()
        gradient = QLinearGradient(0, 130, 0, 580)
        gradient.setColorAt(0, QColor('#21262D'))
        gradient.setColorAt(1, QColor('#0D1117'))
        p.setPen(QPen(QColor('#30363D'), 3))
        p.setBrush(gradient)
        p.drawPath(shell)
        p.setPen(QPen(QColor('#0D1117'), 8))
        p.setBrush(QColor('#161B22'))
        p.drawEllipse(QRectF(187, 192, 126, 126))
        p.drawEllipse(QRectF(577, 349, 126, 126))
        p.setPen(QColor('#8B949E'))
        p.setFont(QFont('Segoe UI', 16))
        p.drawText(QRectF(170, 315, 160, 32), Qt.AlignmentFlag.AlignCenter, self.roles[0])
        p.drawText(QRectF(560, 475, 160, 32), Qt.AlignmentFlag.AlignCenter, self.roles[1])
        p.setPen(QColor('#3F91F4'))
        p.setFont(QFont('Segoe UI', 15, QFont.Weight.DemiBold))
        p.drawText(QRectF(385, 300, 230, 40), Qt.AlignmentFlag.AlignCenter, '@MysticLlama')
        p.end()
