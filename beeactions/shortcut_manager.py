import sys
import os
from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import Qt, QObject, pyqtSlot, QThread, pyqtSignal, QSize, QTimer, QDateTime, QDate, QTime


import pyqtgraph.parametertree.parameterTypes as pTypes
from pyqtgraph.parametertree import Parameter, ParameterTree
import pymodaq.daq_utils.custom_parameter_tree as custom_tree  # to be placed after importing Parameter
from pyqtgraph.parametertree.Parameter import registerParameterType
from pymodaq.daq_utils.h5saver import H5Saver
from pymodaq.daq_utils.daq_utils import get_set_local_dir, select_file

#check if preset_mode directory exists on the drive

local_path = get_set_local_dir()

shortcut_path = os.path.join(local_path, 'preset_shortcuts')
if not os.path.isdir(shortcut_path):
    os.makedirs(shortcut_path)


class ScalableGroupShortCut(pTypes.GroupParameter):
    """
    """
    def __init__(self, **opts):
        opts['type'] = 'groupshortcut'
        opts['addText'] = "Add"
        if 'addList' not in opts:
            opts['addList'] = []
        pTypes.GroupParameter.__init__(self, **opts)

    def addNew(self, typ):
        """
            Add a child.
        """
        childnames = [par.name() for par in self.children()]
        if childnames == []:
            newindex = 0
        else:
            newindex = len(childnames)

        params = [{'title': 'Action:', 'name': 'action', 'type': 'list', 'value': typ, 'values': self.opts['addList']},
                  {'title': 'Set Shortcut:', 'name': 'set_shortcut', 'type': 'bool_push', 'label': 'Set', 'value': False},
                  {'title': 'Shortcut:', 'name': 'shortcut', 'type': 'str', 'value': ''},
                  ]
        for param in params:
            if param['type'] == 'itemselect' or param['type'] == 'list':
                param['show_pb'] = True

        child = {'title': f'Action {newindex:02d}', 'name': f'action{newindex:02d}', 'type': 'group',
                 'removable': True, 'children': params, 'removable': True, 'renamable': False}

        self.addChild(child)
registerParameterType('groupshortcut', ScalableGroupShortCut, override=True)

