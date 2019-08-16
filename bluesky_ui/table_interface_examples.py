from bluesky.plans import scan
from bluesky.simulators import summarize_plan
from mily.widgets import MText, MComboBox, MISpin, MFSpin
from mily.table_interface import MFunctionTableInterfaceWidget
from ophyd.sim import hw

hw = hw()


def partialclass(cls, partial_kwargs):
    '''Returns a partial class with 'partial_kwargs' values set


    This function returns a class whereby any args/kwargs in the dictionary
    ``partial_kwargs`` are set.

    Parameters
    ----------
    partial_kwargs : dict
        a dict mapping arg/kwarg parameters to values.
    '''

    class PartialClass(cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **partial_kwargs, **kwargs)
    return PartialClass


# simplest possible tableinterface RunEngine GUI example
def simple_REfunction(label='label', det=hw.det, motor=hw.motor, start=0,
                      stop=3, num_steps=3):
    '''A simple function that can performs summarize_plan on a scan plan.'''

    plan = scan([det], motor, start, stop, num_steps, md={'plan_label': label})
    summarize_plan(plan)


class SimpleREfunctionWidget(MFunctionTableInterfaceWidget):
    '''A ``MTableInterfaceWidgetWithExport`` for use with simple_REfunction.

    Add custom ``detectors``, ``motors``, ``editor_map`` and ``default_rows``
    attributes which contain some function specfic information and/or user
    configurable information.

   To run this example as a standalone window use the following:

    ..code-block:: python

        from bluesky_ui.table_interface_examples import SimpleREfunctionWidget
        from PyQt5.QtWidgets import QApplication
        app = QApplication([])
        window = SimpleREfunctionWidget('simple_REfunction')
        window.show()
        app.exec_()

    '''

    # NOTE I have made these 'class' variables as I am considering
    # that we may want to make them traitlets for user config reasons.
    detectors = [hw.det, hw.det1, hw.det2]
    motors = [hw.motor, hw.motor1, hw.motor2]
    default_rows = [
        {'label': 'plan_1', 'det': hw.det, 'motor': hw.motor, 'start': 0,
         'stop': 2, 'num_steps': 3},
        {'label': 'plan_2', 'det': hw.det1, 'motor': hw.motor1, 'start': -3,
         'stop': 3, 'num_steps': 7},
        {'label': 'plan_3', 'det': hw.det2, 'motor': hw.motor2, 'start': -4,
         'stop': 4, 'num_steps': 9}]

    def __init__(self, name, *args, **kwargs):
        _det_dict = {det.name: det for det in self.detectors}
        _motor_dict = {motor.name: motor for motor in self.motors}
        self.editor_map = {'label': MText,
                           'det': partialclass(MComboBox,
                                               {'items': _det_dict}),
                           'motor': partialclass(MComboBox,
                                                 {'items': _motor_dict}),
                           'start': MFSpin,
                           'stop': MFSpin,
                           'num_steps': MISpin}
        super().__init__(simple_REfunction, name, *args, **kwargs)
