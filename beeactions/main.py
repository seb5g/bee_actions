import sys
import os
import logging
import datetime
import numpy as np
from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import Qt, QObject, pyqtSlot, QThread, pyqtSignal, QSize, QTimer, QDateTime, QDate, QTime
from pyqtgraph.dockarea import Dock

from pymodaq.daq_utils.h5saver import H5Saver
from pyqtgraph.parametertree import Parameter, ParameterTree
from pymodaq.daq_utils import custom_parameter_tree as custom_tree

from pymodaq.daq_utils.daq_utils import DockArea, get_set_local_dir, getLineInfo, select_file
from shortcut_manager import ShortCutManager, shortcut_path
from pymodaq.daq_utils.chrono_timer import ChronoTimer
import pickle

list_actions = ['Eat', 'Landed', 'Attack']

local_path = get_set_local_dir()
now = datetime.datetime.now()

log_path = os.path.join(local_path, 'logging')
if not os.path.isdir(log_path):
    os.makedirs(log_path)

layout_path = os.path.join(local_path, 'layout')
if not os.path.isdir(layout_path):
    os.makedirs(layout_path)

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(filename=os.path.join(log_path, 'bee_action_{}.log'.format(now.strftime('%Y%m%d_%H_%M_%S'))), level=logging.DEBUG)


