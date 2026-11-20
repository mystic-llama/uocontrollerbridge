"""Desktop binding editor. Drafts commit through the host's validated transaction API."""
import copy
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox, QCheckBox,
    QLineEdit, QKeySequenceEdit, QSpinBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QStackedWidget, QFrame, QSizePolicy,
)
from controller_bridge import configure, migrate_controller_ui
from spell_catalog import SCHOOL_ORDER, SPELL_CATALOG, get_spell
from hotkeys import normalize_hotkey, MODIFIERS
from controller_diagram import ControllerDiagram

LABELS = {
    'south': 'B / bottom', 'east': 'A / right', 'west': 'Y / left', 'north': 'X / top',
    'lb': 'L bumper', 'rb': 'R bumper', 'lt': 'L trigger', 'rt': 'R trigger',
    'ls': 'Left stick click', 'rs': 'Right stick click',
    'dpad_up': 'D-pad up', 'dpad_down': 'D-pad down', 'dpad_left': 'D-pad left', 'dpad_right': 'D-pad right',
    'back': 'Select / minus', 'start': 'Start / plus', 'p1': 'Rear P1', 'p2': 'Rear P2',
}


def action_label(cfg, name):
    a = cfg['actions'].get(name, {})
    if a.get('type') == 'cast':
        return a['spell'] + ' · ' + a.get('target', 'none').replace('none', 'manual')
    if a.get('type') == 'hotkey':
        return 'Shortcut: ' + '+'.join(a['keys'])
    return a.get('label') or {
        'unbound': 'Unassigned',
        'mouse_left': 'Left mouse · click / drag',
        'mouse_right': 'Right mouse · click / drag',
    }.get(name, name.replace('_', ' ').title())


class Keys:
    def key(self, name):
        return normalize_hotkey(name)[0] if name not in MODIFIERS else name


class AssignmentDraft:
    def __init__(self, cfg):
        self.original = copy.deepcopy(cfg)
        migrate_controller_ui(self.original)
        self.cfg = copy.deepcopy(self.original)
        self.changes = {}

    def stage(self, change, key):
        self.cfg = configure(self.cfg, change, Keys())
        self.changes[key] = copy.deepcopy(change)

    def profile(self, name):
        self.cfg = configure(copy.deepcopy(self.original), {'assignment_profile': name}, Keys())
        self.changes = {('profile',): {'assignment_profile': name}}

    def payload(self):
        return {'changes': list(self.changes.values()), 'expected_revision': self.original.get('revision', 0)}


