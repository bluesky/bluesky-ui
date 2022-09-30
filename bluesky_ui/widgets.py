from qtpy import QtWidgets
from bluesky.run_engine import Dispatcher
from bluesky.callbacks.best_effort import BestEffortCallback
from event_model import DocumentNames
from functools import partial
from PyQt5.QtGui import QValidator
from PyQt5.QtCore import Qt
from pyqtgraph.parametertree import ParameterTree

from mily.widgets import (vstacked_label, hstacked_label, MText, MISpin,
                          MFSpin, MComboBox, MCheckBox, MSelector,
                          MetaDataEntry)

from mily.table_interface import MTableInterfaceWidget


def merge_parameters(widget_iter):
    return {k: v
            for w in widget_iter
            for k, v in w.get_parameters().items()
            if w.isEnabled()}


class UniqueValidator(QValidator):
    '''A ``QValidator`` that ensures that the string is not in invalid_list.'''

    def __init__(self, invalid_list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.invalid_list = invalid_list

    # 'validate' function that checks uniqueness
    def validate(self, inputStr, pos):
        if inputStr in self.invalid_list:
            return (self.Invalid, inputStr, pos)
        else:
            return (self.Acceptable, inputStr, pos)

    def fixup(self, text):
        '''Modifes 'text' in-situ in order to attempt to make it unique'''
        # TODO : fill out this method, an example can be found at
        # https://stackoverflow.com/questions/34055174/qvalidator-fixup-issue


def table_unique_mtext_factory(name, parent, table):
    '''An 'Editor Factory' for an ``MText`` widget to ensure unique values.

    This is designed to be used in an ``MTableInterfaceWidget`` where it
    ensures that any entered text does not match any values from the same
    column. The ``MTableInterfaceWidget`` is passed in via the 'table'
    argument.
    '''

    index = table.tableView.selectionModel().selectedIndexes()[0]
    cur_row = index.row()
    column = index.column()
    model = table.tableView.model()
    invalid_list = [model.item(row, column).data(Qt.DisplayRole)
                    for row in range(model.rowCount())
                    if row != cur_row]

    editor = MText(name, parent=parent)
    editor.setValidator(UniqueValidator(invalid_list, parent))

    return editor


def table_mispin_factory(name, parent, minimum=None, maximum=None):
    '''An 'Editor Factory' for an ``MISpin`` in a table interface.

    This simply adds the capability to use ``functools.partial`` to pass in
    minimum and/or maximum values at definition time that will be used at
    instantiation time.
    '''

    return MISpin(name, parent=parent, minimum=minimum, maximum=maximum)


def table_mselector_factory(name, parent, option_list, vertical):
    '''An 'Editor Factory' for an ``MSelector`` in a table interface.

    This simply adds the capability to use ``functools.partial`` to pass in
    a 'detectors' list at definition time that will be used at instantiation
    time.
    '''

    return MSelector(name, parent=parent, option_list=option_list,
                     vertical=vertical)


def table_mcombobox_factory(name, parent, option_list, table, key):
    '''An 'Editor factory' for an ``MComboBox``for use with a table interface.

    This is designed to be used in place of an ``MComboBox`` 'editor' in an
    ``MTableInterfaceWidget``'s ``editor_map``. It will ensure that any 'item'
    selected in an existing row is removed from the list of 'items' to be
    selected, thereby guaranteeing uniqueness. It finds any existing selected
    objects by calling ``table.get_parameters() and searching for any times in
    the returned list if dicts who's key is 'key'. The recommended usage in the
    ``editor_map`` attribute dictionary defined in the table is to wrap this in
    a ``functools.partial`` call, as seen below.

    ..code-block:: python

    functools.partial(table_mcombobox_factory,
                      option_list = some_list',
                      table = self,
                      key = 'some_key')

    parameters
    ----------
    name : str
        The name parameter to pass into the editor to be instantiated.
    parent : object
        The parent object to pass into the editor to be instantiated.
    option_list : The list of items to potentially include in the dropdown list
    table : object
        The 'table' object that calls this editor factory.
    key : str
        The 'key' value that should be used to extract out any previously
        selected items from the parameters returned by ``table`` and remove
        them from the option list.
    '''
    # determine which motors to include as drop-down list options
    selected_items = [item.get(key)
                      for item in table.get_parameters()[table._name]
                      if item.get(key)]
    items = {getattr(item, 'name', str(item)): item
             for item in option_list
             if item not in selected_items}
    return MComboBox(name, parent=parent, items=items)


def bs_snake_editor_factory(name, parent, table):
    '''A function that returns an editor widget for the 'snake' parameter

    This returns a single editor, the exact editor being ``None`` if
    if the current selected row == 0 or a checkbox if it is not.

    Parameters
    ----------
    name: str
        The name to be given to the widget.
    parent: Qt.QWidget
        The parent object of the editor
    table : object
        The 'table' object that defines this editor factory.
    '''
    index = table.tableView.selectionModel().selectedIndexes()[0]

    if index.row() == 0:
        editor = None
    else:
        editor = MCheckBox

    if editor is not None:
        editor = editor(name, parent=parent)

    return editor


def bs_motor_position_mfspin_factory(name, parent, table):
    '''Used to open an MFSpin editor with limits based on the 'motor' column

    This returns an instantiated MFSpin editor, with the limits set by the
    motor selected in the 'motor' column (if they are set at the IOC level)

    Parameters
    ----------
    name: str
        The name to be given to the widget.
    parent: Qt.QWidget
        The parent object of the editor
    table : object
        The 'table' object that defines this editor factory.
    '''
    index = table.tableView.selectionModel().selectedIndexes()[0]

    motor = table.get_row_parameters(index.row())[table._name].get('motor',
                                                                   None)
    # extract the motors limits, or use the EPICS not set value of (0,0)
    limits = getattr(motor, 'limits', (0, 0))

    if limits != (0, 0):
        return MFSpin(name, parent=parent, minimum=limits[0],
                      maximum=limits[1])
    else:
        return MFSpin(name, parent=parent)


class BsCountTableEditor(MTableInterfaceWidget):
    '''Table editor for plan_args following the ``count`` plan API.'''
    def __init__(self, *args, detectors=[], **kwargs):
        self.detectors = detectors
        prefix_editor_map = {'dets': partial(table_mselector_factory,
                                             option_list=self.detectors,
                                             vertical=False),
                             'num': partial(table_mispin_factory,
                                            minimum=0)}
        super().__init__(*args, prefix_editor_map=prefix_editor_map, **kwargs)


def bs_motor_update_coupled_parameters(requested_parameters,
                                       current_parameters,
                                       row):
    '''An 'update_coupled_parameters' function for use with motors.

    This ensures that, if a 'motor' column that selects a motor is updated,
    any corresponding 'start', 'stop' or 'value' column values are checked
    against the new motors limits, and set to 'None' if not.

    For a description of how these functions work see the doc string for
    ``mily.table_interface.MTableInterfaceWidget``.

    Parameters:
    requested_parameters : dict
        A dictionary mapping column headings to new values to be updated.
    current_parameters : dict
        A dictionary mapping column headings to current values.
    row : int
        The row that is to be updated.
    '''

    # create an output dictionary by merging the input dicts.
    new_parameters = {**current_parameters, **requested_parameters}

    # reset any 'positions' columns to None if current value is outside limits
    if 'motor' in requested_parameters.keys():
        motor = requested_parameters['motor']
        limits = getattr(motor, 'limits', (0, 0))
        if limits != (0, 0):
            for column_name in [name for name in ['start', 'stop', 'value']
                                if name in current_parameters.keys()]:
                if (current_parameters[column_name] < limits[0] or
                        current_parameters[column_name] > limits[1]):
                    new_parameters[column_name] = None

    if 'snake' in new_parameters.keys():  # update snake columns if they exist
        # if row is zero ensure that the 'snake' value is set to 'None'
        if row == 0:
            new_parameters['snake'] = None
        elif not new_parameters['snake']:
            new_parameters['snake'] = False

    return new_parameters


class BsMvTableEditor(MTableInterfaceWidget):
    '''Table editor for plan_args following the ``mv`` plan_stub API.'''
    def __init__(self, *args, motors=[], **kwargs):
        self.motors = motors
        table_editor_map = {'motor': partial(table_mcombobox_factory,
                                             option_list=self.motors,
                                             table=self,
                                             key='motor'),
                            'value': partial(bs_motor_position_mfspin_factory,
                                             table=self)}
        super().__init__(
            *args, table_editor_map=table_editor_map,
            update_coupled_parameters=bs_motor_update_coupled_parameters,
            **kwargs)


class BsScanTableEditor(MTableInterfaceWidget):
    '''Table Editor for plan_args following the ``scan`` plan API.'''
    def __init__(self, *args, detectors=[], motors=[], **kwargs):
        self.detectors = detectors
        self.motors = motors
        prefix_editor_map = {'dets': partial(table_mselector_factory,
                                             option_list=self.detectors,
                                             vertical=False)}
        table_editor_map = {'motor': partial(table_mcombobox_factory,
                                             option_list=self.motors,
                                             table=self,
                                             key='motor'),
                            'start': partial(bs_motor_position_mfspin_factory,
                                             table=self),
                            'stop': partial(bs_motor_position_mfspin_factory,
                                            table=self)}
        suffix_editor_map = {'num': partial(table_mispin_factory,
                                            minimum=0)}
        super().__init__(
            *args, prefix_editor_map=prefix_editor_map,
            table_editor_map=table_editor_map,
            suffix_editor_map=suffix_editor_map,
            update_coupled_parameters=bs_motor_update_coupled_parameters,
            **kwargs)


class BsGridTableEditor(MTableInterfaceWidget):
    '''Table Editor for plan_args following the ``grid_scan`` plan API.'''
    def __init__(self, *args, detectors=[], motors=[], **kwargs):
        self.detectors = detectors
        self.motors = motors
        prefix_editor_map = {'dets': partial(table_mselector_factory,
                                             option_list=self.detectors,
                                             vertical=False)}
        table_editor_map = {'motor': partial(table_mcombobox_factory,
                                             option_list=self.motors,
                                             table=self,
                                             key='motor'),
                            'start': partial(bs_motor_position_mfspin_factory,
                                             table=self),
                            'stop': partial(bs_motor_position_mfspin_factory,
                                            table=self),
                            'num': partial(table_mispin_factory,
                                           minimum=0),
                            'snake': partial(bs_snake_editor_factory,
                                             table=self)}
        super().__init__(
            *args, prefix_editor_map=prefix_editor_map,
            table_editor_map=table_editor_map,
            update_coupled_parameters=bs_motor_update_coupled_parameters,
            **kwargs)


class MoverRanger(QtWidgets.QWidget):
    def __init__(self, name, mover=None, *,
                 start_name='start',
                 stop_name='stop',
                 steps_name='steps',
                 steps=10, **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self.mover = None
        hlayout = QtWidgets.QHBoxLayout()
        label = self.label = QtWidgets.QLabel('')
        lower = self.lower = MFSpin(start_name)
        upper = self.upper = MFSpin(stop_name)
        stps = self.steps = MISpin(steps_name)
        stps.setValue(steps)
        stps.setMinimum(1)

        hlayout.addWidget(label)
        hlayout.addStretch()
        hlayout.addLayout(vstacked_label(start_name, lower))
        hlayout.addLayout(vstacked_label(stop_name, upper))
        hlayout.addLayout(vstacked_label(steps_name, stps))
        self.setLayout(hlayout)

        if mover is not None:
            self.set_mover(mover)

    def set_mover(self, mover):
        self.mover = mover
        self.label.setText(mover.name)
        limits = getattr(mover, 'limits', (0, 0))
        upper = self.upper
        lower = self.lower
        # (0, 0) is the epics way of saying 'no limits'
        if limits != (0, 0):
            lower.setRange(*limits)
            upper.setRange(*limits)

        egu = getattr(mover, 'egu', None)
        if egu is not None:
            lower.setSuffix(f' {egu}')
            upper.setSuffix(f' {egu}')

    def get_parameters(self):
        return merge_parameters([self.lower, self.upper, self.steps])

    def get_args(self):
        return (self.mover,
                self.lower.get_parameters()['start'],
                self.upper.get_parameters()['stop'],
                self.steps.get_parameters()['steps'])


class DetectorCheck(QtWidgets.QCheckBox):
    def __init__(self, detector, **kwargs):
        self.det = detector
        super().__init__(detector.name, **kwargs)


class DetectorSelector(QtWidgets.QGroupBox):
    def __init__(self, title='Detectors', *, detectors, **kwargs):
        super().__init__(title, **kwargs)
        self.button_group = QtWidgets.QButtonGroup()
        self.button_group.setExclusive(False)
        vlayout = QtWidgets.QVBoxLayout()
        self.setLayout(vlayout)
        for d in detectors:
            button = DetectorCheck(d)
            self.button_group.addButton(button)
            vlayout.addWidget(button)

    def get_detectors(self):
        return tuple(b.det
                     for b in self.button_group.buttons()
                     if b.isChecked())


class MotorSelector(QtWidgets.QWidget):
    """Widget to select one of many motors

    This generates a MoverRanger for each motor passed in and
    a drop-down to select between them.

    Parameters
    ----------
    motors : List[Settable]
        Makes use of .name, .limits (optional), and .egu (optional)
    """
    def __init__(self, motors, **kwargs):
        super().__init__(**kwargs)
        self.motors = []
        self.cb = combobox = QtWidgets.QComboBox()
        hlayout = QtWidgets.QHBoxLayout()
        motor_layout = QtWidgets.QHBoxLayout()

        for motor in motors:
            mrw = MoverRanger(motor.name, motor)
            mrw.label.setVisible(False)
            self.motors.append(mrw)
            motor_layout.addWidget(mrw)
            # the label is redundant with the drop down
            mrw.setVisible(False)
            combobox.addItem(motor.name)

        combobox.currentIndexChanged[int].connect(
            self.set_active_motor)

        hlayout.addWidget(combobox)
        hlayout.addLayout(motor_layout)

        self.setLayout(hlayout)
        self.set_active_motor(0)

    def set_active_motor(self, n):
        try:
            self.active_motor = self.motors[n]
            for m in self.motors:
                if m is not self.active_motor:
                    m.setVisible(False)
            self.active_motor.setVisible(True)

        except IndexError:
            pass

    def get_args(self):
        return self.active_motor.get_args()


class TabScanSelector(QtWidgets.QWidget):
    def __init__(self, *scan_widgets, **kwargs):
        super().__init__(**kwargs)
        self._scans = scan_widgets
        self.tab_widget = QtWidgets.QTabWidget()
        for scan in scan_widgets:
            self.tab_widget.addTab(scan, scan.name)

        vlayout = QtWidgets.QVBoxLayout()
        vlayout.addWidget(self.tab_widget)

        self.setLayout(vlayout)

    def get_plan(self):
        return self.tab_widget.currentWidget().get_plan()


class Scan1D(QtWidgets.QWidget):
    """Widget for 1D scans.

    The wrapped plan must have the signature ::

       def plan(dets : List[OphydObj], motor : Settable,
                start : float, stop : float, step : int, *
                md=None : Dict[str, Any]) -> Any:
    """
    def __init__(self, name, plan, motors_widget, detectors_widget,
                 md_parameters=None, **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self.plan_function = plan
        self.md_parameters = md_parameters
        vlayout = QtWidgets.QVBoxLayout()

        # set up the motor selector
        self.motors_widget = motors_widget
        vlayout.addWidget(motors_widget)

        # set up the detector selector
        self.dets = detectors_widget
        vlayout.addWidget(self.dets)

        self.setLayout(vlayout)

    def get_plan(self):
        md = (self.md_parameters.get_metadata()
              if self.md_parameters is not None
              else None)
        return self.plan_function(self.dets.get_detectors(),
                                  *self.motors_widget.get_args(),
                                  md=md)


class Count(QtWidgets.QWidget):
    def __init__(self, name, plan, detectors_widget, md_parameters=None,
                 **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self.plan_function = plan
        self.md_parameters = md_parameters

        vlayout = QtWidgets.QVBoxLayout()
        hlayout = QtWidgets.QHBoxLayout()
        # num spinner
        self.num_spin = MISpin('num')
        self.num_spin.setRange(1, 2**16)  # 65k maximum, 18hr @ 1hz
        hlayout.addLayout(hstacked_label('num', self.num_spin))

        # float spinner
        self.delay_spin = MFSpin('delay')
        self.delay_spin.setRange(0, 60*60)  # maximum delay an hour
        self.delay_spin.setDecimals(1)  # only 0.1s precision from GUI
        self.delay_spin.setSuffix('s')
        label_layout = QtWidgets.QHBoxLayout()
        inner_layout = QtWidgets.QHBoxLayout()
        cb = QtWidgets.QCheckBox()
        label_layout.addWidget(QtWidgets.QCheckBox())
        inner_layout.addWidget(QtWidgets.QLabel('delay'))
        inner_layout.addWidget(self.delay_spin)
        label_layout.addLayout(inner_layout)
        label_layout.addStretch()
        cb.setCheckable(True)
        cb.stateChanged.connect(self.delay_spin.setEnabled)
        cb.setChecked(False)
        self.delay_spin.setEnabled(False)
        hlayout.addLayout(label_layout)
        hlayout.addStretch()
        vlayout.addLayout(hlayout)
        # set up the detector selector
        self.dets = detectors_widget
        vlayout.addWidget(self.dets)

        self.setLayout(vlayout)

    def get_plan(self):
        d = self.delay_spin.value() if self.delay_spin.isEnabled() else None
        num = self.num_spin.value()
        md = (self.md_parameters.get_metadata()
              if self.md_parameters is not None
              else None)
        return self.plan_function(self.dets.get_detectors(),
                                  num=num,
                                  delay=d,
                                  md=md)


class StartLabel(QtWidgets.QLabel):
    format_str = 'last scan: {uid}'

    def doc_consumer(self, name, doc):
        if name == 'start':
            self.setText(self.format_str.format(**doc))


class LivePlaceholder(QtWidgets.QWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.label = QtWidgets.QLabel('BUILD HERE')
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)

    def doc_consumer(self, name, doc):
        ...


class ControlGui(QtWidgets.QWidget):
    def __init__(self, queue, teleport, *scan_widgets,
                 live_widget=None,
                 **kwargs):
        super().__init__(**kwargs)
        self.label = label = StartLabel()
        self.queue = queue
        self.teleport = teleport
        self.md_parameters = MetaDataEntry(name='Metadata')
        self.md_widget = ParameterTree()
        self.md_widget.setParameters(self.md_parameters)
        outmost_layout = QtWidgets.QHBoxLayout()

        input_layout = QtWidgets.QVBoxLayout()
        outmost_layout.addLayout(input_layout)

        input_layout.addWidget(label)
        self.tabs = TabScanSelector(*scan_widgets)

        input_layout.addWidget(self.tabs)
        for sw in scan_widgets:
            sw.md_parameters = self.md_parameters

        self.go_button = QtWidgets.QPushButton('SCAN!')
        self.md_button = QtWidgets.QPushButton('edit metadata')
        input_layout.addWidget(self.md_button)
        input_layout.addWidget(self.go_button)

        self.teleport.name_doc.connect(label.doc_consumer)

        self.cbr = Dispatcher()
        self.bec = BestEffortCallback()
        self.teleport.name_doc.connect(
            lambda name, doc: self.cbr.process(DocumentNames(name), doc))
        self.cbr.subscribe(self.bec)

        def runner():
            self.queue.put(self.tabs.get_plan())

        self.go_button.clicked.connect(runner)
        self.md_button.clicked.connect(self.md_widget.show)

        if live_widget is None:
            live_widget = LivePlaceholder()
        self.live_widget = live_widget
        self.teleport.name_doc.connect(live_widget.doc_consumer)
        outmost_layout.addWidget(live_widget)

        self.setLayout(outmost_layout)
