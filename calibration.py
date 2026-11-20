"""Interactive input learning; Qt timer polling sends no game or mouse input."""
import os
import time
os.environ['SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS'] = '1'
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QComboBox, QProgressBar, QCheckBox, QFrame,
)
from app_services import CONTROLS, detect_source, source_identity, apply_calibration, apply_button_calibration
from controller_bridge import joystick_connected


class CalibrationDialog(QDialog):
    def __init__(self, cfg, parent=None, buttons_only=False):
        super().__init__(parent)
        import pygame
        self.pg = pygame
        self.cfg = cfg
        self.result_config = None
        self.buttons_only = buttons_only
        pygame.display.init()
        pygame.joystick.init()
        self.setWindowTitle('Check bumpers / triggers' if buttons_only else 'Learn your controller')
        self.resize(480, 360)
        self.setMinimumSize(420, 320)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        title = QLabel('Check bumpers / triggers' if buttons_only else 'Controller setup')
        title.setObjectName('brand')
        layout.addWidget(title)
        self.instructions = QLabel('Connect the controller, then select it below. No game actions run during setup.')
        self.instructions.setObjectName('muted')
        self.instructions.setWordWrap(True)
        layout.addWidget(self.instructions)

        card = QFrame()
        card.setObjectName('card')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)
        self.devices = QComboBox()
        card_layout.addWidget(self.devices)
        self.refresh = QPushButton('Refresh controllers')
        self.refresh.clicked.connect(self.scan)
        card_layout.addWidget(self.refresh)
        self.paddles = QCheckBox('Test independent P1 / P2 rear buttons')
        card_layout.addWidget(self.paddles)
        if buttons_only:
            self.paddles.hide()
        hint = QLabel('Rear buttons that duplicate L3/R3 cannot be assigned independently. Skip them if needed.')
        hint.setObjectName('muted')
        hint.setWordWrap(True)
        card_layout.addWidget(hint)
        if buttons_only:
            hint.hide()
        self.progress = QProgressBar()
        card_layout.addWidget(self.progress)
        self.live = QLabel('')
        self.live.setObjectName('muted')
        self.live.setWordWrap(True)
        card_layout.addWidget(self.live)
        layout.addWidget(card)
        layout.addStretch()

        row = QHBoxLayout()
        row.setSpacing(6)
        self.action = QPushButton('Begin')
        self.action.setObjectName('primary')
        self.action.clicked.connect(self.advance)
        row.addWidget(self.action)
        self.skip = QPushButton('Skip rear button')
        self.skip.clicked.connect(self.skip_step)
        self.skip.hide()
        row.addWidget(self.skip)
        cancel = QPushButton('Cancel')
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)

        self.joy = None
        self.steps = []
        self.index = -1
        self.learned = {}
        self.used = set()
        self.before = None
        self.candidate = None
        self.since = 0
        self.started = 0
        self.confirm_source = None
        self.release_wait = False
        self.baseline = None
        self.released_since = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(16)
        self.scan()
        self.finished.connect(lambda _: self.cleanup())

    def cleanup(self):
        self.timer.stop()
        self.pg.quit()

    def scan(self):
        self.pg.event.pump()
        self.devices.clear()
        for i in range(self.pg.joystick.get_count()):
            joy = self.pg.joystick.Joystick(i)
            self.devices.addItem(joy.get_name(), joy.get_instance_id())
            if joy.get_guid() == self.cfg.get('device_guid'):
                self.devices.setCurrentIndex(self.devices.count() - 1)
        self.action.setEnabled(self.devices.count() > 0)
        if not self.devices.count():
            self.live.setText('No controller detected. Check Bluetooth or USB, then Refresh.')

    def snapshot(self):
        if not joystick_connected(self.pg, self.joy):
            raise RuntimeError('Controller disconnected. Cancel and reconnect before retrying.')
        return {
            'axes': [self.joy.get_axis(i) for i in range(self.joy.get_numaxes())],
            'buttons': [bool(self.joy.get_button(i)) for i in range(self.joy.get_numbuttons())],
            'hats': [self.joy.get_hat(i) for i in range(self.joy.get_numhats())],
        }

    def advance(self):
        if self.index == -1:
            for i in range(self.pg.joystick.get_count()):
                joy = self.pg.joystick.Joystick(i)
                if joy.get_instance_id() == self.devices.currentData():
                    self.joy = joy
                    break
            if self.joy is None:
                self.live.setText('The controller changed. Refresh and select it again.')
                return
            self.steps = [
                (key, 'Press ' + label, False)
                for key, label in CONTROLS
                if not self.buttons_only or key in ('lb', 'rb', 'lt', 'rt')
            ]
            if self.buttons_only:
                self.used = {
                    source_identity(spec)
                    for name, spec in self.cfg['presets'][self.cfg['preset']]['controls'].items()
                    if name not in ('lb', 'rb', 'lt', 'rt')
                }
            if not self.buttons_only:
                self.steps += [
                    (side + '_' + axis, 'Push ' + side.upper() + ' stick fully ' + direction, True)
                    for side in ('left', 'right')
                    for axis, direction in [('x', 'RIGHT'), ('y', 'DOWN')]
                ]
            if self.paddles.isChecked():
                self.steps += [('p1', 'Press rear P1 only', False), ('p2', 'Press rear P2 only', False)]
            self.devices.setEnabled(False)
            self.refresh.hide()
            self.paddles.setEnabled(False)
            self.progress.setMaximum(len(self.steps))
            self.index = 0
            self.show_step()
            return
        if self.index >= len(self.steps):
            try:
                apply = apply_button_calibration if self.buttons_only else apply_calibration
                self.result_config = apply(self.cfg, self.joy.get_name(), self.joy.get_guid(), self.learned)
            except Exception as exc:
                self.live.setText(str(exc))
                return
            self.accept()
            return
        try:
            self.before = self.snapshot()
        except Exception as exc:
            self.live.setText(str(exc))
            return
        if any(self.before['buttons']) or any(any(hat) for hat in self.before['hats']):
            self.live.setText('Release every button and the D-pad before clicking Ready.')
            self.before = None
            return
        self.baseline = self.before
        self.started = time.monotonic()
        self.candidate = None
        self.confirm_source = None
        self.release_wait = False
        self.instructions.setText(self.steps[self.index][1] + '. Hold until detected.')
        self.action.setEnabled(False)

    def show_step(self):
        self.before = None
        self.confirm_source = None
        self.release_wait = False
        self.progress.setValue(self.index)
        optional = self.index < len(self.steps) and self.steps[self.index][0] in ('p1', 'p2')
        self.skip.setVisible(optional)
        if self.index >= len(self.steps):
            self.instructions.setText(
                'Four inputs checked. Save to finish. Assignments and sticks are preserved.'
                if self.buttons_only
                else 'All controls learned. Save to finish. Your game bindings are preserved.'
            )
            self.action.setText('Save button inputs' if self.buttons_only else 'Save controller')
            self.action.setEnabled(True)
            return
        self.instructions.setText(
            'Next: ' + self.steps[self.index][1] + '. Release ALL controls, center sticks, then Ready.'
        )
        self.action.setText('Ready')
        self.action.setEnabled(True)

    def skip_step(self):
        self.index += 1
        self.show_step()

    def poll(self):
        try:
            self.pg.event.get()
            if self.joy is None:
                return
            current = self.snapshot()
            self.live.setText('Connected: ' + self.joy.get_name())
            if self.release_wait:
                source = self.confirm_source
                released = (
                    (not current['buttons'][source['button']]) if 'button' in source
                    else (current['hats'][source['hat']][source['component']] != source['sign']) if 'hat' in source
                    else abs(current['axes'][source['axis']] - source['rest']) < .15
                )
                if released:
                    if self.released_since is None:
                        self.released_since = time.monotonic()
                    if time.monotonic() - self.released_since > .2:
                        self.before = self.baseline
                        self.release_wait = False
                        self.candidate = None
                        self.started = time.monotonic()
                        self.instructions.setText(self.steps[self.index][1] + ' once more to confirm.')
                else:
                    self.released_since = None
                return
            if self.before is None:
                return
            key, _, axis_only = self.steps[self.index]
            source = detect_source(self.before, current, axis_only, key in ('lt', 'rt'))
            if source != self.candidate:
                self.candidate = source
                self.since = time.monotonic()
            if source and time.monotonic() - self.since >= .12:
                identity = source_identity(source)
                if not axis_only and identity in self.used:
                    self.before = None
                    self.action.setEnabled(True)
                    self.instructions.setText(
                        'That input already belongs to another button. Release and retry, or Skip rear button.'
                    )
                    return
                if self.buttons_only and 'axis' in source and source['axis'] in self.cfg['presets'][self.cfg['preset']]['left_stick'] + self.cfg['presets'][self.cfg['preset']]['right_stick']:
                    self.before = None
                    self.action.setEnabled(True)
                    self.instructions.setText(
                        'That is a stick axis. Release sticks, click Ready and press only the requested trigger.'
                    )
                    return
                if not axis_only and self.confirm_source is None:
                    self.confirm_source = source
                    self.before = None
                    self.release_wait = True
                    self.released_since = None
                    self.instructions.setText('Detected. Release fully, then press once more when prompted.')
                    return
                if not axis_only and source_identity(source) != source_identity(self.confirm_source):
                    self.before = None
                    self.action.setEnabled(True)
                    self.instructions.setText('Second press differed. Release everything and click Ready to retry.')
                    return
                self.learned[key] = source
                if not axis_only:
                    self.used.add(identity)
                self.index += 1
                self.show_step()
            elif time.monotonic() - self.started > 25:
                self.before = None
                self.action.setEnabled(True)
                self.instructions.setText('No input detected. Release controls and click Ready to retry.')
        except Exception as exc:
            self.before = None
            self.action.setEnabled(False)
            self.live.setText(str(exc))
