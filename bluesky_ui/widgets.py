from qtpy import QtWidgets
from bluesky.run_engine import Dispatcher
from bluesky.callbacks.best_effort import BestEffortCallback
from event_model import DocumentNames

from pyqtgraph.parametertree import ParameterTree

from mily.widgets import (vstacked_label,
                          hstacked_label, MISpin, MFSpin,
                          MetaDataEntry)


def merge_parameters(widget_iter):
    return {k: v
            for w in widget_iter
            for k, v in w.get_parameters().items()
            if w.isEnabled()}


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
