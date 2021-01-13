# Copyright (c) 2018 TechNexion,Inc. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, 
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. The names of the authors may not be used to endorse or promote products 
#    derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY EXPRESSED OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL
# TECHNEXION, INC. OR ANY CONTRIBUTORS TO THIS SOFTWARE BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

# guidraw:
# Qt draw library to initialize and draw qt gui components defined
# in the configuration xml files
#
# Author: Po Cheng <po.cheng@technexion.com>

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from view import CliViewer
from guiprocslot import QProcessSlot, QWaitingIndicator, QMessageDialog
from PyQt5 import QtGui, QtCore, QtSvg, QtWidgets
from PyQt5.QtWidgets import QDialog

# import our resources.py with all the pretty images/icons
import ui_res

import logging
# get the handler to the current module, and setup logging options
_logger = logging.getLogger(__name__)

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    def _fromUtf8(s):
        return s

try:
    _encoding = QtWidgets.QApplication.UnicodeUTF8
    def _translate(context, text, disambig):
        return QtWidgets.QApplication.translate(context, text, disambig, _encoding)
except AttributeError:
    def _translate(context, text, disambig):
        return QtWidgets.QApplication.translate(context, text, disambig)

def _convertList(prop):
    # turn properties dict into a list for looping
    plist = []
    if isinstance(prop, list):
        plist.extend(prop)
    elif isinstance(prop, dict):
        plist.append(prop)
    return plist