class AssignmentEditor(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.loading = False
        self.pending = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(QLabel('Profile'))
        self.profiles = QComboBox()
        self.profiles.addItems(['Blank', 'Caster', 'Dexxer', 'Custom'])
        self.profiles.setMinimumWidth(110)
        toolbar.addWidget(self.profiles)
        toolbar.addStretch()
        self.list_view = QCheckBox('List view')
        toolbar.addWidget(self.list_view)
        outer.addLayout(toolbar)

        content = QHBoxLayout()
        content.setSpacing(10)
        self.views = QStackedWidget()
        self.diagram = ControllerDiagram()
        self.diagram.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.views.addWidget(self.diagram)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Button', 'Assignment'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(180)
        self.views.addWidget(self.table)
        content.addWidget(self.views, 5)

        panel = QFrame()
        panel.setObjectName('card')
        panel.setMinimumWidth(250)
        panel.setMaximumWidth(320)
        form = QVBoxLayout(panel)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(6)

        self.selected = QLabel('Choose a button')
        self.selected.setObjectName('sectionTitle')
        form.addWidget(self.selected)

        self.mode = QComboBox()
        self.mode.addItems(['Native action', 'Spell', 'Keyboard shortcut'])
        form.addWidget(self.mode)

        self.pages = QStackedWidget()
        form.addWidget(self.pages)

        native = QWidget()
        v = QVBoxLayout(native)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.category = QComboBox()
        for title, key in [
            ('All actions', 'all'), ('Mouse / targeting / other', 'general'),
            ('Pets', 'pets'), ('Items / hands', 'items'), ('Agents', 'agents'),
        ]:
            self.category.addItem(title, key)
        v.addWidget(self.category)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Find an action…')
        v.addWidget(self.search)
        self.actions = QComboBox()
        v.addWidget(self.actions)
        v.addStretch()
        self.pages.addWidget(native)

        spell = QWidget()
        f = QFormLayout(spell)
        f.setContentsMargins(0, 0, 0, 0)
        f.setSpacing(6)
        f.setHorizontalSpacing(8)
        self.school = QComboBox()
        self.school.addItems(SCHOOL_ORDER)
        f.addRow('School', self.school)
        self.spell_search = QLineEdit()
        self.spell_search.setPlaceholderText('Find a spell…')
        f.addRow(self.spell_search)
        self.spell = QComboBox()
        f.addRow('Spell', self.spell)
        self.target = QComboBox()
        self.target.addItems(['Manual target', 'Self', 'Last target'])
        f.addRow('Target', self.target)
        self.recovery = QSpinBox()
        self.recovery.setRange(0, 10000)
        self.recovery.setSuffix(' ms')
        f.addRow('Recovery', self.recovery)
        self.pages.addWidget(spell)

        hotkey = QWidget()
        hv = QVBoxLayout(hotkey)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.setSpacing(6)
        hint = QLabel('Click recorder, then press the chord already bound in Razor / ClassicUO.')
        hint.setObjectName('muted')
        hint.setWordWrap(True)
        hv.addWidget(hint)
        self.recorder = QKeySequenceEdit()
        self.recorder.setMaximumSequenceLength(1)
        self.recorder.setClearButtonEnabled(True)
        self.recorder.setFinishingKeyCombinations([])
        hv.addWidget(self.recorder)
        self.recorded = QLabel('No shortcut recorded')
        self.recorded.setObjectName('muted')
        self.recorded.setWordWrap(True)
        hv.addWidget(self.recorded)
        hv.addStretch()
        self.pages.addWidget(hotkey)

        self.apply_button = QPushButton('Apply')
        self.apply_button.setObjectName('primary')
        self.apply_button.clicked.connect(self.apply)
        form.addWidget(self.apply_button)
        form.addStretch()
        content.addWidget(panel, 3)
        outer.addLayout(content, 1)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.feedback = QLabel('')
        self.feedback.setObjectName('muted')
        self.feedback.setWordWrap(True)
        foot.addWidget(self.feedback, 1)
        reload = QPushButton('Reload')
        reload.clicked.connect(self.reload)
        foot.addWidget(reload)
        recover = QPushButton('Reset input')
        recover.clicked.connect(owner.recover_input)
        foot.addWidget(recover)
        outer.addLayout(foot)

        self.mode.currentIndexChanged.connect(self.pages.setCurrentIndex)
        self.table.currentCellChanged.connect(self.select_control)
        self.category.currentIndexChanged.connect(self.fill_actions)
        self.search.textChanged.connect(self.fill_actions)
        self.school.currentTextChanged.connect(self.fill_spells)
        self.spell_search.textChanged.connect(self.fill_spells)
        self.spell.currentIndexChanged.connect(self.spell_changed)
        self.recorder.keySequenceChanged.connect(self.record_change)
        self.list_view.toggled.connect(lambda enabled: self.views.setCurrentIndex(1 if enabled else 0))
        self.diagram.controlSelected.connect(self.select_by_name)
        self.profiles.currentTextChanged.connect(self.change_profile)
        self.reload()

    def reload(self):
        if self.pending:
            return
        self.loading = True
        self.draft = AssignmentDraft(self.owner.read_config())
        self.profiles.setCurrentText(self.draft.cfg.get('active_assignment_profile', 'Custom'))
        self.loading = False
        self.fill_actions()
        self.fill_spells()
        self.render_table()
        self.feedback.setText('Select a button, choose an action, then Apply.')

    def change_profile(self, name):
        if self.loading:
            return
        if self.pending:
            self.loading = True
            self.profiles.setCurrentText(self.draft.cfg['active_assignment_profile'])
            self.loading = False
            return
        self.draft.profile(name)
        self.render_table()
        self.feedback.setText('Previewing ' + name + '. Apply saves this profile with the selected button.')

    def row(self):
        return next((r for r in self.draft.cfg['layers'] if r['name'] == 'base'), {'bindings': {}})

    def select_by_name(self, name):
        if name in self.controls:
            self.table.setCurrentCell(self.controls.index(name), 0)
            self.select_control()

    def show_live_input(self, status):
        self.diagram.set_state(pressed=status.get('active_controls', []))

    def update_diagram(self):
        cfg = self.draft.cfg
        roles = []
        for side in ('left', 'right'):
            roles.append(
                'Movement' if cfg['input'].get('movement_stick', 'left') == side
                else 'Cursor' if cfg['input'].get('mouse_stick', 'right') == side
                else 'Stick click'
            )
        bindings = {
            name: action_label(cfg, self.row()['bindings'].get(name, {}).get('action', 'unbound'))
            for name in self.controls
        }
        self.diagram.set_state(available=self.controls, selected=self.control(), bindings=bindings, roles=roles)

    def render_table(self, *args):
        if self.loading:
            return
        selected = self.control() if hasattr(self, 'controls') else None
        self.controls = sorted(
            self.draft.cfg['presets'][self.draft.cfg['preset']]['controls'],
            key=lambda n: list(LABELS).index(n) if n in LABELS else 99,
        )
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.controls))
        for index, name in enumerate(self.controls):
            action = self.row()['bindings'].get(name, {}).get('action', 'unbound')
            text = action_label(self.draft.cfg, action)
            self.table.setItem(index, 0, QTableWidgetItem(LABELS.get(name, name)))
            self.table.setItem(index, 1, QTableWidgetItem(text))
        self.table.blockSignals(False)
        index = self.controls.index(selected) if selected in self.controls else 0
        if self.controls:
            self.table.setCurrentCell(index, 0)
            self.select_control()

    def control(self):
        row = self.table.currentRow()
        return self.controls[row] if hasattr(self, 'controls') and 0 <= row < len(self.controls) else None

    def fill_actions(self, *args):
        if not hasattr(self, 'draft'):
            return
        previous = self.actions.currentData()
        self.actions.clear()
        query = self.search.text().strip().lower()
        category = self.category.currentData()
        for name, a in sorted(self.draft.cfg['actions'].items(), key=lambda pair: action_label(self.draft.cfg, pair[0])):
            if a.get('type') in ('cast', 'hotkey') or a.get('type') == 'equip_cycle' and not a.get('serials'):
                continue
            text = action_label(self.draft.cfg, name)
            if (category == 'all' or a.get('category', 'general') == category) and query in text.lower():
                self.actions.addItem(text, name)
        i = self.actions.findData(previous)
        if i >= 0:
            self.actions.setCurrentIndex(i)

    def fill_spells(self, *args):
        previous = self.spell.currentText()
        self.spell.blockSignals(True)
        self.spell.clear()
        query = self.spell_search.text().lower()
        for a in SPELL_CATALOG[self.school.currentText()]:
            if query in a['name'].lower():
                self.spell.addItem(a['name'])
        i = self.spell.findText(previous)
        if i >= 0:
            self.spell.setCurrentIndex(i)
        self.spell.blockSignals(False)
        self.spell_changed()

    def spell_changed(self, *args):
        spell = get_spell(self.school.currentText(), self.spell.currentText()) if self.spell.currentText() else None
        for index in (1, 2):
            self.target.model().item(index).setEnabled(bool(spell and spell['auto_target']))
        if not spell or not spell['auto_target']:
            self.target.setCurrentIndex(0)
        if spell:
            self.recovery.setValue(spell['recovery_ms'])

    def record_change(self, sequence):
        text = sequence.toString(QKeySequence.SequenceFormat.PortableText)
        try:
            self.recorded.setText('Will send: ' + '+'.join(normalize_hotkey(text)))
        except ValueError as exc:
            self.recorded.setText(str(exc))

    def select_control(self, *args):
        name = self.control()
        if not name:
            return
        self.selected.setText(LABELS.get(name, name))
        self.update_diagram()
        action = self.row()['bindings'].get(name, {}).get('action', 'unbound')
        a = self.draft.cfg['actions'].get(action, {})
        if a.get('type') == 'cast':
            self.mode.setCurrentIndex(1)
            self.spell_search.clear()
            self.school.setCurrentText(a['school'])
            self.fill_spells()
            self.spell.setCurrentText(a['spell'])
            self.target.setCurrentIndex({'none': 0, 'self': 1, 'last': 2}.get(a.get('target'), 0))
            self.recovery.setValue(a.get('recovery_ms', 0))
        elif a.get('type') == 'hotkey':
            self.mode.setCurrentIndex(2)
            self.recorder.setKeySequence(QKeySequence('+'.join(a['keys'])))
        else:
            self.mode.setCurrentIndex(0)
            self.search.clear()
            self.category.setCurrentIndex(0)
            self.fill_actions()
            self.actions.setCurrentIndex(self.actions.findData(action))

    def apply(self):
        if self.pending:
            return
        try:
            control = self.control()
            if not control:
                raise ValueError('Select a controller button')
            layer = 'base'
            data = {'control': control, 'layer': layer, 'action': 'unbound'}
            if self.mode.currentIndex() == 0:
                if self.actions.currentData() is None:
                    raise ValueError('Select an action')
                data['action'] = self.actions.currentData()
            elif self.mode.currentIndex() == 1:
                data['cast'] = {
                    'school': self.school.currentText(),
                    'spell': self.spell.currentText(),
                    'target': ('none', 'self', 'last')[self.target.currentIndex()],
                    'recovery_ms': self.recovery.value(),
                }
            else:
                data['keys'] = '+'.join(normalize_hotkey(
                    self.recorder.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                ))
            self.draft.stage({'binding': data}, ('binding', layer, control))
            self.pending = True
            self.setEnabled(False)
            self.apply_button.setEnabled(False)
            self.feedback.setText('Applying…')
            self.owner.apply_assignments(self.draft.payload(), self.applied)
        except Exception as exc:
            self.pending = False
            self.setEnabled(True)
            self.apply_button.setEnabled(True)
            self.feedback.setText('Not applied: ' + str(exc))

    def applied(self, result):
        self.pending = False
        self.setEnabled(True)
        self.apply_button.setEnabled(True)
        if result.get('status') == 'ok':
            self.reload()
            self.feedback.setText('Saved and applied. Focus UO and center the movement stick once.')
        else:
            self.feedback.setText('Not applied: ' + result.get('detail', 'No confirmation. Reload before retrying.'))
