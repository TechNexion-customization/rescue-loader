#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import os
from math import log
from view import CliViewer
from urllib.parse import urlparse
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import QObject, pyqtSignal, pyqtSlot

# import our resource.py with all the pretty images/icons
import resource

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

def _prettySize(n,pow=0,b=1024,u='B',pre=['']+[p+'i'for p in'KMGTPEZY']):
    r,f=min(int(log(max(n*b**pow,1),b)),len(pre)-1),'{:,.%if} %s%s'
    return (f%(abs(r%(-r-1)),pre[r],u)).format(n*b**pow/b**float(r))

def _convertList(prop):
    # turn properties dict into a list for looping
    plist = []
    if isinstance(prop, list):
        plist.extend(prop)
    elif isinstance(prop, dict):
        plist.append(prop)
    return plist

def _insertToContainer(lResult, qContainer, qSignal):
    """
    Insert results to a container, e.g. QListWidget, QTableWidget, QTreeWidget
    parse the results in a list of dictionaries, and add them to container
    """
    if isinstance(qContainer, QtGui.QListWidget):
        # insert into a listWidget

        # setup widget items
        for r, row in enumerate(lResult, start=0):
            # [{name, path, size}, ...] for storage
            # [{cpu, form, board, display, os, ver, size(uncompsize), url}, ...] for rescue images

            item = QtGui.QListWidgetItem() #item = QtGui.QListWidgetItem(qContainer)
            if 'path' in row.keys():
                # storage disk
                _logger.debug('{} {} size:{}'.format(row['name'], row['path'], row['size']))
                item.setText('{}\n{}'.format(row['path'], _prettySize(int(row['size']))))
                item.setIcon(QtGui.QIcon(QtGui.QPixmap(":/res/images/micro_sd_recover.png")))
                item.setToolTip('{}\n{} bytes'.format(row['name'], row['size']))
                item.setData(QtCore.Qt.UserRole, row['path'])
                #item.setData(QtCore.Qt.UserRole, './ubuntu.img')
            elif 'url' in row.keys():
                # rescue images
                _logger.debug('{} {} {} {} {} {} {}'.format(row['cpu'], row['form'], row['board'], row['display'], row['os'], row['ver'], row['size']))
                item.setText('{}-{}\n{}\n{}\n{}'.format(row['os'], row['ver'], row['board'], row['display'], _prettySize(int(row['size']))))
                if row['os'].lower() == 'android':
                    item.setIcon(QtGui.QIcon(QtGui.QPixmap(":/res/images/android.png")))
                elif row['os'].lower() == 'ubuntu':
                    item.setIcon(QtGui.QIcon(QtGui.QPixmap(":/res/images/ubuntu.png")))
                elif row['os'].lower() == 'yocto':
                    item.setIcon(QtGui.QIcon(QtGui.QPixmap(":/res/images/yocto")))
                else:
                    item.setIcon(QtGui.QIcon(QtGui.QPixmap(":/res/images/NewTux.png")))
                item.setToolTip('{}\n{}\n{} bytes'.format(row['board'], row['display'], row['size']))
                item.setData(QtCore.Qt.UserRole, row['url'])
            qSignal.emit(item)

    elif isinstance(qContainer, QtGui.QTableWidget):
        # insert into a tableWidget

        # setup table headers
        qContainer.setColumnCount(len(lResult[0]))
        hdrs = [k for k in lResult[0].keys()]
        qContainer.setHorizontalHeaderLabels(hdrs)
        qContainer.setRowCount(len(lResult))

        # setup widget items
        for r, row in enumerate(lResult, start=0):
            # [{name, path, size}, ...] for storage
            # [{cpu, form, board, display, os, ver, size(uncompsize), url}, ...] for rescue images
            for i, k in enumerate(row.keys(), start=0):
                item = QtGui.QTableWidgetItem(row[k])
                if 'path' in row.keys():
                    item.setData(QtCore.Qt.UserRole, row['path'])
                elif 'url' in row.keys():
                    item.setData(QtCore.Qt.UserRole, row['url'])
                qSignal.emit(r, i, item)

    elif isinstance(qContainer, QtGui.QTreeWidget):
        # TODO: Add support for insert into a treeWidget
        return False

    return True



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
                _logger.info('Found Existing GUI Element: {}'.format(confdict['name']))
                return cls.clsGuiDraws[confdict['name']]
            else:
                # No existing mapping, create one

                _logger.debug('class:{} parent:{} hasattr {}'.format(confdict['class'], parent, hasattr(QtGui, confdict['class'])))
                if confdict['class'] == 'QProcessSlot':
                    # Include additional custom slots/signals per widgets from QtDesigner
                    # create the QProcessSlot's sub class object
                    _logger.debug('GenUI: create: ({}){} parent: {}'.format(confdict['class'], confdict['name'], parent.objectName() if parent is not None else 'None'))
                    cls.clsGuiDraws.update({confdict['name']: QProcessSlot.GenSlot(confdict, parent)})

                elif hasattr(QtGui, confdict['class']) or confdict['class'] == 'Line':
                    # DIRTY hack for drawing h/v line in QtDesigner with confdict['class'] == 'Line'

                    if parent is None:
                        # dynamically add additional class variable, 'initialised' to the root gui class using build-in type()
                        subcls = type(confdict['class'], (getattr(QtGui, confdict['class']),), dict(initialised = QtCore.pyqtSignal([dict])))
                    else:
                        # get the sub class type from QtGui
                        if confdict['class'] == 'Line':
                            # DIRTY hack for drawing h/v line in QtDesigner
                            # we use QFrame to draw line
                            subcls = getattr(QtGui, 'QFrame')
                        else:
                            subcls = getattr(QtGui, confdict['class'])

                    if confdict['class'] == subcls.__name__:
                        _logger.info('GenUI: has subcls: {}'.format(subcls))
                    elif confdict['class'] == 'Line':
                        # DIRTY HACK for QtDesigner vertical/horizontal lines
                        _logger.info('GenUI: draw line with subcls: {}'.format(subcls))
                        if 'property' in confdict.keys():
                            for it in confdict['property']:
                                if it['name'] == 'orientation':
                                    confdict['property'].remove(it)
                                    direction = 'QFrame::VLine' if 'Vertical' in it['enum'] else 'QFrame::HLine'
                                    confdict['property'].append({'name': 'frameShape', 'enum': direction})

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
                    # You can nest layouts using addLayout() on a layout (boxlayout/gridlayout);
                    # the inner layout then becomes a child of the layout it is inserted into.
                    #
                    if isinstance(parent, QtGui.QLayout):
                        _logger.debug('parent layout adding child layout/widget with config dict: {}'.format(confdict))
                        # create GUI subclass object references
                        _logger.debug('GenUI: create subclass({}) obj ref: {}'.format(confdict['class'], confdict['name']))
                        # Important!!! if parent is a layout, create child widgets without a parent,
                        # then add the child widgets to the layout, these widgets will be re-parent-ed
                        cls.clsGuiDraws.update({confdict['name']: subcls()})

                        if isinstance(cls.clsGuiDraws[confdict['name']], QtGui.QLayout):
                            # Add the newly created child layout to the parent layout
                            _logger.debug('GenUI: parent: {} adds {} layout'.format(parent.objectName(), confdict['name']))
                            if isinstance(parent, QtGui.QGridLayout):
                                # For parent as grid layouts, addLayout() requires additional
                                # row, column, rowspan, and colspan (and alignment)
                                # e.g. parent.addLayout(r, c, rs, cs, l)
                                rs = int(confdict['rowspan']) if 'rowspan' in confdict else 1
                                cs = int(confdict['colspan']) if 'colspan' in confdict else 1
                                r = int(confdict['row']) if 'row' in confdict else 0
                                c = int(confdict['column']) if 'column' in confdict else 0
                                parent.addLayout(cls.clsGuiDraws[confdict['name']], r, c, rs, cs)
                            elif isinstance(parent, QtGui.QBoxLayout):
                                parent.addLayout(cls.clsGuiDraws[confdict['name']])

                        elif isinstance(cls.clsGuiDraws[confdict['name']], QtGui.QWidget):
                            # Add the newly created child widget to the parent layout
                            _logger.debug('GenUI: parent: {} adds {} widget'.format(parent.objectName(), confdict['name']))
                            if isinstance(parent, QtGui.QGridLayout):
                                # For parent as grid layouts, addWidget() requires additional
                                # row, column, rowspan, and colspan (and alignment)
                                # e.g. parent.addWidget(r, c, rs, cs, l)
                                rs = int(confdict['rowspan']) if 'rowspan' in confdict else 1
                                cs = int(confdict['colspan']) if 'colspan' in confdict else 1
                                r = int(confdict['row']) if 'row' in confdict else 0
                                c = int(confdict['column']) if 'column' in confdict else 0
                                parent.addWidget(cls.clsGuiDraws[confdict['name']], r, c, rs, cs)
                            elif isinstance(parent, QtGui.QBoxLayout):
                                parent.addWidget(cls.clsGuiDraws[confdict['name']])

                    else:
                        _logger.debug('GenUI: create subclass({}) obj ref: {} parent: {}'.format(confdict['class'], confdict['name'], parent.objectName() if parent is not None else 'None'))
                        # cls.clsGuiDraws.update({confdict['name']: subcls(confdict, parent)})
                        cls.clsGuiDraws.update({confdict['name']: subcls(parent)})

                        if isinstance(parent, QtGui.QTabWidget) and isinstance(cls.clsGuiDraws[confdict['name']], QtGui.QWidget):
                            # add tab page widget to the parent TabWidget
                            _logger.debug('GenUI: parent: {} adds tab widget: {}'.format(parent.objectName(), confdict['name']))
                            parent.addTab(cls.clsGuiDraws[confdict['name']], _fromUtf8(confdict['name']))
                        elif isinstance(parent, QtGui.QWidget) and isinstance(cls.clsGuiDraws[confdict['name']], QtGui.QLayout):
                            # add layout to the parent widget
                            _logger.debug('GenUI: parent: {} sets layout: {}'.format(parent.objectName(), confdict['name']))
                            parent.setLayout(cls.clsGuiDraws[confdict['name']])
                        elif isinstance(parent, QtGui.QWidget) and isinstance(cls.clsGuiDraws[confdict['name']], QtGui.QWidget):
                            # add widget to the parent widget
                            _logger.debug('GenUI: parent: {} adds child widget: {}'.format(confdict['name'], parent.objectName()))
                            parent.addWidget(cls.clsGuiDraws[confdict['name']])

                else:
                    raise TypeError('Warning: Cannot find GUI class: {} in QtGui'.format(confdict['class']))

                _logger.info('call setupConfig for GUI class:{}'.format(confdict['class']))
                # setup the widget's configuration
                cls.setupConfig(cls.clsGuiDraws[confdict['name']], confdict, parent)

                # attribute are for the parent class to set
                if 'attribute' in confdict.keys() and parent is not None and isinstance(parent, QtGui.QTabWidget):
                    cls.setupAttribute(cls.clsGuiDraws[confdict['name']], _convertList(confdict['attribute']), parent)

                # setup additional headers for the TableWidget qobj
                if isinstance(cls.clsGuiDraws[confdict['name']], QtGui.QTableWidget):
                    cls.setupTableHeader(cls.clsGuiDraws[confdict['name']], confdict, parent)

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
            _logger.debug('_setupProperty: {}'.format(proplist))
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

                elif prop['name'] == 'styleSheet':
                    if 'string' in prop.keys():
                        qobj.setStyleSheet(_fromUtf8(prop['string']['_text']))

                # QLabel
                elif prop['name'] == 'text':
                    # Text in QLabel
                    qobj.setText(_fromUtf8(prop['string']) if 'string' in prop.keys() else 'No Text')
                elif prop['name'] == 'pixmap':
                    # Icon in QLabel
                    if isinstance(prop['pixmap'], dict):
                        qobj.setPixmap(QtGui.QPixmap(prop['pixmap']['_text']))
                    else:
                        qobj.setPixmap(QtGui.QPixmap(prop['pixmap']))
                elif prop['name'] == 'alignment':
                    # Alignment in QLabel
                    align = QtCore.Qt.AlignLeft
                    if 'AlignLeading' in prop['set']:
                        align = QtCore.Qt.AlignLeft
                    elif 'AlignRight' in prop['set'] or 'AlignTrailing' in prop['set']:
                        align = QtCore.Qt.AlignRight
                    elif 'AlignHCenter' in prop['set']:
                        align = QtCore.Qt.AlignHCenter
                    elif 'AlignJustify' in prop['set']:
                        align = QtCore.Qt.AlignJustify
                    if 'AlignTop' in prop['set']:
                        align |= QtCore.Qt.AlignTop
                    elif 'AlignBottom' in prop['set']:
                        align |= QtCore.Qt.AlignBottom
                    elif 'AlignVCenter' in prop['set']:
                        align |= QtCore.Qt.AlignVCenter
                    if 'AlignAbsolute' in prop['set']:
                        align = 0x0010
                    if 'AlignCenter' in prop['set']:
                        align = QtCore.Qt.AlignVCenter | QtCore.Qt.AlignHCenter
                    if 'AlignHorizontal_Mask' in prop['set']:
                        align = QtCore.Qt.AlignLeft | QtCore.Qt.AlignRight | QtCore.Qt.AlignHCenter | QtCore.Qt.AlignJustify | QtCore.Qt.AlignAbsolute
                    if 'AlignVertical_Mask' in prop['set']:
                        align = QtCore.Qt.AlignTop | QtCore.Qt.AlignBottom | QtCore.Qt.AlignVCenter
                    qobj.setAlignment(align)
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
                        qobj.setOrientation(QtCore.Qt.Horizontal)
                    else:
                        qobj.setOrientation(QtCore.Qt.Vertical)
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
                    if 'family' in prop['font']:
                        font = QtGui.QFont(_fromUtf8(prop['font']['family']))
                    else:
                        font = QtGui.QFont()
                    font.setPointSize(int(prop['font']['pointsize']) if 'pointsize' in prop['font'] else 11)
                    font.setWeight(int(prop['font']['weight']) if 'weight' in prop['font'] else 50)
                    #     QFont.Light     25     25
                    #     QFont.Normal    50     50
                    #     QFont.DemiBold  63     63
                    #     QFont.Bold      75     75
                    #     QFont.Black     87     87
                    font.setItalic(False if ('italic' in prop['font'] and prop['font']['italic'] == 'false') else True)
                    font.setBold(False if ('bold' in prop['font'] and prop['font']['bold'] == 'false') else True)
                    qobj.setFont(font)

                # QTableWidget
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

                # QFrame
                elif prop['name'] == 'frameShadow':
                    if 'Plain' in prop['enum']:
                        qobj.setFrameShadow(QtGui.QFrame.Plain)
                    elif 'Raised' in prop['enum']:
                        qobj.setFrameShadow(QtGui.QFrame.Raised)
                    elif 'Sunken' in prop['enum']:
                        qobj.setFrameShadow(QtGui.QFrame.Sunken)
                elif prop['name'] == 'lineWidth':
                    qobj.setLineWidth(int(prop['number']))
                elif prop['name'] == 'frameShape':
                    if 'NoFrame' in prop['enum']:
                        qobj.setFrameShape(QtGui.QFrame.NoFrame)
                    elif 'Box' in prop['enum']:
                        qobj.setFrameShape(QtGui.QFrame.Box)
                    elif 'Panel' in prop['enum']:
                        qobj.setFrameShape(QtGui.QFrame.Panel)
                    elif 'StyledPanel' in prop['enum']:
                        qobj.setFrameShape(QtGui.QFrame.StyledPanel)
                    elif 'HLine' in prop['enum']:
                        qobj.setFrameShape(QtGui.QFrame.HLine)
                    elif 'VLine' in prop['enum']:
                        qobj.setFrameShape(QtGui.QFrame.VLine)
                    elif 'WinPanel' in prop['enum']:
                        qobj.setFrameShape(QtGui.QFrame.WinPanel)

                # QListView
                elif prop['name'] == 'viewMode':
                    if 'IconMode' in prop['enum']:
                        qobj.setViewMode(QtGui.QListView.IconMode)
                    elif 'ListMode' in prop['enum']:
                        qobj.setViewMode(QtGui.QListView.ListMode)
                elif prop['name'] == 'layoutMode':
                    if 'SinglePass' in prop['enum']:
                        qobj.setLayoutMode(QtGui.QListView.SinglePass)
                    elif 'Batched' in prop['enum']:
                        qobj.setLayoutMode(QtGui.QListView.Batched)
                elif prop['name'] == 'movement':
                    if 'Static' in prop['enum']:
                        qobj.setMovement(QtGui.QListView.Static)
                    elif 'Free' in prop['enum']:
                        qobj.setMovement(QtGui.QListView.Free)
                    elif 'Snap' in prop['enum']:
                        qobj.setMovement(QtGui.QListView.Snap)
                elif prop['name'] == 'resizeMode':
                    if 'Fixed' in prop['enum']:
                        qobj.setResizeMode(QtGui.QListView.Fixed)
                    elif 'Adjust' in prop['enum']:
                        qobj.setResizeMode(QtGui.QListView.Adjust)
                elif prop['name'] == 'flow':
                    if 'LeftToRight' in prop['enum']:
                        qobj.setFlow(QtGui.QListView.LeftToRight)
                    elif 'TopToBottom':
                        qobj.setFlow(QtGui.QListView.TopToBottom)
                elif prop['name'] == 'gridSize':
                    qobj.setGridSize(QtCore.QSize(int(prop['size']['width']), int(prop['size']['height'])))
                elif prop['name'] == 'editTriggers':
                    trig = QtGui.QAbstractItemView.NoEditTriggers
                    if 'CurrentChanged' in prop['set']:
                        trig |= QtGui.QAbstractItemView.CurrentChanged
                    if 'DoubleClicked' in prop['set']:
                        trig |= QtGui.QAbstractItemView.DoubleClicked
                    if 'SelectedClicked' in prop['set']:
                        trig |= QtGui.QAbstractItemView.SelectedClicked
                    if 'EditKeyPressed' in prop['set']:
                        trig |= QtGui.QAbstractItemView.EditKeyPressed
                    if 'AnyKeyPressed' in prop['set']:
                        trig |= QtGui.QAbstractItemView.AnyKeyPressed
                    if 'AllEditTriggers' in prop['set']:
                        trig |= QtGui.QAbstractItemView.AllEditTriggers
                    qobj.setEditTriggers(trig)
                elif prop['name'] == 'dragDropMode':
                    if 'NoDragDrop' in prop['enum']:
                        qobj.setDragDropMode(QtGui.QAbstractItemView.NoDragDrop)
                    elif 'DragOnly' in prop['enum']:
                        qobj.setDragDropMode(QtGui.QAbstractItemView.DragOnly)
                    elif 'DropOnly' in prop['enum']:
                        qobj.setDragDropMode(QtGui.QAbstractItemView.DropOnly)
                    elif 'DragDrop' in prop['enum']:
                        qobj.setDragDropMode(QtGui.QAbstractItemView.DragDrop)
                    elif 'InternalMove' in prop['enum']:
                        qobj.setDragDropMode(QtGui.QAbstractItemView.InternalMove)
                elif prop['name'] == 'showDropIndicator':
                    qobj.setDropIndicatorShown(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'sortingEnabled':
                    qobj.setSortingEnabled(True if prop['bool'] == 'true' else False)

        # 1. setup name (common to all Qt widgets)
        if 'name' in confdict:
            qobj.setObjectName(_fromUtf8(confdict['name']))
        else:
            qobj.setObjectName(_fromUtf8(confdict['class']).lstrip('Q') if 'class' in confdict else '')
        if 'property' in confdict:
            # 2. setup GUI element's properties
            _setupProperty(_convertList(confdict['property']), parent)

    @classmethod
    def setupTableHeader(cls, qobj, confdict, parent=None):
        """
        Sets up headers for TableWidget Container
        """
        def _setupColumnHeader(columnslist, parent):
            _logger.debug('_setupColumnHeader: {}'.format(columnslist))
            for index, col in enumerate(columnslist, start=0):
                item = QtGui.QTableWidgetItem()
                for prop in _convertList(col['property']):
                    if prop['name'] == 'text':
                        item.setText(_translate(qobj.window().objectName(), prop['string'], None))
                qobj.setHorizontalHeaderItem(index, item)

        def _setupRowHeader(rowslist, parent):
            _logger.debug('_setupRowHeader: {}'.format(rowslist))
            for index, row in enumerate(rowslist, start=0):
                item = QtGui.QTableWidgetItem()
                for prop in _convertList(row['property']):
                    if prop['name'] == 'text':
                        item.setText(_translate(qobj.window().objectName(), prop['string'], None))
                qobj.setVerticalHeaderItem(index, item)

        if 'column' in confdict:
            # 3a. setup column header for tableWidget
            _setupColumnHeader(_convertList(confdict['column']), parent)
        if 'row' in confdict:
            # 3b. setup row headers for tableWidget
            _setupRowHeader(_convertList(confdict['row']), parent)

    @classmethod
    def setupAttribute(cls, child, attrs, parent):
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

    finish = pyqtSignal()

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
        self.mCmds = []
        self.finish.connect(self._reqDone)

    def _setCommand(self, cmd):
        self.mCmds.append(cmd)
        _logger.debug("issued request: {}".format(self.mCmds[-1]))

    @pyqtSlot()
    @pyqtSlot(int)
    @pyqtSlot(str)
    @pyqtSlot(dict)
    def processSlot(self, inputs = None):
        """
        called by signals from other GObject components
        To be overriden by all sub classes
        """
        if self.mViewer is None and inputs is not None and 'viewer' in inputs.keys():
            try:
                self.request.disconnect()
                # disconnect request signal first
            except:
                _logger.debug("disconnect request signal first")

            self.mViewer = inputs['viewer']
            self.mViewer.setResponseSlot(self.resultSlot)
            _logger.debug("initialised: Setup GuiViewer.responseSignal() to connect to {}\n".format(self.resultSlot))
            self.fail.emit("initialised: Setup GuiViewer.responseSignal() to connect to {}\n".format(self.resultSlot))
            self.request.connect(self.mViewer.request)
            _logger.debug("initialised: Setup {}.request signal to GuiViewer.request()\n".format(self.objectName(), self.sender().objectName()))
            self.fail.emit("initialised: Setup {}.request signal to GuiViewer.request()\n".format(self.objectName(), self.sender().objectName()))
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
            if len(self.mCmds) == 0:
                self.finish.emit()

    def parseResult(self, results):
        """
        To be overridden
        """
        pass

    def procResult(self):
        return True

    def _findChildWidget(self, widgetName):
        return self.window().findChild(QtGui.QWidget, widgetName)

    def _hasSameCommand(self, results):
        # match exactly 1 key, value from self.mCmd
        # alternatively, return self.mCmd.items() <= results.items()
        #if dict(results, **self.mCmd) == results:
        #    return True
        #return False

        # match exact key, value from self.mCmd
        for i, cmd in enumerate(self.mCmds):
            #print('{} orig cmd#{}: {}'.format(self, i, cmd))
            if dict(results, **cmd) == results:
                #print("{} cmd#{} matched: {}".format(self, i, results))
                if 'status' in results:
                    if results['status'] == 'success' or results['status'] == 'failure':
                        _logger.debug("remove returned request (success or failure): {}".format(self.mCmds[-1]))
                        self.mCmds.remove(cmd)
                return True
        return False

    @pyqtSlot()
    def _reqDone(self):
        self.validateResult()

    def validateResult(self):
        """
        To be overridden
        """
        pass


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
        self.request.emit(self.mCmds[-1])

    def parseResult(self, results):
        """
        Handle returned detect device results from PyQt Msger
        """
        if 'found_match' in results:
            form, cpu, baseboard = results['found_match'].split(',')
            self._findChildWidget('lblDetectedCpu').setText(cpu)
            self._findChildWidget('lblDetectedForm').setText(form)
            self.success.emit('Found: {} {} {}\n'.format(cpu, form, baseboard))
        else:
            if results['status'] != 'processing':
                form = cpu = baseboard = '' # same reference
                self._findChildWidget('lblDetectedCpu').setText('No CPU')
                self._findChildWidget('lblDetectedForm').setText('No Form Factor')
                self.fail.emit('Target Device SOM info not found.\n')



@QProcessSlot.registerProcessSlot('crawlWeb')
class crawlWebSlot(QProcessSlot):
    """
    Potentially the Crawling Mechanism is done in a long process thread.
    If the long process is needed, it could possibly be done using QThread in Qt.
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(object)
    #success = pyqtSignal(int, int, object) # QtGui.PyQt_PyObject)
    fail = pyqtSignal(str)

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
        self.mViewer = None
        self.mResults = []
        self.mErrors = ''

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
                            _logger.debug('internet item path: {}'.format(pobj.path))
                            self.__crawlUrl({'cmd': results['cmd'], 'target':'http://rescue.technexion.net', 'location':pobj.path.replace('/rescue/', '/')})
                    elif item[1].endswith('xz'):
                        # match against the target device, and send request to obtain uncompressed size
                        _logger.debug('internet xzfile path: {} {} {}'.format(item[1], item[2], item[2].split('/rescue/',1)))
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
            lstRescues = self._findChildWidget('listRescueFiles')
            if lstRescues is not None:
                lstRescues.clear()
                return _insertToContainer(self.mResults, lstRescues, self.success)
        return False

    def __matchDevice(self, filename):
        # step 2: find menu items that matches as cpu, form, but not baseboard
        cpu = self._findChildWidget('lblDetectedCpu').text().lower()
        form = self._findChildWidget('lblDetectedForm').text().lower()
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

    def validateResult(self):
        """
        Check for available rescue image in the listRescueFiles
        """
        if self._findChildWidget('listRescueFiles').count() == 0:
            ret = QtGui.QMessageBox.warning(self, 'TechNexion Rescue System', 'No suitable xz file found, please set a new location...\nClick Retry to rescan!!!', QtGui.QMessageBox.Ok | QtGui.QMessageBox.Retry, QtGui.QMessageBox.Ok)
            if ret == QtGui.QMessageBox.Retry:
                # retry scanning the storage
                self.process({'target': self.findChild(QtGui.QWidget, 'lineRescueServer'.text())})



@QProcessSlot.registerProcessSlot('scanStorage')
class scanStorageSlot(QProcessSlot):
    """
    Handle scanStorage callback slot
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(object)
    #success = pyqtSignal(int, int, object) # QtGui.PyQt_PyObject)
    fail = pyqtSignal(str)

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
        self.mResults = []
        self.mErrors = ''
        self.mViewer = None

    def process(self, inputs = None):
        # step 4: request for list of targets storage device
        self._setCommand({'cmd': 'info', 'target': 'emmc', 'location': 'disk'})
        #self._setCommand({'cmd': 'info', 'target': 'hd', 'location': 'disk'})
        self.request.emit(self.mCmds[-1])

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
                self.fail.emit('Did not find any suitable target storage\n')
        else:
            self.fail.emit('Not found any target storage\n')

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
            lstStorage = self._findChildWidget('listTargetStorage')
            if lstStorage is not None:
                lstStorage.clear()
                return _insertToContainer(self.mResults, lstStorage, self.success)
        return False

    def validateResult(self):
        """
        Check for available storage disk in the listTargetStorage
        """
        if self._findChildWidget('listTargetStorage').count() == 0:
            ret = QtGui.QMessageBox.warning(self, 'TechNexion Rescue System', 'No suitable storage found, please insert sdcard or emmc...\nClick Retry to rescan!!!', QtGui.QMessageBox.Ok | QtGui.QMessageBox.Retry, QtGui.QMessageBox.Ok)
            if ret == QtGui.QMessageBox.Retry:
                # retry scanning the storage
                self.process()



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
        self.mCmd = {'cmd': 'download'}
        self.mViewer = None
        self.mTimer = QtCore.QTimer()
        self.mTimer.timeout.connect(self._queryResult)
        self.mFileUrl = ''
        self.mTgtStorage = ''
        self.mFlashFlag = False
        self.mAvSpeed = 0
        self.mLastWritten = 0
        self.mRemaining = 0

    def _queryResult(self):
        if self.mViewer:
            self.mResults.update(self.mViewer.queryResult())
            if 'total_uncompressed' in self.mResults and 'bytes_written' in self.mResults:
                smoothing = 0.005
                lastSpeed = int(self.mResults['bytes_written']) - self.mLastWritten
                # averageSpeed = SMOOTHING_FACTOR * lastSpeed + (1-SMOOTHING_FACTOR) * averageSpeed;
                self.mAvSpeed = smoothing * lastSpeed + (1 - smoothing) * self.mAvSpeed
                self.mRemaining = float((int(self.mResults['total_uncompressed']) - int(self.mResults['bytes_written'])) / self.mAvSpeed)
                self.mLastWritten = int(self.mResults['bytes_written'])
                _logger.debug('total: {} written:{} av:{} remain: {}'.format(int(self.mResults['total_uncompressed']), int(self.mResults['bytes_written']), self.mAvSpeed, self.mRemaining))
                self._findChildWidget('lblRemaining').setText('Remaining Time: {:02}:{:02}'.format(int(self.mRemaining / 60), int(self.mRemaining % 60)))
                pcent = int(float(self.mResults['bytes_written']) / float(self.mResults['total_uncompressed']) * 100)
                self.success.emit(pcent)

    def process(self, inputs):
        # python3 view.py {download -u http://rescue.technexion.net/rescue/pico-imx6/dwarf-070/ubuntu-16.04.xz -t ./ubuntu.img}
        # dlparam = {'cmd': 'download', 'dl_url': menus[int(srcNum)][2], 'tgt_filename': targets[int(tgtNum)][2]['device_node']}
        # grab the dl_url and tgt_filename from the tableRescueFile and tableTargetStorage currentItemChanged() signals
        if not self.mFlashFlag:
            _logger.debug('signal sender: {}, inputs: {}'.format(self.sender().objectName(), inputs))
            if self.sender().objectName() == 'listRescueFiles':
                # uncheck all checked items
                if self.sender().DragDropMode() != QtGui.QAbstractItemView.NoDragDrop:
                    for selected in self.sender().findItems('*', QtCore.Qt.MatchWrap | QtCore.Qt.MatchWildcard):
                        if selected.checkState() == QtCore.Qt.Checked or selected.checkState() == QtCore.Qt.PartiallyChecked:
                            selected.setCheckState(QtCore.Qt.Unchecked)
                if self.sender().currentItem().isSelected():
                    if self.sender().DragDropMode() != QtGui.QAbstractItemView.NoDragDrop:
                        # check the double clicked selected item
                        self.sender().currentItem().setCheckState(QtCore.Qt.Checked)
                    # get the rescue image file's url
                    self.mFileUrl = self.sender().currentItem().data(QtCore.Qt.UserRole)
                    _logger.debug('download from {}'.format(self.mFileUrl))
                    self.success.emit(0)

            if self.sender().objectName() == 'listTargetStorage':
                if self.sender().DragDropMode() != QtGui.QAbstractItemView.NoDragDrop:
                    # uncheck all checked item
                    for selected in self.sender().findItems('*', QtCore.Qt.MatchWrap | QtCore.Qt.MatchWildcard):
                        if selected.checkState() == QtCore.Qt.Checked or selected.checkState() == QtCore.Qt.PartiallyChecked:
                            selected.setCheckState(QtCore.Qt.Unchecked)
                if self.sender().currentItem().isSelected():
                    # check the double clicked selected item
                    if self.sender().DragDropMode() != QtGui.QAbstractItemView.NoDragDrop:
                        self.sender().currentItem().setCheckState(QtCore.Qt.Checked)
                    # get the target storage's path
                    self.mTgtStorage = self.sender().currentItem().data(QtCore.Qt.UserRole)
                    _logger.debug('flash to {}'.format(self.mTgtStorage))
                    self.success.emit(0)

            # step 6: make up the command to download and flash and execute it
            # Need to grab or keep the chooses from file list selection and target list selection
            if self.sender().objectName() == 'pushButtonCmd':
                if self.mFileUrl and self.mTgtStorage:
                    self._setCommand({'cmd': 'download', 'dl_url': self.mFileUrl, 'tgt_filename': self.mTgtStorage})
                    self.request.emit(self.mCmds[-1])
                    self._findChildWidget('tabRescue').hide()
                    self._findChildWidget('tabInstall').show()
                    QtGui.QMessageBox.information(self, 'TechNexion Rescue System', 'Download {} and Flash to {}'.format(self.mFileUrl, self.mTgtStorage))
                else:
                    # prompt for error message
                    QtGui.QMessageBox.information(self, 'TechNexion Rescue System', 'Input Error:\nPlease Choose an image file to download and a storage device to flash')

            # prompt error message to select a download file and target storage
            if self.sender().objectName() == 'diaWidget' and self.mViewer:
                # had to have diaWidget initialised() signal send signal to downloadImageSlot (self) to obtain self.mViewer
                # send message to textOutput on tabResult
                _logger.debug("downloadImageSlot obtained viewer from diaWidget's initialised() signal\n")
        else:
            # prompt for error message
            QtGui.QMessageBox.information(self, 'TechNexion Rescue System', 'Hold Your Hourses!!!\nPlease wait until flashing is done...')

    def parseResult(self, results):
        # step 7: parse the result in a loop until result['status'] != 'processing'
        # Start a timer to query results every 1 second
        if results['status'] == 'processing':
            self.mTimer.start(1000) # 1000 ms
            self.mFlashFlag = True
        else:
            self.mTimer.stop()
            self.mFlashFlag = False

    def validateResult(self):
        """
        Check for flash complete
        """
        ret = QtGui.QMessageBox.warning(self, 'TechNexion Rescue System', 'Installation Complete...\nSet boot jumper to boot from sdcard/emmc,\nAnd click RESET to reboot sytem!', QtGui.QMessageBox.Ok | QtGui.QMessageBox.Reset, QtGui.QMessageBox.Ok)
        if ret == QtGui.QMessageBox.Reset:
            # reset/reboot the system
            os.system("reboot")
