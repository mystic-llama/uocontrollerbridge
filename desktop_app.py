"""Windows desktop shell. Controller polling lives in a managed child process."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import sys
import time
import traceback
import uuid

from PySide6.QtCore import QLockFile, QProcess, QTimer, QUrl, Qt
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QScrollArea, QFrame, QFormLayout, QComboBox, QCheckBox, QDoubleSpinBox,
    QFileDialog, QMessageBox, QPlainTextEdit, QSystemTrayIcon, QMenu, QDialog, QGridLayout,
)
import app_services as services
from controller_bridge import VERSION, configure, host_elevated, load_config, save_config

STYLE = '''
QWidget {
  background: #0D1117;
  color: #E6EDF3;
  font-family: "Segoe UI";
  font-size: 12px;
}
QMainWindow, QDialog { background: #0D1117; }
QLabel#brand { font-size: 15px; font-weight: 700; color: #E6EDF3; letter-spacing: 0.2px; }
QLabel#brandSub { font-size: 11px; color: #8B949E; }
QLabel#sectionTitle { font-size: 12px; font-weight: 600; color: #E6EDF3; }
QLabel#muted, QLabel[subtitle="true"] { color: #8B949E; font-size: 11px; }
QLabel#chipText { font-size: 11px; color: #E6EDF3; }
QLabel#chipMuted { font-size: 11px; color: #8B949E; }
QFrame#banner {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #0A1628, stop:0.45 #123A6B, stop:1 #3F91F4);
  border: none;
  border-radius: 0;
  min-height: 44px;
  max-height: 44px;
}
QFrame#card {
  background: #161B22;
  border: 1px solid #30363D;
  border-radius: 8px;
}
QFrame#chip {
  background: #21262D;
  border: 1px solid #30363D;
  border-radius: 10px;
  padding: 2px 8px;
}
QFrame#chipGood { background: #12261a; border: 1px solid #238636; border-radius: 10px; }
QFrame#chipWarn { background: #2a2111; border: 1px solid #9e6a03; border-radius: 10px; }
QFrame#chipBad  { background: #2d1517; border: 1px solid #da3633; border-radius: 10px; }
QPushButton {
  min-height: 14px;
  background: #21262D;
  border: 1px solid #30363D;
  border-radius: 6px;
  padding: 6px 12px;
  color: #E6EDF3;
}
QPushButton:hover { background: #30363D; border-color: #484f58; }
QPushButton:pressed { background: #161B22; }
QPushButton:disabled { color: #484f58; border-color: #21262D; background: #161B22; }
QPushButton#primary {
  background: #3F91F4;
  border-color: #3F91F4;
  color: #ffffff;
  font-weight: 600;
}
QPushButton#primary:hover { background: #63A8F7; border-color: #63A8F7; }
QPushButton#primary:pressed { background: #2F7BD4; }
QPushButton#danger {
  background: #21262D;
  border-color: #da3633;
  color: #FF7B72;
}
QPushButton#ghost {
  background: transparent;
  border: 1px solid #30363D;
  color: #8B949E;
  padding: 4px 10px;
}
QPushButton#ghost:hover { color: #E6EDF3; border-color: #484f58; }
QPushButton#setupToggle {
  text-align: left;
  padding: 8px 12px;
  font-weight: 600;
}
QTabWidget::pane {
  border: 1px solid #30363D;
  border-radius: 8px;
  top: -1px;
  background: #0D1117;
  padding: 8px;
}
QTabBar::tab {
  background: #161B22;
  color: #8B949E;
  border: 1px solid #30363D;
  border-bottom: none;
  border-top-left-radius: 6px;
  border-top-right-radius: 6px;
  padding: 7px 14px;
  margin-right: 3px;
  min-width: 72px;
}
QTabBar::tab:selected {
  background: #21262D;
  color: #E6EDF3;
  border-color: #3F91F4;
}
QTabBar::tab:hover:!selected { color: #E6EDF3; background: #1c2128; }
QComboBox, QDoubleSpinBox, QSpinBox, QPlainTextEdit, QLineEdit, QKeySequenceEdit {
  background: #0D1117;
  border: 1px solid #30363D;
  border-radius: 6px;
  padding: 5px 8px;
  min-height: 18px;
  selection-background-color: #3F91F4;
}
QComboBox:hover, QLineEdit:hover, QDoubleSpinBox:hover, QSpinBox:hover {
  border-color: #484f58;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
  background: #161B22;
  border: 1px solid #30363D;
  selection-background-color: #3F91F4;
  outline: 0;
}
QTableWidget {
  background: #0D1117;
  alternate-background-color: #161B22;
  gridline-color: #21262D;
  border: 1px solid #30363D;
  border-radius: 6px;
  selection-background-color: #14365c;
  selection-color: #E6EDF3;
}
QHeaderView::section {
  background: #161B22;
  color: #8B949E;
  border: none;
  border-bottom: 1px solid #30363D;
  border-right: 1px solid #21262D;
  padding: 5px 8px;
  font-weight: 600;
}
QCheckBox { spacing: 8px; padding: 2px 0; color: #E6EDF3; }
QCheckBox::indicator {
  width: 14px; height: 14px;
  border: 1px solid #30363D;
  border-radius: 3px;
  background: #0D1117;
}
QCheckBox::indicator:checked { background: #3F91F4; border-color: #3F91F4; }
QProgressBar {
  border: 1px solid #30363D;
  border-radius: 6px;
  text-align: center;
  background: #0D1117;
  min-height: 14px;
}
QProgressBar::chunk { background: #3F91F4; border-radius: 5px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
  background: transparent; width: 10px; margin: 0;
}
QScrollBar::handle:vertical {
  background: #30363D; border-radius: 5px; min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QPlainTextEdit { font-family: Consolas, "Cascadia Mono", monospace; font-size: 11px; }
QToolTip {
  background: #161B22;
  color: #E6EDF3;
  border: 1px solid #30363D;
  padding: 4px 8px;
}
QMenu {
  background: #161B22;
  border: 1px solid #30363D;
  padding: 4px;
}
QMenu::item { padding: 6px 18px; border-radius: 4px; }
QMenu::item:selected { background: #21262D; }
QMessageBox { background: #0D1117; }
'''


def button(text, callback, primary=False, object_name=None):
    result = QPushButton(text)
    result.clicked.connect(callback)
    if primary:
        result.setObjectName('primary')
    elif object_name:
        result.setObjectName(object_name)
    return result


def label(text, muted=False, object_name=None):
    result = QLabel(text)
    result.setWordWrap(True)
    if muted:
        result.setObjectName('muted')
    if object_name:
        result.setObjectName(object_name)
    return result


def status_chip(title):
    frame = QFrame()
    frame.setObjectName('chip')
    row = QVBoxLayout(frame)
    row.setContentsMargins(10, 6, 10, 6)
    row.setSpacing(1)
    caption = QLabel(title)
    caption.setObjectName('chipMuted')
    value = QLabel('—')
    value.setObjectName('chipText')
    row.addWidget(caption)
    row.addWidget(value)
    return frame, value


class StudioWindow(QMainWindow):
    def __init__(self, directory):
        super().__init__()
        self.directory = directory
        self.config_path = services.initialize(directory)
        self.control_path = directory / 'host_control.json'
        self.status_path = directory / 'host_status.json'
        self.settings_path = directory / 'desktop_settings.json'
        self.settings = {}
        if self.settings_path.exists():
            self.settings = json.loads(self.settings_path.read_text(encoding='utf-8'))
        self.process = None
        self.sequence = 0
        self.desktop_paused = False
        self.quitting = False
        self.stopping = False
        self.started_at = 0
        self.selected_window = None
        self.windows = []
        self.after_stop = None
        self.control_request = None
        self.pending_request = None
        self.last_status = {}
        self.setWindowTitle(services.APP_NAME + ' — ' + VERSION)
        self.resize(740, 420)
        self.setMinimumSize(620, 360)
        self.setWindowIcon(QIcon(str(services.resource('assets/studio.svg'))))

        body = QWidget()
        self.setCentralWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        banner = QFrame()
        banner.setObjectName('banner')
        banner_row = QHBoxLayout(banner)
        banner_row.setContentsMargins(16, 8, 16, 8)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand = QLabel('Mystic Llama')
        brand.setObjectName('brand')
        sub = QLabel('Controller Studio')
        sub.setObjectName('brandSub')
        brand_col.addWidget(brand)
        brand_col.addWidget(sub)
        banner_row.addLayout(brand_col)
        banner_row.addStretch()
        self.banner_state = QLabel('Stopped')
        self.banner_state.setObjectName('brandSub')
        banner_row.addWidget(self.banner_state)
        outer.addWidget(banner)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(12, 10, 12, 8)
        content_layout.setSpacing(8)

        self.tabs = QTabWidget()
        content_layout.addWidget(self.tabs, 1)
        self.build_home()
        self.build_settings()
        self.build_assignments()
        self.build_support()
        self.tabs.tabBar().moveTab(2, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(label('v' + VERSION, True))
        footer.addStretch()
        footer.addWidget(button('Tray', self.minimize_to_tray, object_name='ghost'))
        footer.addWidget(label('@MysticLlama', True))
        content_layout.addLayout(footer)
        outer.addWidget(content, 1)

        self.build_tray()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)
        self.reload_settings()
        self.refresh_windows()
        self.refresh_home()
        if not self.cfg.get('setup_complete'):
            self.tabs.setCurrentIndex(0)

    @property
    def running(self):
        return self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning

    def read_config(self):
        return json.loads(self.config_path.read_text(encoding='utf-8'))

    def error(self, text):
        QMessageBox.warning(self, 'Controller Studio', str(text))

    def stopped_required(self):
        if self.running:
            self.error('Stop the controller before changing setup or saved settings. Use Assignments for live bindings.')
            return False
        return True

    def add_tab(self, page, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, title)

    def build_home(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.states = {}
        self.chip_frames = {}
        for key, title in [
            ('controller', 'Controller'),
            ('game', 'Game'),
            ('listener', 'Listener'),
            ('state', 'Status'),
        ]:
            frame, value = status_chip(title)
            self.chip_frames[key] = frame
            self.states[key] = value
            chips.addWidget(frame, 1)
        self.states['profile'] = QLabel('')
        layout.addLayout(chips)

        self.notice = label('', True)
        layout.addWidget(self.notice)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.start_button = button('Start', self.start, True)
        controls.addWidget(self.start_button)
        self.pause_button = button('Pause', self.toggle_pause)
        controls.addWidget(self.pause_button)
        self.stop_button = button('Stop', self.stop)
        controls.addWidget(self.stop_button)
        controls.addWidget(button('Reset input', self.recover_input))
        controls.addStretch()
        layout.addLayout(controls)

        self.input_status = label('Press a controller button to see its input.', True)
        layout.addWidget(self.input_status)

        self.setup_toggle = QPushButton('Connection setup ▸')
        self.setup_toggle.setObjectName('setupToggle')
        self.setup_toggle.setCheckable(True)
        layout.addWidget(self.setup_toggle)

        self.setup_details = QFrame()
        self.setup_details.setObjectName('card')
        v = QVBoxLayout(self.setup_details)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(button('Learn controller…', self.calibrate))
        row.addWidget(button('Check bumpers / triggers…', self.check_buttons))
        v.addLayout(row)

        v.addWidget(label('Game window', muted=False, object_name='sectionTitle'))
        self.window_combo = QComboBox()
        v.addWidget(self.window_combo)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(button('Refresh', self.refresh_windows))
        row.addWidget(button('Use this window', self.select_window, True))
        row.addStretch()
        v.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(button('Install / update Razor listener', self.install_listener))
        row.addStretch()
        v.addLayout(row)
        self.listener_path = label('', True)
        v.addWidget(self.listener_path)
        v.addWidget(label('Run the installed listener in Razor with Loop off.', True))
        layout.addWidget(self.setup_details)

        self.setup_toggle.toggled.connect(self._toggle_setup)
        expanded = not self.read_config().get('setup_complete')
        self.setup_toggle.setChecked(expanded)
        self.setup_details.setVisible(expanded)
        self._update_setup_toggle_text(expanded)
        layout.addStretch()
        self.add_tab(page, 'Controller')

    def _toggle_setup(self, checked):
        self.setup_details.setVisible(checked)
        self._update_setup_toggle_text(checked)

    def _update_setup_toggle_text(self, checked):
        self.setup_toggle.setText('Connection setup ▾' if checked else 'Connection setup ▸')

    def build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        card = QFrame()
        card.setObjectName('card')
        form = QFormLayout(card)
        form.setContentsMargins(12, 10, 12, 10)
        form.setSpacing(6)
        form.setHorizontalSpacing(12)

        self.roles = QComboBox()
        self.roles.addItems([
            'Left movement / right cursor',
            'Right movement / left cursor',
            'Left movement / cursor off',
        ])
        form.addRow('Stick roles', self.roles)
        self.show_gump = QCheckBox('Show optional in-game assignment Gump')
        form.addRow(self.show_gump)
        self.global_cursor = QCheckBox('Allow cursor & mouse buttons outside UO')
        form.addRow(self.global_cursor)
        self.close_to_tray = QCheckBox('Keep running in the tray when the window closes')
        self.close_to_tray.setChecked(True)
        form.addRow(self.close_to_tray)

        self.spin = {}
        specs = [
            ('left_deadzone', 'Left deadzone', .05, .6, .01),
            ('right_deadzone', 'Right deadzone', .05, .6, .01),
            ('run_threshold', 'Run threshold', .4, 1, .01),
            ('cursor_pixels_per_second', 'Cursor speed', 100, 2500, 50),
            ('cursor_curve', 'Cursor curve', 1, 3, .1),
        ]
        for key, title, low, high, step in specs:
            spin = QDoubleSpinBox()
            spin.setRange(low, high)
            spin.setSingleStep(step)
            spin.setDecimals(2 if high <= 3 else 0)
            self.spin[key] = spin
            form.addRow(title, spin)
        layout.addWidget(card)
        layout.addWidget(label('Profiles live in Assignments. Caster / Dexxer / Blank / Custom save separately.', True))

        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addWidget(button('Import…', self.import_config))
        actions.addWidget(button('Restart as admin…', self.restart_admin))
        actions.addStretch()
        actions.addWidget(button('Save preferences', self.save_preferences, True))
        layout.addLayout(actions)
        layout.addStretch()
        self.add_tab(page, 'Preferences')

    def build_assignments(self):
        from assignment_editor import AssignmentEditor
        self.assignments = AssignmentEditor(self)
        self.add_tab(self.assignments, 'Assignments')

    def build_support(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)
        layout.addWidget(label(
            'Diagnostics omit character names, paths, tokens and item serials. Review log files before sharing.',
            True,
        ))
        self.diagnostic_text = QPlainTextEdit()
        self.diagnostic_text.setReadOnly(True)
        layout.addWidget(self.diagnostic_text, 1)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(button('Refresh', self.refresh_diagnostics))
        row.addWidget(button('Copy', self.copy_diagnostics, True))
        row.addWidget(button('Open settings folder', self.open_folder))
        row.addStretch()
        layout.addLayout(row)
        self.add_tab(page, 'Support')

    def build_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip(services.APP_NAME)
        menu = QMenu(self)
        for title, callback in [
            ('Open Controller Studio', self.restore),
            ('Pause / resume all input', self.toggle_pause),
            ('Stop controller', self.stop),
            ('Exit', self.quit_app),
        ]:
            action = QAction(title, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.restore() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def minimize_to_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
            self.tray.showMessage(
                'Controller Studio',
                'Running in the tray. Double-click the icon to reopen.',
                QSystemTrayIcon.MessageIcon.Information,
                2200,
            )
        else:
            self.showMinimized()

    def _set_chip(self, key, text, tone='neutral'):
        self.states[key].setText(text)
        mapping = {'good': 'chipGood', 'warn': 'chipWarn', 'bad': 'chipBad', 'neutral': 'chip'}
        self.chip_frames[key].setObjectName(mapping.get(tone, 'chip'))
        self.chip_frames[key].style().unpolish(self.chip_frames[key])
        self.chip_frames[key].style().polish(self.chip_frames[key])

    def reload_settings(self):
        self.cfg = self.read_config()
        inp = self.cfg['input']
        desk = self.cfg['desktop']
        self.roles.setCurrentIndex(
            2 if inp.get('mouse_stick') == 'off' else 1 if inp.get('movement_stick') == 'right' else 0
        )
        self.global_cursor.setChecked(desk.get('global_cursor', True))
        self.show_gump.setChecked(self.cfg['razor'].get('show_gump', False))
        for name, spin in self.spin.items():
            spin.setValue((desk if name in ('cursor_pixels_per_second', 'cursor_curve') else inp)[name])
        self.close_to_tray.setChecked(self.settings.get('close_to_tray', True))
        self.listener_path.setText(
            self.settings.get('listener_path', 'Listener has not been installed by this application yet.')
        )

    def refresh_home(self, status=None):
        cfg = self.read_config()
        status = status or {}
        controller_text = status.get('controller') or (
            cfg.get('device_name_contains') if cfg.get('setup_complete') else 'Setup required'
        ) or 'Waiting'
        titles = cfg['focus'].get('window_title_contains', [])
        game_text = (titles[0] if titles else 'Choose window') + (' · focused' if status.get('game_focus') else '')
        if len(game_text) > 34:
            game_text = game_text[:31] + '…'
        listener_text = (
            'Connected' if status.get('listener')
            else 'Waiting' if self.running
            else 'Not connected'
        )
        state_text = (
            'Paused' if self.running and self.desktop_paused
            else 'Game paused' if self.running and status.get('paused')
            else 'Running' if self.running
            else 'Stopped'
        )
        self.states['profile'].setText(status.get('profile', cfg.get('active_assignment_profile', 'Custom')))
        self._set_chip(
            'controller', controller_text,
            'good' if status.get('controller') or cfg.get('setup_complete') else 'warn',
        )
        self._set_chip('game', game_text, 'good' if titles and status.get('game_focus') else 'warn' if titles else 'bad')
        self._set_chip(
            'listener', listener_text,
            'good' if status.get('listener') else 'warn' if self.running else 'neutral',
        )
        self._set_chip(
            'state', state_text,
            'good' if self.running and not self.desktop_paused else 'warn' if self.running else 'neutral',
        )
        self.banner_state.setText(state_text + ' · ' + VERSION)

        self.start_button.setEnabled(not self.running)
        self.stop_button.setEnabled(self.running and not self.stopping)
        self.pause_button.setEnabled(self.running and not self.stopping)
        self.pause_button.setText('Resume' if self.desktop_paused else 'Pause')

        if status.get('mapping_issues'):
            text = 'Button inputs look wrong. Open Connection setup → Check bumpers / triggers. ' + next(
                iter(status['mapping_issues'].values())
            )
            if not self.setup_toggle.isChecked():
                self.setup_toggle.setChecked(True)
        elif status.get('error'):
            text = 'Controller stopped: ' + status['error']
        elif status.get('privilege_warning'):
            text = 'UO is elevated. Stop, then Preferences → Restart as administrator.'
        elif status.get('client_mismatch'):
            text = 'Listener is in another UO process. Start it in the selected client.'
        elif self.running and status.get('pause_reason') == 'application':
            text = 'All input paused. Resume here or from the tray.'
        elif self.running and status.get('pause_reason') == 'gump':
            text = 'Game actions paused in the Gump. Apply or Cancel, then Resume in-game.'
        elif self.running and status.get('game_focus') and not status.get('armed'):
            text = 'Center the movement stick once to arm movement. Release held buttons first.'
        elif self.running and status.get('game_focus') and status.get('armed') and not status.get('game_armed'):
            text = 'Release game buttons and center the movement stick to arm game actions.'
        elif self.running and not status.get('controller'):
            text = 'Waiting for controller. Reconnect it, then release all controls.'
        elif self.running and not status.get('listener'):
            text = 'Start the installed listener in Razor Enhanced for game actions.'
        elif self.running and not status.get('game_focus'):
            text = 'Desktop cursor available when enabled. Game actions wait for the selected UO window.'
        else:
            text = 'Ready.' if cfg.get('setup_complete') and titles else 'Open Connection setup to get started.'
        if self.running and status.get('runtime', {}).get('pending_target'):
            text = 'Waiting for a spell/item target. Resolve it, or Reset input for controller-owned work.'
        self.notice.setText(text)

        if hasattr(self, 'assignments'):
            self.assignments.show_live_input(status)
        last = status.get('last_input', {})
        if last:
            from assignment_editor import action_label, LABELS
            self.input_status.setText(
                'Last: ' + LABELS.get(last.get('control'), last.get('control', ''))
                + ' → ' + action_label(cfg, last.get('action', 'unbound'))
                + ' · ' + (last.get('blocked_reason') or 'ok')
            )
        mouse = status.get('mouse_result', {})
        if mouse and cfg['actions'].get(last.get('action'), {}).get('type') == 'mouse_button':
            self.input_status.setText(
                self.input_status.text()
                + ' · Win '
                + ('ok' if mouse.get('accepted') else 'REJECTED')
                + ' '
                + ('press' if mouse.get('down') else 'release')
            )
        result = status.get('hotkey_result', {})
        if result and cfg['actions'].get(last.get('action'), {}).get('type') == 'hotkey':
            self.input_status.setText(self.input_status.text() + ' · ' + result.get('detail', ''))
        ack = status.get('last_ack', {})
        if ack and ack.get('status') != 'ok' and ack.get('action') == last.get('action'):
            self.input_status.setText(self.input_status.text() + ' · Razor: ' + ack.get('detail', ''))

    def calibrate(self):
        if not self.stopped_required():
            return
        try:
            from calibration import CalibrationDialog
            dialog = CalibrationDialog(self.read_config(), self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                cfg = dialog.result_config
                if not self.cfg.get('setup_complete'):
                    from controller_bridge import assignment_template
                    for name in ('Caster', 'Dexxer', 'Blank'):
                        cfg['assignment_profiles'][name] = assignment_template(cfg, name)
                    cfg['active_assignment_profile'] = 'Blank'
                    cfg['layers'] = copy.deepcopy(cfg['assignment_profiles']['Blank'])
                save_config(self.config_path, cfg)
                self.reload_settings()
                self.refresh_home()
                QMessageBox.information(
                    self,
                    'Controller learned',
                    'Controller saved. Choose your game window next, then pick a profile in Assignments.',
                )
        except Exception as exc:
            self.error(exc)

    def refresh_windows(self):
        try:
            self.windows = services.list_game_windows()
            self.window_combo.clear()
            for item in self.windows:
                self.window_combo.addItem(item['title'] + (' [admin]' if item['elevated'] else ''), item)
            if not self.windows:
                self.window_combo.addItem('No UO window found. Log in, then Refresh.', None)
        except Exception as exc:
            self.error(exc)

    def select_window(self):
        if not self.stopped_required():
            return
        selected = self.window_combo.currentData()
        if not selected:
            self.error('Log into UO and refresh the window list.')
            return
        cfg = self.read_config()
        cfg['focus'].update(
            require_focus=True,
            window_title_contains=[selected['title']],
            process_names=[selected['process']],
            selected_pid=selected['pid'],
        )
        save_config(self.config_path, cfg)
        self.selected_window = selected
        self.reload_settings()
        self.refresh_home()

    def install_listener(self):
        if not self.stopped_required():
            return
        folder = QFileDialog.getExistingDirectory(self, 'Select your Razor Enhanced scripts folder')
        if not folder:
            return
        try:
            path = services.install_listener(self.directory, folder)
            self.settings['listener_path'] = str(path)
            save_config(self.settings_path, self.settings)
            self.reload_settings()
            QApplication.clipboard().setText(str(path))
            QMessageBox.information(
                self,
                'Listener installed',
                'Path copied. In Razor Enhanced, add this script and press Play. Loop OFF.\n\n' + str(path),
            )
        except Exception as exc:
            self.error(exc)

    def check_buttons(self):
        if self.running:
            self.after_stop = lambda: self.run_button_check(True)
            self.stop()
        else:
            self.run_button_check(False)

    def run_button_check(self, restart):
        try:
            from calibration import CalibrationDialog
            dialog = CalibrationDialog(self.read_config(), self, buttons_only=True)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                save_config(self.config_path, dialog.result_config)
                self.reload_settings()
                self.assignments.reload()
                self.notice.setText('Button inputs corrected. Assignments and sticks preserved.')
        except Exception as exc:
            self.error(exc)
        if restart:
            self.start()

    def import_config(self):
        if not self.stopped_required():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Import your existing bindings.json', '', 'JSON files (*.json)')
        if not path:
            return
        try:
            from controller_bridge import migrate_controller_ui
            cfg = load_config(Path(path))
            migrate_controller_ui(cfg)
            cfg['setup_complete'] = bool(cfg.get('device_guid') or cfg.get('device_name_contains'))
            cfg['token'] = self.read_config()['token']
            cfg['bridge']['mode'] = 'socket'
            cfg['focus']['require_focus'] = True
            cfg['focus']['window_title_contains'] = []
            backup = self.directory / ('bindings.before-import-' + str(time.time_ns()) + '.json')
            backup.write_bytes(self.config_path.read_bytes())
            save_config(self.config_path, cfg)
            self.reload_settings()
            self.refresh_home()
            QMessageBox.information(
                self,
                'Imported',
                'Assignments and calibration imported. Reselect your UO window and install this version’s listener before starting.',
            )
        except Exception as exc:
            self.error(exc)

    def save_preferences(self):
        if not self.stopped_required():
            return
        try:
            cfg = self.read_config()

            class KeyValidator:
                def key(self, name):
                    return name

            changes = [{'setting': {'name': name, 'value': spin.value()}} for name, spin in self.spin.items()]
            roles = [('left', 'right'), ('right', 'left'), ('left', 'off')][self.roles.currentIndex()]
            changes += [
                {'setting': {'name': name, 'value': value}}
                for name, value in [
                    ('movement_stick', roles[0]),
                    ('mouse_stick', roles[1]),
                    ('global_cursor', self.global_cursor.isChecked()),
                    ('show_gump', self.show_gump.isChecked()),
                ]
            ]
            cfg = configure(cfg, {'changes': changes, 'expected_revision': cfg.get('revision', 0)}, KeyValidator())
            save_config(self.config_path, cfg)
            self.settings['close_to_tray'] = self.close_to_tray.isChecked()
            save_config(self.settings_path, self.settings)
            self.reload_settings()
            self.refresh_home()
            self.notice.setText('Preferences saved.')
        except Exception as exc:
            self.error(exc)

    def start(self):
        if self.running:
            return
        cfg = self.read_config()
        if not cfg.get('setup_complete') or not cfg['focus'].get('window_title_contains'):
            self.tabs.setCurrentIndex(0)
            self.setup_toggle.setChecked(True)
            self.error('Learn your controller and choose a UO window first.')
            return
        matches = [
            item for item in services.list_game_windows()
            if item['title'] in cfg['focus']['window_title_contains']
            and item['process'].lower() in [name.lower() for name in cfg['focus'].get('process_names', [])]
        ]
        if len(matches) != 1:
            self.tabs.setCurrentIndex(0)
            self.setup_toggle.setChecked(True)
            self.refresh_windows()
            self.error('The saved game window is unavailable or ambiguous. Select your character window again.')
            return
        cfg['focus']['selected_pid'] = matches[0]['pid']
        save_config(self.config_path, cfg)
        self.desktop_paused = False
        self.stopping = False
        self.started_at = time.time()
        self.write_control()
        self.status_path.unlink(missing_ok=True)
        command = services.launch_arguments(
            '--host', '--config', str(self.config_path),
            '--control', str(self.control_path), '--status', str(self.status_path),
        )
        self.process = QProcess(self)
        self.process.setProgram(command[0])
        self.process.setArguments(command[1:])
        self.process.setWorkingDirectory(str(self.directory))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_process_output)
        self.process.errorOccurred.connect(
            lambda error: self.notice.setText('Could not run controller: ' + self.process.errorString())
            if error == QProcess.ProcessError.FailedToStart else None
        )
        self.process.finished.connect(self.host_finished)
        self.process.start()
        self.tabs.setCurrentIndex(0)
        self.refresh_home()

    def read_process_output(self):
        data = bytes(self.process.readAllStandardOutput()).decode('utf-8', errors='replace')
        if data:
            with (self.directory / 'application.log').open('a', encoding='utf-8') as stream:
                stream.write(data)

    def write_control(self, stop=False):
        save_config(self.control_path, {
            'sequence': self.sequence,
            'paused': self.desktop_paused,
            'stop': stop,
            'heartbeat': time.time(),
            'request': self.control_request,
        })

    def apply_assignments(self, payload, callback):
        if self.running:
            if self.pending_request:
                callback({'status': 'error', 'detail': 'Wait for the previous request to finish.'})
                return
            self.control_request = {'id': uuid.uuid4().hex, 'kind': 'apply', 'payload': payload}
            self.pending_request = {
                'id': self.control_request['id'],
                'callback': callback,
                'deadline': time.monotonic() + 5,
            }
            self.sequence += 1
            self.write_control()
        else:
            try:
                from assignment_editor import Keys
                cfg = configure(self.read_config(), payload, Keys())
                save_config(self.config_path, cfg)
                self.reload_settings()
                callback({'status': 'ok'})
            except Exception as exc:
                callback({'status': 'error', 'detail': str(exc)})

    def recover_input(self):
        if not self.running:
            self.notice.setText('Start the controller first.')
            return
        if self.pending_request:
            self.notice.setText('Wait for the assignment update to finish.')
            return
        self.desktop_paused = False
        self.control_request = {'id': uuid.uuid4().hex, 'kind': 'recover'}

        def complete(result):
            text = (
                'Input reset. Click UO, release buttons and center the movement stick once.'
                if result.get('status') == 'ok'
                else result.get('detail', 'Recovery not confirmed')
            )
            self.assignments.feedback.setText(text)
            self.notice.setText(text)

        self.pending_request = {
            'id': self.control_request['id'],
            'callback': complete,
            'deadline': time.monotonic() + 5,
        }
        self.sequence += 1
        self.write_control()

    def check_request(self, status):
        if not self.pending_request:
            return
        reply = status.get('desktop_reply', {})
        if reply.get('id') == self.pending_request['id']:
            pending = self.pending_request
            self.pending_request = None
            self.control_request = None
            pending['callback'](reply)
        elif time.monotonic() > self.pending_request['deadline']:
            pending = self.pending_request
            self.pending_request = None
            self.control_request = None
            pending['callback']({
                'status': 'error',
                'detail': 'Update was not confirmed. Reload saved assignments before retrying.',
            })

    def toggle_pause(self):
        if self.running and not self.stopping:
            self.desktop_paused = not self.desktop_paused
            self.sequence += 1
            self.write_control()
            self.refresh_home()

    def stop(self):
        if self.running and not self.stopping:
            self.stopping = True
            self.write_control(True)
            self.notice.setText('Stopping…')
            process = self.process
            QTimer.singleShot(
                4500,
                lambda: process.kill() if process.state() != QProcess.ProcessState.NotRunning else None,
            )

    def host_finished(self, code, status):
        intentional = self.stopping
        self.stopping = False
        if self.pending_request:
            pending = self.pending_request
            self.pending_request = None
            self.control_request = None
            pending['callback']({
                'status': 'error',
                'detail': 'Controller stopped before confirmation. Reload saved assignments.',
            })
        self.reload_settings()
        self.refresh_home()
        if code and not intentional:
            detail = 'The controller stopped unexpectedly. Check Support and controller_bridge.log.'
            try:
                detail = json.loads(self.status_path.read_text(encoding='utf-8')).get('error', detail)
            except (OSError, ValueError):
                pass
            self.notice.setText(detail)
        if self.quitting:
            QApplication.instance().quit()
        callback = self.after_stop
        self.after_stop = None
        if callback and not self.quitting:
            QTimer.singleShot(0, callback)

    def tick(self):
        if self.running:
            if not self.stopping:
                self.write_control()
            try:
                status = json.loads(self.status_path.read_text(encoding='utf-8'))
                if status.get('at', 0) >= self.started_at:
                    self.last_status = status
                    self.check_request(status)
                    self.refresh_home(status)
            except (OSError, ValueError):
                pass
        if self.pending_request:
            self.check_request(self.last_status)
        if self.tabs.currentIndex() == 3:
            self.refresh_diagnostics()

    def refresh_diagnostics(self):
        try:
            self.diagnostic_text.setPlainText(services.diagnostics(self.directory))
        except Exception as exc:
            self.diagnostic_text.setPlainText(str(exc))

    def copy_diagnostics(self):
        self.refresh_diagnostics()
        QApplication.clipboard().setText(self.diagnostic_text.toPlainText())

    def open_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.directory)))

    def restart_admin(self):
        if not self.stopped_required():
            return
        if host_elevated():
            QMessageBox.information(self, 'Already elevated', 'Controller Studio is already running as administrator.')
            return
        try:
            services.elevate(self.directory)
            self.quitting = True
            QApplication.instance().quit()
        except Exception as exc:
            self.error(exc)

    def quit_app(self):
        self.quitting = True
        if self.running:
            self.stop()
        else:
            QApplication.instance().quit()

    def closeEvent(self, event):
        if self.running and self.close_to_tray.isChecked() and QSystemTrayIcon.isSystemTrayAvailable() and not self.quitting:
            event.ignore()
            self.minimize_to_tray()
        elif self.running:
            event.ignore()
            self.quit_app()
        else:
            event.accept()
            QApplication.instance().quit()


def main(directory):
    app = QApplication(sys.argv[:1])
    app.setApplicationName(services.APP_NAME)
    app.setOrganizationName('MysticLlama')
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    directory.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(directory / 'desktop.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(3000):
        QMessageBox.information(
            None,
            'Already open',
            'Controller Studio is already open. Use its tray icon to restore it.',
        )
        return 0
    try:
        window = StudioWindow(directory)
        window.show()
    except Exception:
        text = traceback.format_exc()
        (directory / 'application-error.log').write_text(text, encoding='utf-8')
        QMessageBox.critical(
            None,
            'Could not open Controller Studio',
            'Setup could not open. Details were saved in:\n' + str(directory / 'application-error.log'),
        )
        return 1

    def shutdown():
        if window.running:
            window.write_control(True)
            if not window.process.waitForFinished(2500):
                window.process.kill()
                window.process.waitForFinished(1000)
        lock.unlock()

    app.aboutToQuit.connect(shutdown)
    return app.exec()