def _getAlignment(strAlign):
    align = QtCore.Qt.AlignLeft
    if 'AlignLeft' in strAlign or 'AlignLeading' in strAlign:
        align = QtCore.Qt.AlignLeft
    elif 'AlignRight' in strAlign or 'AlignTrailing' in strAlign:
        align = QtCore.Qt.AlignRight
    elif 'AlignHCenter' in strAlign:
        align = QtCore.Qt.AlignHCenter
    elif 'AlignJustify' in strAlign:
        align = QtCore.Qt.AlignJustify
    if 'AlignTop' in strAlign:
        align |= QtCore.Qt.AlignTop
    elif 'AlignBottom' in strAlign:
        align |= QtCore.Qt.AlignBottom
    elif 'AlignVCenter' in strAlign:
        align |= QtCore.Qt.AlignVCenter
    if 'AlignCenter' in strAlign:
        align = QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter
    if 'AlignAbsolute' in strAlign:
        align = QtCore.Qt.AlignAbsolute
    if 'AlignHorizontal_Mask' in strAlign:
        align = QtCore.Qt.AlignLeft | QtCore.Qt.AlignRight | QtCore.Qt.AlignHCenter | QtCore.Qt.AlignJustify | QtCore.Qt.AlignAbsolute
    if 'AlignVertical_Mask' in strAlign:
        align = QtCore.Qt.AlignTop | QtCore.Qt.AlignBottom | QtCore.Qt.AlignVCenter
    return align


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

                _logger.debug('class:{} parent:{} hasattr {}'.format(confdict['class'], parent, hasattr(QtWidgets, confdict['class'])))
                if confdict['class'] == 'QProcessSlot':
                    # Include additional custom slots/signals per widgets from QtDesigner
                    # create the QProcessSlot's sub class object
                    _logger.debug('GenUI: create: ({}){} parent: {}'.format(confdict['class'], confdict['name'], parent.objectName() if parent is not None else 'None'))
                    cls.clsGuiDraws.update({confdict['name']: QProcessSlot.GenSlot(confdict, parent)})

                elif confdict['class'] == 'QWaitingIndicator':
                    # create the QWaitingIndicator's sub class object
                    _logger.debug('GenUI: create: ({}){} parent: {}'.format(confdict['class'], confdict['name'], parent.objectName() if parent is not None else 'None'))
                    cls.clsGuiDraws.update({confdict['name']: QWaitingIndicator(parent)})

                elif confdict['class'] == 'QMessageDialog':
                    # create the QMessageDialog's sub class object
                    _logger.debug('GenUI: create: ({}){} parent: {}'.format(confdict['class'], confdict['name'], parent.objectName() if parent is not None else 'None'))
                    cls.clsGuiDraws.update({confdict['name']: QMessageDialog(parent)})

                elif hasattr(QtWidgets, confdict['class']) or hasattr(QtSvg, confdict['class']) or confdict['class'] == 'Line':
                    # DIRTY HACK for drawing h/v line in QtDesigner with condition checking confdict['class'] == 'Line'

                    if parent is None:
                        # dynamically add additional class variable, 'initialised' to the root gui class using build-in type()
                        subcls = type(confdict['class'], (getattr(QtWidgets, confdict['class']),), dict(initialised = QtCore.pyqtSignal([dict])))
                    elif hasattr(QtSvg, confdict['class']):
                        subcls = getattr(QtSvg, confdict['class'])
                    else:
                        # get the sub class type from QtGui
                        if confdict['class'] == 'Line':
                            # DIRTY HACK!!! for drawing h/v line in QtDesigner
                            # we use QFrame to draw line
                            subcls = getattr(QtWidgets, 'QFrame')
                        else:
                            subcls = getattr(QtWidgets, confdict['class'])

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
                    if isinstance(parent, QtWidgets.QLayout):
                        _logger.debug('parent layout adding child layout/widget with config dict: {}'.format(confdict))
                        # create GUI subclass object references
                        _logger.debug('GenUI: create subclass({}) obj ref: {}'.format(confdict['class'], confdict['name']))
                        # Important!!! if parent is a layout, create child widgets without a parent,
                        # then add the child widgets to the layout, these widgets will be re-parent-ed
                        cls.clsGuiDraws.update({confdict['name']: subcls()})

                        if isinstance(cls.clsGuiDraws[confdict['name']], QtWidgets.QLayout):
                            # Add the newly created child layout to the parent layout
                            _logger.debug('GenUI: parent: {} adds {} layout'.format(parent.objectName(), confdict['name']))
                            if isinstance(parent, QtWidgets.QGridLayout):
                                # For parent as grid layouts, addLayout() requires additional
                                # row, column, rowspan, and colspan (and alignment)
                                # e.g. parent.addLayout(r, c, rs, cs, l)
                                rs = int(confdict['rowspan']) if 'rowspan' in confdict else 1
                                cs = int(confdict['colspan']) if 'colspan' in confdict else 1
                                r = int(confdict['row']) if 'row' in confdict else 0
                                c = int(confdict['column']) if 'column' in confdict else 0
                                if 'alignment' in confdict:
                                    parent.addLayout(cls.clsGuiDraws[confdict['name']], r, c, rs, cs, _getAlignment(confdict['alignment']))
                                else:
                                    parent.addLayout(cls.clsGuiDraws[confdict['name']], r, c, rs, cs)
                            elif isinstance(parent, QtWidgets.QBoxLayout):
                                parent.addLayout(cls.clsGuiDraws[confdict['name']])

                        elif isinstance(cls.clsGuiDraws[confdict['name']], QtWidgets.QWidget):
                            # Add the newly created child widget to the parent layout
                            _logger.debug('GenUI: parent: {} adds {} widget'.format(parent.objectName(), confdict['name']))
                            if isinstance(parent, QtWidgets.QGridLayout):
                                # For parent as grid layouts, addWidget() requires additional
                                # row, column, rowspan, and colspan (and alignment)
                                # e.g. parent.addWidget(r, c, rs, cs, l)
                                rs = int(confdict['rowspan']) if 'rowspan' in confdict else 1
                                cs = int(confdict['colspan']) if 'colspan' in confdict else 1
                                r = int(confdict['row']) if 'row' in confdict else 0
                                c = int(confdict['column']) if 'column' in confdict else 0
                                if 'alignment' in confdict:
                                    parent.addWidget(cls.clsGuiDraws[confdict['name']], r, c, rs, cs, _getAlignment(confdict['alignment']))
                                else:
                                    parent.addWidget(cls.clsGuiDraws[confdict['name']], r, c, rs, cs)
                            elif isinstance(parent, QtWidgets.QBoxLayout):
                                parent.addWidget(cls.clsGuiDraws[confdict['name']])

                    else:
                        _logger.debug('GenUI: create subclass({}) obj ref: {} parent: {}'.format(confdict['class'], confdict['name'], parent.objectName() if parent is not None else 'None'))
                        # cls.clsGuiDraws.update({confdict['name']: subcls(confdict, parent)})
                        cls.clsGuiDraws.update({confdict['name']: subcls(parent)})

                        if isinstance(parent, QtWidgets.QTabWidget) and isinstance(cls.clsGuiDraws[confdict['name']], QtWidgets.QWidget):
                            # add tab page widget to the parent TabWidget
                            _logger.debug('GenUI: parent: {} adds tab widget: {}'.format(parent.objectName(), confdict['name']))
                            parent.addTab(cls.clsGuiDraws[confdict['name']], _fromUtf8(confdict['name']))
                        elif isinstance(parent, QtWidgets.QWidget) and isinstance(cls.clsGuiDraws[confdict['name']], QtWidgets.QLayout):
                            # add layout to the parent widget
                            _logger.debug('GenUI: parent: {} sets layout: {}'.format(parent.objectName(), confdict['name']))
                            parent.setLayout(cls.clsGuiDraws[confdict['name']])
                        elif isinstance(parent, QtWidgets.QWidget) and isinstance(cls.clsGuiDraws[confdict['name']], QtWidgets.QWidget):
                            # add widget to the parent widget
                            _logger.debug('GenUI: parent: {} adds child widget: {}'.format(confdict['name'], parent.objectName()))
                            parent.addWidget(cls.clsGuiDraws[confdict['name']])

                else:
                    raise TypeError('Warning: Cannot find GUI class: {} in QtGui'.format(confdict['class']))

                _logger.info('call setupConfig for GUI class:{}'.format(confdict['class']))
                # setup the widget's configuration
                cls.setupConfig(cls.clsGuiDraws[confdict['name']], confdict, parent)

                # setup additional items within the Gui Element, e.g. QListWidget, QTreeWidget
                if 'item' in confdict.keys() and isinstance(cls.clsGuiDraws[confdict['name']], QtWidgets.QAbstractItemView):
                    cls.setupItem(cls.clsGuiDraws[confdict['name']], confdict['item'], parent)

                # attribute are for the parent class to set
                if 'attribute' in confdict.keys() and parent is not None and isinstance(parent, QtGui.QTabWidget):
                    cls.setupAttribute(cls.clsGuiDraws[confdict['name']], _convertList(confdict['attribute']), parent)

                # setup additional headers for the TableWidget qobj
                if isinstance(cls.clsGuiDraws[confdict['name']], QtWidgets.QTableWidget):
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
            for prop in proplist:
                # 2. actual configurations for all UI types in this giant method

                # QWidget
                if prop['name'] == 'sizePolicy':
                    # size policy
                    sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
                    sizePolicy.setHorizontalStretch(0)
                    sizePolicy.setVerticalStretch(0)
                    #sizePolicy.setHeightForWidth(parent.sizePolicy().hasHeightForWidth())
                    qobj.setSizePolicy(sizePolicy)
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
                elif prop['name'] == 'autoFillBackground':
                    qobj.setAutoFillBackground(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'toolTip':
                    qobj.setToolTip(_fromUtf8(prop['string']) if 'string' in prop.keys() else 'No Tip')

                # QLabel
                elif prop['name'] == 'text':
                    # Text in QLabel
                    qobj.setText(_fromUtf8(prop['string']) if 'string' in prop.keys() else 'No Text')
                elif prop['name'] == 'pixmap':
                    # Icon in QLabel
                    if isinstance(prop['pixmap'], dict) and '_text' in prop['pixmap'] and prop['pixmap']['_text'].startswith(':/res'):
                        qobj.setPixmap(QtGui.QPixmap(QtGui.QImage(prop['pixmap']['_text'])))
                    else:
                        qobj.setPixmap(QtGui.QPixmap(prop['pixmap']))
                elif prop['name'] == 'scaledContents':
                    qobj.setScaledContents(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'alignment':
                    # Alignment
                    qobj.setAlignment(_getAlignment(prop['set']))
                elif prop['name'] == 'wordWrap':
                    qobj.setWordWrap(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'readOnly':
                    qobj.setReadOnly(True if prop['bool'] == 'true' else False)

                elif prop['name'] == 'icon':
                    if 'normalon' in prop['iconset'].keys():
                        qobj.setIcon(QtGui.QIcon(prop['iconset']['normalon']))
                    if 'normaloff' in prop['iconset'].keys():
                        qobj.setIcon(QtGui.QIcon(prop['iconset']['normaloff']))
                    if 'selectedon' in prop['iconset'].keys():
                        qobj.setIcon(QtGui.QIcon(prop['iconset']['selectedon']))
                    if 'selectedoff' in prop['iconset'].keys():
                        qobj.setIcon(QtGui.QIcon(prop['iconset']['selectedoff']))
                    if 'disabledon' in prop['iconset'].keys():
                        qobj.setIcon(QtGui.QIcon(prop['iconset']['disabledon']))
                    if 'disabledoff' in prop['iconset'].keys():
                        qobj.setIcon(QtGui.QIcon(prop['iconset']['disabledoff']))
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
                    if 'Horizontal' in prop['enum']:
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
                        qobj.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
                    elif 'ContiguousSelection' in prop['enum']:
                        qobj.setSelectionMode(QtWidgets.QAbstractItemView.ContiguousSelection)
                    elif 'ExtendedSelection' in prop['enum']:
                        qobj.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
                    elif 'MultiSelection' in prop['enum']:
                        qobj.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
                    elif 'NoSelection' in prop['enum']:
                        qobj.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
                elif prop['name'] == 'selectionBehavior':
                    if 'SelectRows' in prop['enum']:
                        qobj.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
                    elif 'SelectItems' in prop['enum']:
                        qobj.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
                    elif 'SelectColumns' in prop['enum']:
                        qobj.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectColumns)

                # QFrame
                elif prop['name'] == 'frameShadow':
                    if 'Plain' in prop['enum']:
                        qobj.setFrameShadow(QtWidgets.QFrame.Plain)
                    elif 'Raised' in prop['enum']:
                        qobj.setFrameShadow(QtWidgets.QFrame.Raised)
                    elif 'Sunken' in prop['enum']:
                        qobj.setFrameShadow(QtWidgets.QFrame.Sunken)
                elif prop['name'] == 'lineWidth':
                    qobj.setLineWidth(int(prop['number']))
                elif prop['name'] == 'frameShape':
                    if 'NoFrame' in prop['enum']:
                        qobj.setFrameShape(QtWidgets.QFrame.NoFrame)
                    elif 'Box' in prop['enum']:
                        qobj.setFrameShape(QtWidgets.QFrame.Box)
                    elif 'Panel' in prop['enum']:
                        qobj.setFrameShape(QtWidgets.QFrame.Panel)
                    elif 'StyledPanel' in prop['enum']:
                        qobj.setFrameShape(QtWidgets.QFrame.StyledPanel)
                    elif 'HLine' in prop['enum']:
                        qobj.setFrameShape(QtWidgets.QFrame.HLine)
                    elif 'VLine' in prop['enum']:
                        qobj.setFrameShape(QtWidgets.QFrame.VLine)
                    elif 'WinPanel' in prop['enum']:
                        qobj.setFrameShape(QtWidgets.QFrame.WinPanel)

                # QListView
                elif prop['name'] == 'uniformItemSizes':
                    qobj.setUniformItemSizes(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'viewMode':
                    if 'IconMode' in prop['enum']:
                        qobj.setViewMode(QtWidgets.QListView.IconMode)
                    elif 'ListMode' in prop['enum']:
                        qobj.setViewMode(QtWidgets.QListView.ListMode)
                elif prop['name'] == 'layoutMode':
                    if 'SinglePass' in prop['enum']:
                        qobj.setLayoutMode(QtWidgets.QListView.SinglePass)
                    elif 'Batched' in prop['enum']:
                        qobj.setLayoutMode(QtWidgets.QListView.Batched)
                elif prop['name'] == 'movement':
                    if 'Static' in prop['enum']:
                        qobj.setMovement(QtWidgets.QListView.Static)
                    elif 'Free' in prop['enum']:
                        qobj.setMovement(QtWidgets.QListView.Free)
                    elif 'Snap' in prop['enum']:
                        qobj.setMovement(QtWidgets.QListView.Snap)
                elif prop['name'] == 'resizeMode':
                    if 'Fixed' in prop['enum']:
                        qobj.setResizeMode(QtWidgets.QListView.Fixed)
                    elif 'Adjust' in prop['enum']:
                        qobj.setResizeMode(QtWidgets.QListView.Adjust)
                elif prop['name'] == 'flow':
                    if 'LeftToRight' in prop['enum']:
                        qobj.setFlow(QtWidgets.QListView.LeftToRight)
                    elif 'TopToBottom':
                        qobj.setFlow(QtWidgets.QListView.TopToBottom)
                elif prop['name'] == 'iconSize':
                    qobj.setIconSize(QtCore.QSize(int(prop['size']['width']), int(prop['size']['height'])))
                elif prop['name'] == 'flat':
                    qobj.setFlat(True if prop['bool'] == 'true' else False)

                elif prop['name'] == 'gridSize':
                    qobj.setGridSize(QtCore.QSize(int(prop['size']['width']), int(prop['size']['height'])))
                elif prop['name'] == 'editTriggers':
                    trig = QtWidgets.QAbstractItemView.NoEditTriggers
                    if 'CurrentChanged' in prop['set']:
                        trig |= QtWidgets.QAbstractItemView.CurrentChanged
                    if 'DoubleClicked' in prop['set']:
                        trig |= QtWidgets.QAbstractItemView.DoubleClicked
                    if 'SelectedClicked' in prop['set']:
                        trig |= QtWidgets.QAbstractItemView.SelectedClicked
                    if 'EditKeyPressed' in prop['set']:
                        trig |= QtWidgets.QAbstractItemView.EditKeyPressed
                    if 'AnyKeyPressed' in prop['set']:
                        trig |= QtWidgets.QAbstractItemView.AnyKeyPressed
                    if 'AllEditTriggers' in prop['set']:
                        trig |= QtWidgets.QAbstractItemView.AllEditTriggers
                    qobj.setEditTriggers(trig)
                elif prop['name'] == 'dragDropMode':
                    if 'NoDragDrop' in prop['enum']:
                        qobj.setDragDropMode(QtWidgets.QAbstractItemView.NoDragDrop)
                    elif 'DragOnly' in prop['enum']:
                        qobj.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
                    elif 'DropOnly' in prop['enum']:
                        qobj.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
                    elif 'DragDrop' in prop['enum']:
                        qobj.setDragDropMode(QtWidgets.QAbstractItemView.DragDrop)
                    elif 'InternalMove' in prop['enum']:
                        qobj.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
                elif prop['name'] == 'showDropIndicator':
                    qobj.setDropIndicatorShown(True if prop['bool'] == 'true' else False)
                elif prop['name'] == 'sortingEnabled':
                    qobj.setSortingEnabled(True if prop['bool'] == 'true' else False)

                # QWaitingIndicator
                elif prop['name'] == 'nodeCount':
                    qobj.setNodeCount(int(prop['number']))
                elif prop['name'] == 'nodeSize':
                    qobj.setNodeSize(int(prop['number']))
                elif prop['name'] == 'radius':
                    qobj.setRadius(int(prop['number']))

                # QMessageDialog
                elif prop['name'] == 'modal':
                    qobj.setModal(True if prop['bool'] == 'true' else False)

        # 1. setup name (common to all Qt widgets)
        if 'name' in confdict:
            qobj.setObjectName(_fromUtf8(confdict['name']))
        else:
            qobj.setObjectName(_fromUtf8(confdict['class']).lstrip('Q') if 'class' in confdict else '')
        if 'property' in confdict:
            # 2. setup GUI element's properties
            _setupProperty(_convertList(confdict['property']), parent)

    @classmethod
    def setupItem(cls, qobj, confdict, parent=None):
        """
        Sets up items for Container, i.e. QListWidget, QTreeWidget, etc
        """
        for prop in confdict:
            lstItem = QtWidgets.QListWidgetItem()
            for item in prop['property']:
                if item['name'] == 'text':
                    if qobj.objectName() == 'lstWgtSelection':
                        lstItem.setData(QtCore.Qt.UserRole, item['string'])
                    else:
                        lstItem.setText(item['string'])
                elif item['name'] == 'icon':
                    if 'normalon' in item['iconset'].keys():
                        lstItem.setIcon(QtGui.QIcon(item['iconset']['normalon']))
                    elif 'normaloff' in item['iconset'].keys():
                        lstItem.setIcon(QtGui.QIcon(item['iconset']['normaloff']))
                    elif 'selectedon' in item['iconset'].keys():
                        lstItem.setIcon(QtGui.QIcon(item['iconset']['selectedon']))
                    elif 'selectedoff' in item['iconset'].keys():
                        lstItem.setIcon(QtGui.QIcon(item['iconset']['selectedoff']))
                    elif 'disabledon' in item['iconset'].keys():
                        lstItem.setIcon(QtGui.QIcon(item['iconset']['disabledon']))
                    elif 'disabledoff' in item['iconset'].keys():
                        lstItem.setIcon(QtGui.QIcon(item['iconset']['disabledoff']))
                elif item['name'] == 'checkState':
                    if item['enum'] == 'Unchecked':
                        lstItem.setCheckState(QtCore.Qt.Unchecked)
                    elif item['enum'] == 'PartiallyChecked':
                        lstItem.setCheckState(QtCore.Qt.PartiallyChecked)
                    elif item['enum'] == 'Checked':
                        lstItem.setCheckState(QtCore.Qt.Checked)
                elif item['name'] == 'toolTip':
                    lstItem.setToolTip(item['string']['_text'])
                elif item['name'] == 'statusTip':
                    lstItem.setToolTip(item['string']['_text'])
                elif item['name'] == 'whatsThis':
                    lstItem.setToolTip(item['string']['_text'])
                elif item['name'] == 'textAlignment':
                    lstItem.setTextAlignment(_getAlignment(item['set']))
                elif item['name'] == 'flags':
                    if 'ItemIsSelectable' in item['set']:
                        lstItem.setFlags(lstItem.flags() | QtCore.Qt.ItemIsSelectable)
                    elif 'ItemIsEditable' in item['set']:
                        lstItem.setFlags(lstItem.flags() | QtCore.Qt.ItemIsEditable)
                    elif 'ItemIsDragEnabled' in item['set']:
                        lstItem.setFlags(lstItem.flags() | QtCore.Qt.ItemIsDragEnabled)
                    elif 'ItemIsDropEnabled' in item['set']:
                        lstItem.setFlags(lstItem.flags() | QtCore.Qt.ItemIsDropEnabled)
                    elif 'ItemIsUserCheckable' in item['set']:
                        lstItem.setFlags(lstItem.flags() | QtCore.Qt.ItemIsUserCheckable)
                    elif 'ItemIsEnabled' in item['set']:
                        lstItem.setFlags(lstItem.flags() | QtCore.Qt.ItemIsEnabled)
                    elif 'ItemIsTristate' in item['set']:
                        lstItem.setFlags(lstItem.flags() | QtCore.Qt.ItemIsTristate)

            qobj.addItem(lstItem)

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