class ShortcutBox(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        horwidget = QtWidgets.QWidget()
        layout.addWidget(horwidget)
        hor_layout = QtWidgets.QHBoxLayout()
        horwidget.setLayout(hor_layout)
        label = QtWidgets.QLabel('Pressed key on the keyboard:')
        self.label = QtWidgets.QLabel('')

        hor_layout.addWidget(label)
        hor_layout.addWidget(self.label)

        buttonBox = QtWidgets.QDialogButtonBox()
        buttonBox.addButton(QtWidgets.QDialogButtonBox.Ok)
        buttonBox.addButton(QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(self.label)
        layout.addWidget(buttonBox)

        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

    def keyPressEvent(self, event):
        keyseq = QtGui.QKeySequence(event.key())
        self.label.setText(keyseq.toString())





class ShortCutManager(QObject):

    def __init__(self, list_actions=[], msgbox=False):
        super().__init__()
        self.list_actions = list_actions

        if msgbox:
            msgBox = QtWidgets.QMessageBox()
            msgBox.setText("Preset Manager?")
            msgBox.setInformativeText("What do you want to do?");
            cancel_button = msgBox.addButton(QtWidgets.QMessageBox.Cancel)
            new_button = msgBox.addButton("New", QtWidgets.QMessageBox.ActionRole)
            modify_button = msgBox.addButton('Modify', QtWidgets.QMessageBox.AcceptRole)
            msgBox.setDefaultButton(QtWidgets.QMessageBox.Cancel)
            ret = msgBox.exec()

            if msgBox.clickedButton() == new_button:
                self.set_new_preset()

            elif msgBox.clickedButton() == modify_button:
                path = select_file(start_path=shortcut_path,save=False, ext='xml')
                if path != '':
                    self.set_file_preset(str(path))
            else: #cancel
                pass

    def set_new_preset(self):
        param = [
                {'title': 'Filename:', 'name': 'filename', 'type': 'str', 'value': 'preset_default'},
                {'title': 'Author:', 'name': 'author', 'type': 'str', 'value': 'Aurore Avargues'},
                {'title': 'Saving options:', 'name': 'saving_options', 'type': 'group', 'children': H5Saver.params},
                
                ]
        params_action = [{'title': 'Actions:', 'name': 'actions', 'type': 'groupshortcut', 'addList': self.list_actions}]  # PresetScalableGroupMove(name="Moves")]
        self.shortcut_params = Parameter.create(title='Preset', name='Preset', type='group', children=param+params_action)
        self.shortcut_params.child('saving_options', 'save_type').hide()
        self.shortcut_params.child('saving_options', 'save_2D').hide()
        self.shortcut_params.child('saving_options', 'do_save').hide()
        self.shortcut_params.child('saving_options', 'N_saved').hide()
        self.shortcut_params.child('saving_options', 'custom_name').hide()
        self.shortcut_params.child('saving_options', 'show_file').hide()
        self.shortcut_params.child('saving_options', 'current_scan_name').hide()
        self.shortcut_params.child('saving_options', 'current_scan_path').hide()
        self.shortcut_params.child('saving_options', 'current_h5_file').hide()
        self.shortcut_params.sigTreeStateChanged.connect(self.parameter_tree_changed)

        self.show_preset()

    def parameter_tree_changed(self, param, changes):
        """
            Check for changes in the given (parameter,change,information) tuple list.
            In case of value changed, update the DAQscan_settings tree consequently.

            =============== ============================================ ==============================
            **Parameters**    **Type**                                     **Description**
            *param*           instance of pyqtgraph parameter              the parameter to be checked
            *changes*         (parameter,change,information) tuple list    the current changes state
            =============== ============================================ ==============================
        """
        for param, change, data in changes:
            path = self.shortcut_params.childPath(param)
            if change == 'childAdded':pass

            elif change == 'value':
                if param.name() == 'set_shortcut':

                    msgBox = ShortcutBox()
                    ret = msgBox.exec()
                    if ret:
                        param.parent().child(('shortcut')).setValue(msgBox.label.text())

            elif change == 'parent':pass

    def set_file_preset(self, filename, show=True):
        """

        """
        children = custom_tree.XML_file_to_parameter(filename)
        self.shortcut_params = Parameter.create(title='Shortcuts:', name='shortcuts', type='group', children=children)
        if show:
            self.show_preset()

    def show_preset(self):
        """

        """
        dialog = QtWidgets.QDialog()
        vlayout = QtWidgets.QVBoxLayout()
        tree = ParameterTree()
        #tree.setMinimumWidth(400)
        tree.setMinimumHeight(500)
        tree.setParameters(self.shortcut_params, showTop=False)

        vlayout.addWidget(tree)
        dialog.setLayout(vlayout)
        buttonBox = QtWidgets.QDialogButtonBox(parent=dialog)

        buttonBox.addButton('Save', buttonBox.AcceptRole)
        buttonBox.accepted.connect(dialog.accept)
        buttonBox.addButton('Cancel', buttonBox.RejectRole)
        buttonBox.rejected.connect(dialog.reject)

        vlayout.addWidget(buttonBox)
        dialog.setWindowTitle('Fill in information about the actions and their shortcuts')
        res = dialog.exec()

        if res == dialog.Accepted:
            # save preset parameters in a xml file
            custom_tree.parameter_to_xml_file(self.shortcut_params, os.path.join(shortcut_path,
                                                                               self.shortcut_params.child(
                                                                                   ('filename')).value()))



if __name__ == '__main__':
    from bee_actions import list_actions

    app = QtWidgets.QApplication(sys.argv)
    prog = ShortCutManager(list_actions, True)

    sys.exit(app.exec_())