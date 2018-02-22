#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from view import CliViewer
from urllib.parse import urlparse
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import QObject, pyqtSignal, pyqtSlot

import logging
# get the handler to the current module, and setup logging options
_logger = logging.getLogger(__name__)



try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s

try:
    _encoding = QtGui.QApplication.UnicodeUTF8
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig, _encoding)
except AttributeError:
    def _translate(context, text, disambig):
        return QtGui.QApplication.translate(context, text, disambig)

def _convertList(prop):
    # for make other properties into a list
    plist = []
    if isinstance(prop, list):
        plist.extend(prop)
    elif isinstance(prop, dict):
        plist.append(prop)
    return plist

###############################################################################
#
# GuiDraw
#
###############################################################################
class GuiDraw(object):
    """
    Base Class for GuiDraw
    - Loop through all its sub-classes and create instance of the sub-classes
      that has an entry in the xml definition
    - GenGuiDraw factory method returns a matched GuiDraw subclass object
    - Overrides the __call__() magic method to make the instance of subclasses
      callable for slot event callbacks.
    - Subclass naming must obey following format: gui_elem_name + 'Draw'
    """
    clsGuiDraws = {}

    @classmethod
    def GenGuiDraw(cls, confdict, parent=None):
        """
        Factory Method to generate Gui Elements defined in XML configuration

        example:
            confdict = { 'widget(QWidget)': {}, action(QAction): {},
                         'name': 'TabWidget', 'class': 'QTabWidget',
                         'property': [{}] or {}, 'attribute': [{}] or {} } }
        """
        if 'name' in confdict.keys() and 'class' in confdict.keys():
            # all QWidget has a name and a class, except action, which has 'class' added to confdict
            if confdict['name'] in cls.clsGuiDraws.keys():
                # found existing mapping
                _logger.info('Found Existing Mapping: {}'.format(confdict['name']))
                return cls.clsGuiDraws[confdict['name']]
            else:
                # No existing mapping, create one

                # for subcls in cls.Subclasses():
                _logger.info('class:{} parent:{} hasattr {}'.format(confdict['class'], parent, hasattr(QtGui, confdict['class'])))
                if confdict['class'] == 'QProcessSlot':
                    # create the QProcessSlot's sub class object
                    _logger.debug('GenUI: create: ({}){} parent: {}'.format(confdict['class'], confdict['name'], parent.objectName() if parent is not None else 'None'))
                    cls.clsGuiDraws.update({confdict['name']: QProcessSlot.GenSlot(confdict, parent)})
                elif hasattr(QtGui, confdict['class']):
                    #
                    # FIXME: also need to include additional slots/signals per widgets from QtDesigner
                    #
                    if parent is None:
                        # dynamically add additional class variable, 'initialised' to the root gui class using build-in type()
                        subcls = type(confdict['class'], (getattr(QtGui, confdict['class']),), dict(initialised = QtCore.pyqtSignal([dict])))
                    else:
                        subcls = getattr(QtGui, confdict['class'])
                    if confdict['class'] == subcls.__name__:
                        _logger.debug('GenUI: subcls:{}'.format(subcls))
                    #
                    # Tips for Using Layouts
                    #
                    # When you use a layout, you do not need to pass a parent when constructing the child widgets.
                    # The layout will automatically re-parent the widgets (using QWidget::setParent()) so that they
                    # are children of the widget on which the layout is installed.
                    #
                    # Widgets in a layout are children of the widget on which the layout is installed, not
                    # of the layout itself. Widgets can only have other widgets as parent, not layouts.
                    #
                    # You can nest layouts using addLayout() on a layout; the inner layout then becomes a child
                    # of the layout it is inserted into.
                    #
                    if isinstance(parent, QtGui.QLayout):
                        # if parent is a layout, create widgets without a parent,
                        # then add the widgets to the layout, and they will be re-parent-ed

                        # cls.clsGuiDraws.update({confdict['name']: subcls(confdict)})
                        if issubclass(subcls, QtGui.QLayout):
                            _logger.debug('GenUI: create: ({}){}'.format(confdict['class'], confdict['name']))
                            cls.clsGuiDraws.update({confdict['name']: subcls()})
                        else:
                            _logger.debug('GenUI: create: ({}){} parentWidget:{}'.format(confdict['class'], confdict['name'], parent.parentWidget()))
                            cls.clsGuiDraws.update({confdict['name']: subcls(parent.parentWidget())})

                        if isinstance(cls.clsGuiDraws[confdict['name']], QtGui.QLayout):
                            # Add the newly created layout to the parent layout
                            _logger.debug('GenUI: add layout: {} -> {}'.format(parent.objectName(), confdict['name']))
                            parent.addLayout(cls.clsGuiDraws[confdict['name']])
                        elif isinstance(cls.clsGuiDraws[confdict['name']], QtGui.QWidget):
                            # Add the newly created widget to the parent layout
                            _logger.debug('GenUI: add widget: {} -> {}'.format(parent.objectName(), confdict['name']))
                            parent.addWidget(cls.clsGuiDraws[confdict['name']])
                    else:
                        _logger.debug('GenUI: create: ({}){} parent: {}'.format(confdict['class'], confdict['name'], parent.objectName() if parent is not None else 'None'))
                        # cls.clsGuiDraws.update({confdict['name']: subcls(confdict, parent)})
                        cls.clsGuiDraws.update({confdict['name']: subcls(parent)})

                        if isinstance(parent, QtGui.QTabWidget) and isinstance(cls.clsGuiDraws[confdict['name']], QtGui.QWidget):
                            # add widget to the parent TabWidget
                            _logger.debug('GenUI: add tab: {} -> {}'.format(parent.objectName(), confdict['name']))
                            parent.addTab(cls.clsGuiDraws[confdict['name']], _fromUtf8(""))
                        elif isinstance(parent, QtGui.QWidget) and isinstance(cls.clsGuiDraws[confdict['name']], QtGui.QLayout):
                            # add layout to the parent widget
                            _logger.debug('GenUI: set layout: {} -> {}'.format(parent.objectName(), confdict['name']))
                            parent.setLayout(cls.clsGuiDraws[confdict['name']])
                        elif isinstance(parent, QtGui.QWidget) and isinstance(cls.clsGuiDraws[confdict['name']], QtGui.QWidget):
                            # add widget to the parent widget
                            _logger.debug('GenUI: set parent: {} -> {}'.format(confdict['name'], parent.objectName()))
                            cls.clsGuiDraws[confdict['name']].setParent(parent)

                cls.setupConfig(cls.clsGuiDraws[confdict['name']], confdict, parent)
                # attribute are for the parent class to set
                if 'attribute' in confdict.keys() and parent is not None and isinstance(parent, QtGui.QTabWidget):
                    cls.setupAttribute(parent, cls.clsGuiDraws[confdict['name']], _convertList(confdict['attribute']))

                return cls.clsGuiDraws[confdict['name']]

            # if all subclasses cannot be matched, raise an error
            raise TypeError('Cannot find a suitable GuiElement type')
        else:
            raise TypeError('GuiDraw element does not have a name')

    @classmethod
    def Name(cls):
        return cls.__name__[0:-4]

    ###########################################################################
    # QObject related
    ###########################################################################
    @classmethod
    def setupConfig(cls, qobj, confdict, parent=None):
        """
        Setting up the GUI Element qobj
        """
        def _setupProperty(proplist, parent):
            for prop in proplist:
                # 2. actual configurations for all UI types in this giant method
                if prop['name'] == 'sizepolicy':
                    # size policy
                    sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
                    sizePolicy.setHorizontalStretch(0)
                    sizePolicy.setVerticalStretch(0)
                    sizePolicy.setHeightForWidth(parent.sizePolicy().hasHeightForWidth())
                    qobj.tabRescue.setSizePolicy(sizePolicy)
                elif prop['name'] == 'geometry':
                    # Window Widget Dimension
                    if 'rect' in prop.keys():
                        qobj.setGeometry(QtCore.QRect(int(prop['rect']['x']),
                                                      int(prop['rect']['y']),
                                                      int(prop['rect']['width']),
                                                      int(prop['rect']['height'])))
                    else:
                        if parent is not None:
                            qobj.setGeometry(parent.availableGeometry())
                        else:
                            qobj.setGeometry(QtGui.QDesktopWidget().availableGeometry())
                elif prop['name'] == 'sizeConstraint':
                    qobj.setSizeConstraint(QtGui.QLayout.SetMaximumSize)
                elif prop['name'] == 'text':
                    # Text in QLabel
                    qobj.setText(_fromUtf8(prop['string']) if 'string' in prop.keys() else 'No Text')
                elif prop['name'] == 'pixmap':
                    # Icon in QLabel
                    qobj.setPixmap(QtGui.QPixmap(prop['pixmap']))
                elif prop['name'] == 'readOnly':
                    qobj.setReadOnly(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'icon':
                    qobj.setIcon(QtGui.QIcon(QtGui.QPixmap(prop['icon'])))
                elif prop['name'] == 'toolTip':
                    qobj.setToolTip(_fromUtf8(prop['string']) if 'string' in prop.keys() else 'No Tip')
                elif prop['name'] == 'checkable':
                    qobj.setCheckable(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'editable':
                    qobj.setEditable(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'minimum':
                    qobj.setMinimum(int(prop['number']))
                elif prop['name'] == 'maximum':
                    qobj.setMaximum(int(prop['number']))
                elif prop['name'] == 'singleStep':
                    qobj.setSingleStep(int(prop['number']))
                elif prop['name'] == 'pageStep':
                    pass
                elif prop['name'] == 'orientation':
                    if 'Horitzontal' in prop['enum']:
                        qobj.setOrientation(QtGui.Qt.Horizontal)
                    else:
                        qobj.setOrientation(QtGui.Qt.Vertical)
                elif prop['name'] == 'tickInterval':
                    qobj.setTickInterval(int(prop['number']))
                elif prop['name'] == 'tickPosition':
                    if 'NoTicks' in prop['enum']:
                        qobj.setTickPosition(QtGui.QSlider.NoTicks)
                    elif 'BothSides' in prop['enum']:
                        qobj.setTickPosition(QtGui.QSlider.TicksBothSides)
                    elif 'TicksAbove' in prop['enum']:
                        qobj.setTickPosition(QtGui.QSlider.TicksAbove)
                    elif 'TicksBelow' in prop['enum']:
                        qobj.setTickPosition(QtGui.QSlider.TicksBelow)
                    elif 'TicksLeft' in prop['enum']:
                        qobj.setTickPosition(QtGui.QSlider.TicksLeft)
                    elif 'TicksRight' in prop['enum']:
                        qobj.setTickPosition(QtGui.QSlider.TicksRight)
                elif prop['name'] == 'selection':
                    pass
                elif prop['name'] == 'title':
                    # menu title
                    qobj.setTitle(_fromUtf8(prop['string']) if 'string' in prop.keys() else 'No Title')
                elif prop['name'] == 'visible':
                    qobj.setVisible(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'floatable':
                    qobj.setFloatable(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'movable':
                    qobj.setMovable(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'windowTitle':
                    # Window Title
                    qobj.setWindowTitle(_fromUtf8(prop['string']) if 'string' in prop.keys() else 'TechNexion Rescue System')
                elif prop['name'] == 'tabPosition':
                    # Tab position
                    if 'East' in prop['enum']:
                        qobj.setTabPosition(QtGui.QTabWidget.East)
                    elif 'South' in prop['enum']:
                        qobj.setTabPosition(QtGui.QTabWidget.South)
                    elif 'West' in prop['enum']:
                        qobj.setTabPosition(QtGui.QTabWidget.West)
                    else:
                        qobj.setTabPosition(QtGui.QTabWidget.North)
                elif prop['name'] == 'currentIndex':
                    # Current Index
                    qobj.setCurrentIndex(int(prop['number']) if 'number' in prop.keys() else 0)
                elif prop['name'] == 'shortcut':
                    qobj.setShortcut(_translate(parent.objectName(), _fromUtf8(prop['string']) if 'string' in prop.keys() else '', None))
                    # self.setShortcut(_translate(parent, "Ctrl+O", None))
                    # self.setText(parent, QtGui.QKeySequence(_translate(_fromUtf8(prop['string']))) if 'string' in prop.keys() else '', None)
                elif prop['name'] == 'font':
                    font = QtGui.QFont(_fromUtf8(prop['font']['family']))
                    font.setPointSize(int(prop['font']['pointsize']) if 'pointsize' in prop['font'] else 11)
                    font.setWeight(int(prop['font']['weight']) if 'weight' in prop['font'] else 50)
                    #     QFont.Light     25     25
                    #     QFont.Normal    50     50
                    #     QFont.DemiBold  63     63
                    #     QFont.Bold      75     75
                    #     QFont.Black     87     87
                    font.setItalic(False if prop['font']['italic'] == 'false' else True)
                    font.setBold(False if prop['font']['bold'] == 'false' else True)
                    qobj.setFont(font)
                elif prop['name'] == 'rowCount':
                    qobj.setRowCount(int(prop['number']))
                elif prop['name'] == 'columnCount':
                    qobj.setColumnCount(int(prop['number']))
                elif prop['name'] == 'selectionMode':
                    if 'SingleSelection' in prop['enum']:
                        qobj.setSelectionMode(QtGui.QAbstractItemView.SingleSelection)
                    elif 'ContiguousSelection' in prop['enum']:
                        qobj.setSelectionMode(QtGui.QAbstractItemView.ContiguousSelection)
                    elif 'ExtendedSelection' in prop['enum']:
                        qobj.setSelectionMode(QtGui.QAbstractItemView.ExtendedSelection)
                    elif 'MultiSelection' in prop['enum']:
                        qobj.setSelectionMode(QtGui.QAbstractItemView.MultiSelection)
                    elif 'NoSelection' in prop['enum']:
                        qobj.setSelectionMode(QtGui.QAbstractItemView.NoSelection)
                elif prop['name'] == 'selectionBehavior':
                    if 'SelectRows' in prop['enum']:
                        qobj.setSelectionBehavior(QtGui.QAbstractItemView.SelectRows)
                    elif 'SelectItems' in prop['enum']:
                        qobj.setSelectionBehavior(QtGui.QAbstractItemView.SelectItems)
                    elif 'SelectColumns' in prop['enum']:
                        qobj.setSelectionBehavior(QtGui.QAbstractItemView.SelectColumns)

        def _setupColumnHeader(colslist, parent):
            for index, col in enumerate(colslist, start=0):
                item = QtGui.QTableWidgetItem()
                for prop in _convertList(col['property']):
                    if prop['name'] == 'text':
                        item.setText(_translate(qobj.window().objectName(), prop['string'], None))
                    # FIXME: Setting up future TableWidgetItem's property here

                qobj.setHorizontalHeaderItem(index, item)

        def _setupRowHeader(rowlist, parent):
            for index, row in enumerate(rowlist, start=0):
                item = QtGui.QTableWidgetItem()
                for prop in _convertList(row['property']):
                    if prop['name'] == 'text':
                        item.setText(_translate(qobj.window().objectName(), prop['string'], None))
                    # FIxme: Setting up other TableWidgetItem's property here
                qobj.setVerticalHeaderItem(index, item)

        # 1. setup name (common to all Qt widgets)
        if 'name' in confdict:
            qobj.setObjectName(_fromUtf8(confdict['name']))
        else:
            qobj.setObjectName(_fromUtf8(confdict['class']).lstrip('Q') if 'class' in confdict else '')
        if 'property' in confdict:
            # 2. setup GUI element's properties
            _setupProperty(_convertList(confdict['property']), parent)
        if 'column' in confdict:
            # 3a. setup column header for tableWidget
            _setupColumnHeader(_convertList(confdict['column']), parent)
        if 'row' in confdict:
            # 3b. setup row headers for tableWidget
            _setupRowHeader(_convertList(confdict['row']), parent)

    @classmethod
    def setupAttribute(cls, parent, child, attrs):
        for att in attrs:
            if isinstance(att, dict):
                if att['name'] == 'title': # for tab title
                    parent.setTabText(parent.indexOf(child), _translate(parent.objectName(), att['string'], None))



###############################################################################
#
# QProcessSlot and subclasses
#
# In PyQt4, a slot is a callable method with a signature defined by
# qtCore.pyqtSLOT(args_types)
#
###############################################################################
class QProcessSlot(QtGui.QWidget):
    """
    Base Class for Slots
    sub classess use the decorator to add its entry into cls.subclasses
    The GenSlot is called to generate subclass instance
    """

    subclasses = {}

    @classmethod
    def Name(cls):
        return cls.__name__

    @classmethod
    def registerProcessSlot(cls, slot_name):
        def decorator(subclass):
            cls.subclasses[slot_name] = subclass
            return subclass
        return decorator

    @classmethod
    def GenSlot(cls, confdict, parent):
        """
        Factory Method Design Pattern
        example:
            confdict = {'name': 'returnPressed', 'property' : [{}] or {} }
        """
        if confdict['name'] not in cls.subclasses.keys():
            raise ValueError('Bad slot name: {}'.format(confdict['name']))
        return cls.subclasses[confdict['name']](confdict, parent)

    def __init__(self, confdict, parent = None):
        QtGui.QWidget.__init__(self, parent)
        GuiDraw.setupConfig(self, confdict, parent)

    def _setCommand(self, cmd):
        self.mCmd.update(cmd)

    @pyqtSlot()
    @pyqtSlot(int)
    @pyqtSlot(str)
    @pyqtSlot(dict)
    def processSlot(self, inputs = None):
        """
        called by signals from other GObject components
        To be overriden by all sub classes
        """
        try: self.request.disconnect()
        except: pass
        if inputs is not None and 'viewer' in inputs.keys():
            self.mViewer = inputs['viewer']
            self.request.connect(self.mViewer.request)
            _logger.info('connect {}.request to {}'.format(self, self.mViewer.request))
        self.process(inputs)

    def process(self, inputs):
        """
        To be overridden
        """
        pass

    @pyqtSlot()
    @pyqtSlot(int)
    @pyqtSlot(str)
    @pyqtSlot(dict)
    def resultSlot(self, results = None):
        """
        called by signals from other GObject components
        To be overriden by all sub classes
        """
        if self._hasSameCommand(results):
            self.parseResult(results)

    def parseResult(self, results):
        """
        To be overridden
        """
        pass

    def procResult(self):
        return True

    def _findChildElem(self, elemName):
        return self.window().findChild(QtGui.QWidget, elemName)

    def _hasSameCommand(self, results):
        # match exactly 1 key, value from self.mCmd
        #return self.mCmd.items() <= results.items()
        if dict(results, **self.mCmd) == results:
            return True
        return False



@QProcessSlot.registerProcessSlot('detectDevice')
class detectDeviceSlot(QProcessSlot):
    request = pyqtSignal(dict)
    success = pyqtSignal(str)
    fail = pyqtSignal(str)

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
        self.mCmd = {}
        self.mViewer = None
        self.mResults = ''
        self.mErrors = ''

    def process(self, inputs = None):
        """
        Handle detect device callback slot
        NOTE: inputs just contains a {'viewer': guiviwer_object}
        """
        self._setCommand({'cmd': 'info', 'target': 'som'})
        self.request.emit(self.mCmd)

    def parseResult(self, results):
        """
        Handle returned detect device results from PyQt Msger
        """
        if 'found_match' in results:
            form, cpu, baseboard = results['found_match'].split(',')
            self._findChildElem('lblCpu').setText(cpu)
            self._findChildElem('lblFormFactor').setText(form)
            self.success.emit('Found: {} {} {}\n'.format(cpu, form, baseboard))
        else:
            form = cpu = baseboard = '' # same reference
            self._findChildElem('lblCpu').setText('Cpu')
            self._findChildElem('lblFormFactor').setText('Form Factor')
            self.fail.emit('Target Device SOM info not found.\n')



@QProcessSlot.registerProcessSlot('crawlWeb')
class crawlWebSlot(QProcessSlot):
    """
    Potentially the Crawling Mechansim is done in a long process thread.
    If the long process is needed, it could possibly be done using QThread in Qt.
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(int, int, object) # QtGui.PyQt_PyObject)
    fail = pyqtSignal(str)

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
        self.mCmds = []
        self.mViewer = None
        self.mResults = []
        self.mErrors = ''

    def _setCommand(self, cmd):
        self.mCmds.append(cmd)
        _logger.debug("crawlWebSlot set request: {}".format(self.mCmds[-1]))

    def process(self, inputs = None):
        """
        Handle crawlWeb callback slot
        NOTE: inputs just contains a {'viewer': guiviwer_object}
        """
        params = {}
        if 'location' not in inputs:
            params.update({'location': '/'})
        if 'target' not in inputs:
            params.update({'target': 'http://rescue.technexion.net'})
        params.update(inputs)
        self.__crawlUrl(params) # e.g. /pico-imx7/pi-070/

    def __crawlUrl(self, params):
        self._setCommand({'cmd': 'info', 'target': params['target'], 'location': params['location']})
        self.request.emit(self.mCmds[-1])

    def parseResult(self, results):
        #print('crawlWeb result: {}'.format(results))
        if 'total_uncompressed' in results.keys() or 'total_size' in results.keys():
            # step 3: figure out the xz file to download
            # Extract XZ file info and add to the table
            if 'total_uncompressed' in results:
                uncompsize = results['total_uncompressed']
            elif 'total_size' in results:
                uncompsize = results['total_size']
            else:
                uncompsize = 0
            form, cpu, board, display, fname = self._parseSOMInfo(results['location'])
            os, ver = self._parseFilename(fname.rstrip('.xz'))
            url = results['target'] + '/rescue' + results['location']
            # cpu, form, board, display, os, ver, size(uncompsize), url
            self.mResults.append({'cpu': cpu, 'form': form, 'board': board, 'display': display, 'os': os, 'ver': ver, 'size': uncompsize, 'url': url})
            if len(self.mResults):
                self.procResult()
            else:
                self.fail.emit('Did not find any suitable xz file\n')

        elif 'file_list' in results.keys():
            parsedList = self.__parseWebList(results)
            if len(parsedList) > 0 and isinstance(parsedList, list):
                for item in parsedList:
                    if item[1].endswith('/'):
                        pobj = self.__checkUrl(item[2])
                        if pobj is not None:
                            # print('net item path: {}'.format(pobj.path))
                            self.__crawlUrl({'cmd': results['cmd'], 'target':'http://rescue.technexion.net', 'location':pobj.path.replace('/rescue/', '/')})
                    elif item[1].endswith('xz'):
                        # FIXME: match against the target device, and send request to obtain uncompressed size
                        # print('net xzfile path: {} {} {}'.format(item[1], item[2], item[2].split('/rescue/',1)))
                        if self.__matchDevice(item[2].split('/rescue/', 1)[1]):
                            self.__crawlUrl({'cmd': results['cmd'], 'target':'http://rescue.technexion.net', 'location': '/' + item[2].split('/rescue/', 1)[1]})
            self.fail.emit('Crawling url {} to find suitable xz file.\n'.format(results['location']))

    def __parseWebList(self, results):
        if 'file_list' in results and isinstance(results['file_list'], dict):
            # We know that file_list is a dictionary because we send it from the server
            return [(i, k, v) for i, (k, v) in enumerate(sorted(results['file_list'].items()))]
        return []

    def __checkUrl(self, url):
        try:
            result = urlparse(url)
            return result if all([result.scheme, result.netloc]) else None
        except:
            return None

    def procResult(self):
        if isinstance(self.mResults, list) and len(self.mResults):
            # clear the TableWidgets and set the found xz file into TableWidget
            tbl = self._findChildElem('tableRescueFiles')
            tbl.clear()
            self.__insertToTable(tbl)
            return True
        else:
            return False

    def __insertToTable(self, qtable):
        qtable.setColumnCount(len(self.mResults[0]))
        hdrs = [k for k in self.mResults[0].keys()]
        #hdrs.remove('url')
        qtable.setHorizontalHeaderLabels(hdrs)
        qtable.setRowCount(len(self.mResults))
        for r, row in enumerate(self.mResults, start=0):
            # cpu, form, board, display, os, ver, size(uncompsize), url
            for i, k in enumerate(row.keys(), start=0):
                #qtable.setItem(r, i, QtGui.QTableWidgetItem(row[k]))
                #if k != 'url':
                item = QtGui.QTableWidgetItem(row[k])
                item.setData(QtCore.Qt.UserRole, row['url'])
                self.success.emit(r, i, item)

    def __matchDevice(self, filename):
        # step 2: find menu items that matches as cpu, form, but not baseboard
        cpu = self._findChildElem('lblCpu').text().lower()
        form = self._findChildElem('lblFormFactor').text().lower()
        if (cpu[0:4] in filename.lower() or cpu in filename.lower()):
            if form in filename.lower():
                _logger.debug('Matched {} {}... {}'.format(cpu[0:4], form, filename))
                return True
        return False

    def _parseSOMInfo(self, path):
        p = re.compile('\/(\w+)[_|-](\w+)\/(\w+)-(\w+)\/(.+)\.xz', re.IGNORECASE)
        m = p.match(path)
        if m:
            return m.groups()

    def _parseFilename(self, fname):
        if '-' in fname:
            os, ver = fname.split('-', 1)
        else:
            os = fname
            ver = ''
        return os, ver

    def _hasSameCommand(self, results):
        # match exact key, value from self.mCmd
        #return self.mCmd.items() <= results.items()
        for cmd in self.mCmds:
            #print('get request: {}'.format(cmd))
            if dict(results, **cmd) == results:
                if 'status' in results:
                    if results['status'] == 'success':
                        self.mCmds.remove(cmd)
                return True
        return False



@QProcessSlot.registerProcessSlot('scanStorage')
class scanStorageSlot(QProcessSlot):
    """
    Handle scanStorage callback slot
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(int, int, object) # QtGui.PyQt_PyObject)
    fail = pyqtSignal(str)

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
        self.mResults = []
        self.mErrors = ''
        self.mCmd = {}
        self.mViewer = None

    def process(self, inputs = None):
        # step 4: request for list of targets storage device
        self._setCommand({'cmd': 'info', 'target': 'emmc', 'location': 'disk'})
        self.request.emit(self.mCmd)

    def parseResult(self, results):
        # step 5: ask user to choose the target to flash
        listTarget = self._parseTargetList(results)
        if (len(listTarget)):
            for tgt in listTarget:
                # 'name', 'node path', 'disk size'
                self.mResults.append({'name': tgt[1], 'path':tgt[2]['device_node'], 'size':int(tgt[2]['size']) * 512})
            if len(self.mResults):
                self.procResult()
            else:
                self.fail.emit('Did not find any suitable xz file\n')
        else:
            self.fail.emit('Not found any target\n')

    def _findAttrs(self, keys, dc):
        """
        For dictionary and dictionary within a dictionary
        """
        for k, v in dc.items():
            if k in keys:
                yield (k, v)
            elif isinstance(v, dict):
                for ret in self._findAttrs(keys, v):
                    yield ret

    def _parseTargetList(self, result):
        data = {}
        for k, v in result.items():
            if isinstance(v, dict):
                data.update({k: {att[0]:att[1] for att in self._findAttrs(['device_node', 'size'], v)}})
        return [(i, k, v) for i, (k, v) in enumerate(data.items())]

    def procResult(self):
        if isinstance(self.mResults, list) and len(self.mResults):
            # clear the TableWidgets and set the found xz file into TableWidget
            tbl = self._findChildElem('tableTargetStorage')
            tbl.clear()
            self.__insertToTable(tbl)
            return True
        else:
            return False

    def __insertToTable(self, qtable):
        qtable.setColumnCount(len(self.mResults[0]))
        hdrs = [k for k in self.mResults[0].keys()]
        #hdrs.remove('path')
        qtable.setHorizontalHeaderLabels(hdrs)
        qtable.setRowCount(len(self.mResults))
        for r, row in enumerate(self.mResults, start=0):
            # name, path, size
            for i, k in enumerate(row.keys(), start=0):
                #qtable.setItem(r, i, QtGui.QTableWidgetItem('{}'.format(row[k])))
                #if k != 'path':
                item = QtGui.QTableWidgetItem('{}'.format(row[k]))
                item.setData(QtCore.Qt.UserRole, row['path'])
                self.success.emit(r, i, item)



@QProcessSlot.registerProcessSlot('downloadImage')
class downloadImageSlot(QProcessSlot):
    """
    Handles button click event to issue cmd to download and flash
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(int)
    fail = pyqtSignal(str)

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
        self.mResults = {}
        self.mErrors = ''
        self.mCmd = {}
        self.mViewer = None
        self.mTimer = QtCore.QTimer()
        self.mTimer.timeout.connect(self._queryResult)
        self.mFileUrl = ''
        self.mTgtStorage = ''
        self.mFlashFlag = False

    def _queryResult(self):
        if self.mViewer:
            self.mResults.update(self.mViewer.queryResult())
            if 'total_uncompressed' in self.mResults and 'bytes_written' in self.mResults:
                pcent = int(float(self.mResults['bytes_written']) / float(self.mResults['total_uncompressed']) * 100)
                self.success.emit(pcent)

    def process(self, inputs = None):
        # python3 view.py {download -u http://rescue.technexion.net/rescue/pico-imx6/dwarf-070/ubuntu-16.04.xz -t ./ubuntu.img}
        # dlparam = {'cmd': 'download', 'dl_url': menus[int(srcNum)][2], 'tgt_filename': targets[int(tgtNum)][2]['device_node']}
        # grab the dl_url and tgt_filename from the tableRescueFile and tableTargetStorage currentItemChanged() signals
        if not self.mFlashFlag:
            if self.sender().objectName() == 'tableRescueFiles':
                self.mFileUrl = self.sender().currentItem().data(QtCore.Qt.UserRole)
                _logger.debug(inputs, self.mFileUrl)
                self.success.emit(0)

            if self.sender().objectName() == 'tableTargetStorage':
                self.mTgtStorage = self.sender().currentItem().data(QtCore.Qt.UserRole)
                _logger.debug(inputs, self.mTgtStorage)
                self.success.emit(0)

            # step 6: make up the command to download and flash and execute it
            # Need to grab or keep the chooses from file list selection and target list selection
            if self.sender().objectName() == 'pushButtonCmd':
                if self.mFileUrl and self.mTgtStorage:
                    self._setCommand({'cmd': 'download', 'dl_url': self.mFileUrl, 'tgt_filename': self.mTgtStorage})
                    self.request.connect(self.mViewer.request)
                    self.request.emit(self.mCmd)
                else:
                    # prompt for error message
                    QtGui.QMessageBox.information(self, 'Input Error', "Please Choose A file to download\n" \
                                                  "and a storage device to flash", QtGui.QMessageBox.Yes)
            # prompt error message to select a download file and target storage
            if self.sender().objectName() == 'tabWidget' and self.mViewer:
                self.fail.emit('Obtained viewer from initialised() signal\n')
        else:
            # prompt for error message
            QtGui.QMessageBox.information(self, 'Hold your horses', "Please wait until flashing is done...", QtGui.QMessageBox.Yes)

    def parseResult(self, results):
        # step 7: parse the result in a loop until result['status'] != 'processing'
        # Start a timer to query results every 1 second
        if results['status'] == 'processing':
            self.mTimer.start(1)
            self.mFlashFlag = True
        else:
            self.mTimer.stop()
            self.mFlashFlag = False
            QtGui.QMessageBox.information(self, 'Yay', "Flash Complete...", QtGui.QMessageBox.Yes)