class BeeActions(QObject):
    log_signal = pyqtSignal(str)

    def __init__(self, dockarea):
        super().__init__()
        self.dockarea = dockarea
        self.dockarea.dock_signal.connect(self.save_layout_state_auto)
        self.mainwindow = dockarea.parent()
        self.chrono = ChronoTimer(dockarea)
        self.author = 'Aurore Avargues'
        self.h5saver = H5Saver()
        self.h5saver.new_file_sig.connect(self.create_new_file)
        self.settings = None
        self.shortcut_file = None
        self.shortcuts = []
        self.shortcut_manager = ShortCutManager(list_actions)
        self.timestamp_array = None
        self.action_array = None
        self.bee_array = None
        self.setup_ui()

    def setup_ui(self):
        #creating the menubar
        self.menubar = self.mainwindow.menuBar()
        self.create_menu(self.menubar)

        #disconnect normal chrono/timer behaviour with the start button
        self.chrono.start_pb.disconnect()
        self.chrono.start_pb.clicked.connect(self.set_scan)
        self.chrono.reset_pb.clicked.connect(self.stop_daq)

        self.settings_dock = Dock('Settings')
        self.dockarea.addDock(self.settings_dock, 'bottom', self.chrono.dock_controls)

        self.dock_daq = Dock('Data Acquisition')
        self.dockarea.addDock(self.dock_daq, 'right')
        self.logger_list = QtWidgets.QListWidget()
        self.logger_list.setMinimumWidth(300)
        self.dock_daq.addWidget(self.logger_list)



        self.init_tree = ParameterTree()
        self.init_tree.setMinimumWidth(300)
        self.init_tree.setMinimumHeight(150)
        self.settings_dock.addWidget(self.init_tree)
        self.settings_dock.addWidget(self.h5saver.settings_tree)
        self.h5saver.settings.child(('save_type')).hide()
        self.h5saver.settings.child(('save_2D')).hide()
        self.h5saver.settings.child(('save_raw_only')).hide()
        self.h5saver.settings.child(('do_save')).hide()
        self.h5saver.settings.child(('custom_name')).hide()


        self.settings = Parameter.create(name='init_settings', type='group', children=[
            {'title': 'Loaded presets', 'name': 'loaded_files', 'type': 'group', 'children': [
                {'title': 'Shortcut file', 'name': 'shortcut_file', 'type': 'str', 'value': '', 'readonly': True},
                {'title': 'Layout file', 'name': 'layout_file', 'type': 'str', 'value': '', 'readonly': True},
                ]},
            {'title': 'Settings', 'name': 'settings', 'type': 'group', 'children': [
                {'title': 'Save Bee number', 'name': 'save_bee_number', 'type': 'bool', 'value': True},
                ]},
            {'title': 'Shortcuts', 'name': 'shortcuts', 'type': 'group', 'children': []},
            ])
        self.init_tree.setParameters(self.settings, showTop=False)
        self.settings.sigTreeStateChanged.connect(self.parameter_tree_changed)

        #params about dataset attributes and scan attibutes
        date = QDateTime(QDate.currentDate(), QTime.currentTime())
        params_dataset = [{'title': 'Dataset information', 'name': 'dataset_info', 'type': 'group', 'children':[
                            {'title': 'Author:', 'name': 'author', 'type': 'str', 'value': self.author},
                            {'title': 'Date/time:', 'name': 'date_time', 'type': 'date_time', 'value': date},
                            {'title': 'Sample:', 'name': 'sample', 'type': 'str', 'value':''},
                            {'title': 'Experiment type:', 'name': 'experiment_type', 'type': 'str', 'value': ''},
                            {'title': 'Description:', 'name': 'description', 'type': 'text', 'value': ''}]}]

        params_scan = [{'title': 'Scan information', 'name': 'scan_info', 'type': 'group', 'children':[
                            {'title': 'Author:', 'name': 'author', 'type': 'str', 'value': self.author},
                            {'title': 'Date/time:', 'name': 'date_time', 'type': 'date_time', 'value': date},
                            {'title': 'Scan type:', 'name': 'scan_type', 'type': 'list', 'value':'Scan1D', 'values':['Scan1D','Scan2D']},
                            {'title': 'Scan name:', 'name': 'scan_name', 'type': 'str', 'value': '', 'readonly': True},
                            {'title': 'Description:', 'name': 'description', 'type': 'text', 'value': ''},
                            ]}]

        self.dataset_attributes = Parameter.create(name='Attributes', type='group', children=params_dataset)
        self.scan_attributes = Parameter.create(name='Attributes', type='group', children=params_scan)

    def parameter_tree_changed(self, param, changes):
        """
            | Check eventual changes in the changes list parameter.
            |
            | In case of changed values, emit the signal containing the current path and parameter via update_settings_signal to the connected hardware.

            =============== ====================================    ==================================================
            **Parameters**   **Type**                                **Description**

             *param*         instance of pyqtgraph parameter         The parameter to be checked

             *changes*       (parameter,change,infos) tuple list     The (parameter,change,infos) list to be treated
            =============== ====================================    ==================================================
        """

        for param, change, data in changes:
            path = self.settings.childPath(param)
            if path is not None:
                childName = '.'.join(path)
            else:
                childName = param.name()
            if change == 'childAdded':
                pass
            elif change == 'value':
                if param.name() in custom_tree.iter_children(self.settings.child(('shortcuts')), []):
                    if param.parent().name() == 'shortcuts':
                        param_index = custom_tree.iter_children(self.settings.child(('shortcuts')), []).index(param.name())
                        action = self.shortcut_manager.shortcut_params.child(('actions')).children()[param_index].child(('action'))
                        self.activate_shortcut(self.shortcuts[param_index], action, activate=param.value())


            elif change == 'parent':
                pass

    def activate_shortcut(self, shortcut, action='', activate=True):
        if activate:
            shortcut.activated.connect(
                self.create_activated_slot(action))
        else:
            try:
                shortcut.activated.disconnect()
            except:
                pass
    def create_activated_slot(self, action):
        return lambda: self.log_data(action)

    def log_data(self, action=''):
        now = self.chrono.get_elapsed_time()
        if self.settings.child('settings', 'save_bee_number').value():
            widget = QtWidgets.QWidget()
            index, res = QtWidgets.QInputDialog.getInt(widget, 'Bee number', 'Pick a number for this bee!')
            if res:
                new_item = QtWidgets.QListWidgetItem(f'Elapsed time: {int(now)} s, Bee {index} did :{action}')
                self.logger_list.insertItem(0, new_item)

                self.h5saver.append(self.action_array, action)
                self.h5saver.append(self.timestamp_array, np.array([now]))
                self.h5saver.append(self.bee_array, np.array([index]))
        else:
            new_item = QtWidgets.QListWidgetItem(f'Elapsed time: {int(now)} s:{action}')
            self.logger_list.insertItem(0, new_item)
            self.h5saver.append(self.action_array, action)
            self.h5saver.append(self.timestamp_array, np.array([now]))
        self.h5saver.flush()

    def create_shortcuts(self):
        pass

    def create_new_file(self, new_file):
        self.h5saver.init_file(update_h5=new_file)
        res = self.update_file_settings(new_file)
        return res

    def set_scan(self):
        """
        Sets the current scan given the selected settings. Makes some checks, increments the h5 file scans.
        In case the dialog is cancelled, return False and aborts the scan
        """
        try:
            if self.shortcut_file is not None:

                # set the filename and path
                res = self.create_new_file(False)
                if not res:
                    return

                #create the arrays within the current scan group
                self.timestamp_array = self.h5saver.add_array(self.h5saver.current_scan_group, 'time_axis', 'data',
                                       scan_type='scan1D', enlargeable=True, array_to_save=np.array([0., ]),
                                       data_shape=(1,), title='Timestamps',
                                                metadata=dict(units='seconds'))

                self.action_array = self.h5saver.add_string_array(self.h5saver.current_scan_group, 'actions',
                                            title='Actions', metadata=dict([]))
                if self.settings.child('settings', 'save_bee_number').value():
                    self.bee_array = self.h5saver.add_array(self.h5saver.current_scan_group, 'bees', 'data',
                                           scan_type='scan1D', enlargeable=True, array_to_save=np.array([0, ]),
                                            title='Bees', data_shape=(1, ))

                current_filename = self.h5saver.settings.child(('current_scan_name')).value()
                self.init_tree.setEnabled(False)
                self.h5saver.settings_tree.setEnabled(False)
                self.logger_list.clear()

                self.h5saver.current_scan_group._v_attrs['scan_done'] = False
                # if all metadat steps have been validated, start the chrono
                self.chrono.start()

                return True
            else:
                mssg = QtWidgets.QMessageBox()
                mssg.setText(
                    'You have to load a shortcut file configuration before starting')
                mssg.exec()
                return False

        except Exception as e:
            self.update_status(getLineInfo() + str(e))

    def stop_daq(self):
        self.h5saver.current_scan_group._v_attrs['scan_done'] = True
        self.init_tree.setEnabled(True)
        self.h5saver.settings_tree.setEnabled(True)
        self.h5saver.flush()

    def update_file_settings(self, new_file=False):
        try:
            if self.h5saver.current_scan_group is None:
                new_file = True


            if new_file:
                self.set_metadata_about_dataset()
                self.save_metadata(self.h5saver.raw_group, 'dataset_info')

            if self.h5saver.current_scan_name is None:
                self.h5saver.add_scan_group()
            elif not self.h5saver.is_node_in_group(self.h5saver.raw_group, self.h5saver.current_scan_name):
                self.h5saver.add_scan_group()


            #set attributes to the current group, such as scan_type....
            self.scan_attributes.child('scan_info','scan_type').setValue('Scan1D')
            self.scan_attributes.child('scan_info','scan_name').setValue(self.h5saver.current_scan_group._v_name)
            self.scan_attributes.child('scan_info','description').setValue(self.h5saver.current_scan_group._v_attrs['description'])
            res = self.set_metadata_about_current_scan()
            self.save_metadata(self.h5saver.current_scan_group, 'scan_info')
            return res

        except Exception as e:
            self.update_status(getLineInfo() + str(e))


    def set_metadata_about_current_scan(self):
        """
            Set the date/time and author values of the scan_info child of the scan_attributes tree.
            Show the 'scan' file attributes.

            See Also
            --------
            show_file_attributes
        """
        date = QDateTime(QDate.currentDate(), QTime.currentTime())
        self.scan_attributes.child('scan_info', 'date_time').setValue(date)
        self.scan_attributes.child('scan_info', 'author').setValue(self.dataset_attributes.child('dataset_info', 'author').value())
        res = self.show_file_attributes('scan')
        return res

    def set_metadata_about_dataset(self):
        """
            Set the date value of the data_set_info-date_time child of the data_set_attributes tree.
            Show the 'dataset' file attributes.

            See Also
            --------
            show_file_attributes
        """
        date = QDateTime(QDate.currentDate(), QTime.currentTime())
        self.dataset_attributes.child('dataset_info', 'date_time').setValue(date)
        res = self.show_file_attributes('dataset')
        return res

    def show_file_attributes(self,type_info='dataset'):
        """
        """
        dialog = QtWidgets.QDialog()
        vlayout = QtWidgets.QVBoxLayout()
        tree = ParameterTree()
        tree.setMinimumWidth(400)
        tree.setMinimumHeight(500)
        if type_info =='scan':
            tree.setParameters(self.scan_attributes, showTop=False)
        elif type_info =='dataset':
            tree.setParameters(self.dataset_attributes, showTop=False)


        vlayout.addWidget(tree)
        dialog.setLayout(vlayout)
        buttonBox = QtWidgets.QDialogButtonBox(parent=dialog)
        buttonBox.addButton('Cancel', buttonBox.RejectRole)
        buttonBox.addButton('Apply', buttonBox.AcceptRole)
        buttonBox.rejected.connect(dialog.reject)
        buttonBox.accepted.connect(dialog.accept)

        vlayout.addWidget(buttonBox)
        dialog.setWindowTitle('Fill in information about this {}'.format(type_info))
        res=dialog.exec()
        return res

    def save_metadata(self, node, type_info='dataset_info'):
        """
        """

        attr = node._v_attrs
        if type_info == 'dataset_info':
            attr['type'] = 'dataset'
            params = self.dataset_attributes
        else:
            attr['type'] = 'scan'
            params = self.scan_attributes
        for child in params.child((type_info)).children():
            if isinstance(child.value(), QDateTime):
                attr[child.name()] = child.value().toString('dd/mm/yyyy HH:MM:ss')
            else:
                attr[child.name()] = child.value()
        if type_info == 'dataset_info':
            #save contents of given parameter object into an xml string under the attribute settings
            settings_str = b'<All_settings title="All Settings" type="group">'
            settings_str += custom_tree.parameter_to_xml_string(params)
            settings_str += custom_tree.parameter_to_xml_string(self.settings)
            if hasattr(self.shortcut_manager, 'shortcut_params'):
                settings_str += custom_tree.parameter_to_xml_string(self.shortcut_manager.shortcut_params)
            settings_str += b'</All_settings>'

            attr.settings = settings_str


        elif type_info=='scan_info':
            settings_str = b'<All_settings title="All Settings" type="group">' + \
                           custom_tree.parameter_to_xml_string(params) + \
                           custom_tree.parameter_to_xml_string(self.settings) + \
                           custom_tree.parameter_to_xml_string(self.h5saver.settings) + b'</All_settings>'

            attr.settings = settings_str



    def show_log(self):
        import webbrowser
        webbrowser.open(logging.getLoggerClass().root.handlers[0].baseFilename)

    def create_menu(self, menubar):
        menubar.clear()

        # %% create Settings menu
        self.file_menu = menubar.addMenu('File')
        log_action = self.file_menu.addAction('Show log file')
        log_action.triggered.connect(self.show_log)
        self.file_menu.addSeparator()
        quit_action = self.file_menu.addAction('Quit')
        quit_action.triggered.connect(self.quit_fun)

        self.settings_menu = menubar.addMenu('Settings')
        docked_menu = self.settings_menu.addMenu('Docked windows')
        action_load = docked_menu.addAction('Load Layout')
        action_save = docked_menu.addAction('Save Layout')

        action_load.triggered.connect(self.load_layout_state)
        action_save.triggered.connect(self.save_layout_state)
        docked_menu.addSeparator()

        self.preset_menu = menubar.addMenu('Preset Shortcuts')
        action_new_preset = self.preset_menu.addAction('New preset')
        # action.triggered.connect(lambda: self.show_file_attributes(type_info='preset'))
        action_new_preset.triggered.connect(self.create_preset)
        action_modify_preset = self.preset_menu.addAction('Modify preset')
        action_modify_preset.triggered.connect(self.modify_shortcuts)
        self.preset_menu.addSeparator()
        load_preset = self.preset_menu.addMenu('Load presets')

        slots = dict([])
        for ind_file, file in enumerate(os.listdir(shortcut_path)):
            if file.endswith(".xml"):
                (filesplited, ext) = os.path.splitext(file)
                slots[filesplited] = load_preset.addAction(filesplited)
                slots[filesplited].triggered.connect(
                    self.create_menu_slot(os.path.join(shortcut_path, file)))

    def modify_shortcuts(self):
        try:
            path = select_file(start_path=shortcut_path, save=False, ext='xml')
            if path != '':
                self.shortcut_manager.set_file_preset(str(path))

                mssg = QtWidgets.QMessageBox()
                mssg.setText(f'You have to restart the application to take the modifications into account! '
                             f'Quitting the application...')
                mssg.exec()
                self.quit_fun()
            else:  # cancel
                pass
        except Exception as e:
            self.update_status(getLineInfo() + str(e))

    def create_menu_slot(self, filename):
        return lambda: self.set_shortcut_mode(filename)

    def set_shortcut_mode(self, filename):
        #TODO: apply shortcuts to this widget
        tail, fileext = os.path.split(filename)
        file, ext = os.path.splitext(fileext)
        if ext == '.xml':
            self.shortcut_file = filename
            self.shortcut_manager.set_file_preset(filename, show=False)
            self.settings.child('loaded_files', 'shortcut_file').setValue(filename)
            self.author = self.shortcut_manager.shortcut_params.child(('author')).value()
            self.dataset_attributes.child('dataset_info', 'author').setValue(self.author)
            self.scan_attributes.child('scan_info', 'author').setValue(self.author)

            path = os.path.join(layout_path, file + '.dock')
            if os.path.isfile(path):
                self.load_layout_state(path)

            #remove existing shorcuts
            while len(self.shortcuts):
                self.shortcuts.pop(0)

            for ind, shortcut in enumerate(self.shortcut_manager.shortcut_params.child(('actions')).children()):
                stc = QtWidgets.QShortcut(QtGui.QKeySequence(shortcut.child(('shortcut')).value()), self.dockarea)
                self.settings.child(('shortcuts')).addChild(
                    {'title': f"Shortcut{ind:02d}: {shortcut.child(('action')).value()} {shortcut.child(('shortcut')).value()}:",
                     'name': f'shortcut{ind:02d}', 'type': 'led_push', 'value': True})

                self.shortcuts.append(stc)
                self.activate_shortcut(stc, shortcut.child(('action')).value(), activate=True)



    def create_preset(self):
        try:
            self.shortcut_manager.set_new_preset()
            self.create_menu(self.menubar)
        except Exception as e:
            self.update_status(getLineInfo() + str(e))

    def save_layout_state(self, file = None):
        """
            Save the current layout state in the select_file obtained pathname file.
            Once done dump the pickle.

            See Also
            --------
            utils.select_file
        """
        try:
            dockstate = self.dockarea.saveState()
            if file is None:
                file = select_file(start_path=None, save=True, ext='dock')
            if file is not None:
                with open(str(file), 'wb') as f:
                    pickle.dump(dockstate, f, pickle.HIGHEST_PROTOCOL)
        except: pass

    def save_layout_state_auto(self):
        if self.shortcut_file is not None:
            file = os.path.split(self.shortcut_file)[1]
            file = os.path.splitext(file)[0]
            path = os.path.join(layout_path, file+'.dock')
            self.save_layout_state(path)

    def load_layout_state(self, file=None):
        """
            Load and restore a layout state from the select_file obtained pathname file.

            See Also
            --------
            utils.select_file
        """
        try:
            if file is None:
                file = select_file(save=False, ext='dock')
            if file is not None:
                with open(str(file), 'rb') as f:
                    dockstate = pickle.load(f)
                    self.dockarea.restoreState(dockstate)
            file = os.path.split(file)[1]
            self.settings.child('loaded_files', 'layout_file').setValue(file)
        except: pass

    def quit_fun(self):
        """
            Quit the current instance of DAQ_scan and close on cascade move and detector modules.

            See Also
            --------
            quit_fun
        """
        try:
            areas = self.dockarea.tempAreas[:]
            for area in areas:
                area.win.close()
                QtWidgets.QApplication.processEvents()
                QThread.msleep(1000)
                QtWidgets.QApplication.processEvents()

            if hasattr(self, 'mainwindow'):
                self.mainwindow.close()

        except Exception as e:
            pass

    def update_status(self, txt):
        """
            Show the txt message in the status bar with a delay of wait_time ms.

            =============== =========== =======================
            **Parameters**    **Type**    **Description**
            *txt*             string      The message to show
            *wait_time*       int         the delay of showing
            *log_type*        string      the type of the log
            =============== =========== =======================
        """
        try:
            self.log_signal.emit(txt)
            logging.info(txt)

        except Exception as e:
            pass


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    win = QtWidgets.QMainWindow()
    win.setVisible(False)
    area = DockArea()
    win.setCentralWidget(area)
    win.setWindowTitle('BeeAction')
    prog = BeeActions(area)
    win.show()
    sys.exit(app.exec_())