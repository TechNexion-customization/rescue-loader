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

# guiprocslot:
# Qt Inherited Objects to Handle Input and Output Processing as well as
# udating resuls on GUI display
#
# Author: Po Cheng <po.cheng@technexion.com>

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io
import re
import os
import sys
import signal
import subprocess
import math
import socket
import datetime
from urllib.parse import urlparse
from PyQt4 import QtGui, QtCore, QtSvg, QtNetwork
from PyQt4.QtCore import QObject, pyqtSignal, pyqtSlot
from threading import Event
# import our resources.py with all the pretty images/icons
import ui_res
import logging
from defconfig import IsATargetBoard
# get the handler to the current module, and setup logging options
_logger = logging.getLogger(__name__)

def _printSignatures(qobj):
    metaobject = qobj.metaObject()
    for i in range(metaobject.methodCount()):
        _logger.warn('{} metaobject signature: {}'.format(qobj, metaobject.method(i).signature()))

def _prettySize(n,pow=0,b=1024,u='B',pre=['']+[p+'i'for p in'KMGTPEZY']):
    r,f=min(int(math.log(max(n*b**pow,1),b)),len(pre)-1),'{:,.%if} %s%s'
    return (f%(abs(r%(-r-1)),pre[r],u)).format(n*b**pow/b**float(r))

def _insertToContainer(lstResult, qContainer, qSignal):
    def match_data(data):
        for item in qContainer.findItems('.*', QtCore.Qt.MatchRegExp):
            _logger.debug('match row: {} => item: {} qContainer: {}'.format(data, item.data(QtCore.Qt.UserRole), qContainer.objectName()))
            if item.data(QtCore.Qt.UserRole)['name'] == data['name']:
                return item
        return None
    """
    Insert results to a container, e.g. QListWidget, QTableWidget, QTreeWidget
    parse the results in a list of dictionaries, and add them to container
    """
    if isinstance(qContainer, QtGui.QListWidget) and lstResult is not None:
        # insert into a listWidget

        # setup widget items
        for r, row in enumerate(lstResult, start=0):
            # [{name, path, size}, ...] for storage
            # [{cpu, form, board, display, os, ver, size(uncompsize), url}, ...] for rescue images
            item = match_data(row)
            if item is None:
                item = QtGui.QListWidgetItem()
                # draw radioItem icon, depending on e.g. OS names, or storage device types
                item.setData(QtCore.Qt.UserRole, row)
                if 'device_type' in row and row['device_type'] == 'disk':
                    item.setToolTip(_prettySize(int(row['size'])))
                    if 'id_bus' in row and row['id_bus'] != 'None':
                        resName = ":/res/images/storage_{}.svg".format(row['id_bus'].lower())
                    else:
                        # determine eMMC vs SDCard
                        if 'MMC_TYPE=MMC' in row['uevent']:
                            resName = ":/res/images/storage_emmc.svg"
                        else:
                            resName = ":/res/images/storage_sd.svg"
                    item.setToolTip(row['name'].lower())
                elif 'os' in row:
                    if row['os'] in ['rescue', 'android', 'ubuntu', 'boot2qt', 'yocto', 'androidthings']:
                        resName = ":/res/images/os_{}.svg".format(row['os'].lower())
                    elif row['os'] in ['linux', 'debian', 'redhat']:
                        resName = ":/res/images/os_tux.svg"
                    else:
                        resName = ":/res/images/NoImage.svg"
                    if 'ver' in row:
                        item.setText(row['ver'].lower())
                    else:
                        item.setToolTip(row['os'].lower())
                elif 'board' in row:
                    # could update the VERSION within the svg resource byte array, and draw the svg
                    if row['board'] is not None:
                        for bd in ['dwarf', 'nymph', 'hobbit', 'pi', 'fairy', 'gnome', 'tep', 'tek', 'toucan', 'wizard']:
                            if bd in row['board']:
                                resName = ":/res/images/board_{}.svg".format(bd)
                                break
                    elif 'tc' in row['board']:
                        resName = ":/res/images/board_toucan.svg"
                    else:
                        resName = ":/res/images/board.svg"
                    #font = QtGui.QFont('Lato', 32, QtGui.QFont.Bold)
                    #item.setFont(font)
                    #item.setTextColor(QtGui.QColor(184, 24, 34))
                    #item.setText(row['board'].lower())
                    item.setToolTip(row['board'].lower())
                elif 'display' in row:
                    if 'ifce_type' in row:
                        resName = ":/res/images/display_{}.svg".format(row['ifce_type'])
                    else:
                        resName = ":/res/images/display.svg"
                    item.setToolTip(', '.join(row['display']))
                else:
                    resName = ":/res/images/os_tux.svg"
                    item.setToolTip(row['name'])

                item.setIcon(QtGui.QIcon(resName))
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                qContainer.addItem(item)

            # set disable / enable
            if 'disable' in row:
                item.setFlags((item.flags() & ~QtCore.Qt.ItemIsEnabled) if (row['disable'] == True) else (item.flags() | QtCore.Qt.ItemIsEnabled))
                item.setData(QtCore.Qt.UserRole, row)

            if qSignal: qSignal.emit(item)

    elif isinstance(qContainer, QtGui.QTableWidget) and lstResult is not None:
        # insert into a tableWidget

        # setup table headers
        qContainer.setColumnCount(len(lstResult[0]))
        hdrs = [k for k in lstResult[0].keys()]
        qContainer.setHorizontalHeaderLabels(hdrs)
        qContainer.setRowCount(len(lstResult))

        # setup widget items
        for r, row in enumerate(lstResult, start=0):
            # [{name, path, size}, ...] for storage
            # [{cpu, form, board, display, os, ver, size(uncompsize), url}, ...] for rescue images
            for i, k in enumerate(row.keys(), start=0):
                item = QtGui.QTableWidgetItem(row[k])
                if 'path' in row.keys():
                    item.setData(QtCore.Qt.UserRole, row['path'])
                elif 'url' in row.keys():
                    item.setData(QtCore.Qt.UserRole, row['url'])
                if qSignal: qSignal.emit(r, i, item)

    elif isinstance(qContainer, QtGui.QTreeWidget) and lstResult is not None:
        # TODO: Add support for insert into a treeWidget
        return False

    elif isinstance(qContainer, QtGui.QGroupBox) and lstResult is not None:
        # insert into a groupbox widget
        # setup widget items
        layoutBox = qContainer.layout() if qContainer.layout() else QtGui.QVBoxLayout()
        if not layoutBox.isEmpty():
            for i in range(layoutBox.count()):
                layoutBox.removeItem(layoutBox.itemAt(i))
        for r, row in enumerate(lstResult, start=0):
            radioItem = QtGui.QRadioButton()
            # draw radioItem with text, e.g. board, os, display, storage names.
            radioItem.setText(row['name'])
            # draw radioItem icon, depending on e.g. OS names, or storage device types
            if 'device_type' in row:
                if row['device_type'].lower() == 'disk':
                    radioItem.setIcon(QtGui.QIcon(QtGui.QPixmap(":/res/images/micro_sd_recover.png")))
                elif row['device_type'].lower() == 'partition':
                    radioItem.setIcon(QtGui.QIcon(QtGui.QPixmap(":/res/images/micro_sd_recover.png")))
            if 'os' in row:
                if row['os'] in ["rescue", "android", "ubuntu", "boot2qt", "yocto", "androidthings"]:
                    resName = ":/res/images/os_{}.svg".format(row['os'].lower())
                else:
                    resName = ":/res/images/os_tux.svg"
                radioItem.setIcon(QtGui.QIcon(QtGui.QPixmap(resName)))
            layoutBox.addWidget(radioItem)
        if qContainer.layout() is None: qContainer.setLayout(layoutBox)

    elif isinstance(qContainer, QtGui.QGraphicsView) and lstResult is not None:
        # insert into a graphics view (widget)
        # setup graphics view items
        scene = qContainer.scene() if qContainer.scene() else QtGui.QGraphicsScene()
        gitems = scene.items()
        if len(gitems):
            for gitem in gitems:
                if isinstance(gitem, QtGui.QGraphicsWidget):
                    wgt = gitem
                    layout = gitem.layout()
        else:
            wgt = QtGui.QGraphicsWidget()
            layout = QtGui.QGraphicsLinearLayout(QtCore.Qt.Vertical)
        for r, row in enumerate(lstResult, start=0):
            # draw radioItem icon, depending on e.g. OS names, or storage device types
            name = row['name']
            if 'device_type' in row:
                if row['device_type'].lower() == 'disk':
                    resName = ":/res/images/micro_sd_recover.png"
                elif row['device_type'].lower() == 'partition':
                    resName = ":/res/images/micro_sd_recover.png"
            elif 'os' in row:
                resName = ":/res/images/os_{}.svg".format(row['os'].lower())
            else:
                resName = ":/res/images/NewTux.svg"
            # add the returned proxywidget from scene addItem to the layout
            lbl = QtGui.QLabel(name)
            lbl.setPixmap(QtGui.QPixmap(resName))
            layout.addItem(scene.addWidget(lbl))

        if not wgt.layout(): wgt.setLayout(layout)
        if len(scene.items()) == 0: scene.addItem(wgt)
        if qContainer.scene() is None: qContainer.setScene(scene)
        qContainer.show()

    return True



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
    Base Class for our customized Process Slots
    sub classess use the decorator to add its entry into cls.subclasses
    The GenSlot is called to generate subclass instance
    """

    subclasses = {}

    fail = pyqtSignal(dict)
    request = pyqtSignal(dict)
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
        return cls.subclasses[confdict['name']](parent)

    def __init__(self, parent = None):
        QtGui.QWidget.__init__(self, parent)
        self.mTotalReq = 0
        self.mTotalRemove = 0
        self.mMsgs = []
        self.mCmds = []
        self.mCmdEv = Event()
        self.mCmdEv.set()
        self.mViewer = None
        self.finish.connect(self._reqDone)

    def sendError(self, err):
        if isinstance(err, dict):
            _logger.debug('{}: send error: {}'.format(self.objectName(), err))
            self.fail.emit(err)

    def sendCommand(self, cmd):
        self.mTotalReq += 1
        self.mCmdEv.wait(0)
        self.mCmdEv.clear()
        self.mCmds.append(cmd)
        self.mMsgs.append(dict(cmd))
        self.mCmdEv.set()
        _logger.warn('{}: queue cmd request: {} remaining cmds: {}'.format(self.objectName(), self.mCmds[-1], len(self.mCmds)))
        self.request.emit(cmd)

    def _setupUserInputResponse(self):
        if self.mViewer and hasattr(self.mViewer, "setResponseSlot"):
            # call the viewer's setResponseSlot API to setup the callback to self.resultSlot()
            self.mViewer.setResponseSlot(self.resultSlot)
            _logger.debug('{}: setup GuiViewer.responseSignal() to connect to {}\n'.format(self.objectName(), self.resultSlot))

    @pyqtSlot()
    @pyqtSlot(bool)
    @pyqtSlot(int)
    @pyqtSlot(str)
    @pyqtSlot(list)
    @pyqtSlot(dict)
    @pyqtSlot(object)
    @pyqtSlot(QtGui.QListWidgetItem)
    def processSlot(self, inputs = None):
        """
        called by signals from other GUIObject components
        To be overriden by all sub classes
        """
        if self.sender().objectName() == 'diaWidget' and self.mViewer is None and isinstance(inputs, dict) and 'viewer' in inputs:
            # this bit handles guiviewer's __emitInitSignal(),
            # i.e. root widget's initialised.emit() signal passing {'viewer': self} to all defined QProcessSlots
            # we are trying to keep QProcessSlot as generic as possible, i.e. remove dependency of viewer element
            # in the constructor, and only connect to viewer's request as necessary
            try:
                self.request.disconnect()
                # disconnect request signal first
            except:
                _logger.debug('{}: disconnect request signal first'.format(self.objectName()))

            self.mViewer = inputs['viewer']
            self.request.connect(self.mViewer.request)
            _logger.debug('{}: initialised: Setup {}.request signal to GuiViewer.request()'.format(self.objectName(), self.sender().objectName()))

        _logger.debug('{}: sender: {} inputs: {}'.format(self.objectName(), self.sender().objectName(), inputs))
        self.process(inputs)

    def process(self, inputs):
        """
        To be overridden
        """
        pass

    @pyqtSlot(dict)
    def resultSlot(self, results = None):
        """
        called by viewer's response() slot via MsgDispatcher with returned results
        """
        ret = self._hasSameCommand(results)
        _logger.debug('{}: hasSameCmd: {}, parse results: {}'.format(self.objectName(), ret, results))
        self.parseResult(results)
        if ret and len(self.mCmds) == 0:
            _logger.warn('{}: Requests completed, emit finish signal to validate results'.format(self.objectName()))
            self.finish.emit()

    def parseResult(self, results):
        """
        To be overridden
        """
        pass

    def _findSubset(self, lstCriteria, lstFiles):
        def find_match(strSearch, listOfFileDict):
            for fdict in listOfFileDict:
                if strSearch in fdict.values():
                    yield fdict
        if len(lstCriteria):
            v = lstCriteria.pop()
            return list(self._findSubset(lstCriteria, list(find_match(v, lstFiles)))) if len(lstCriteria) else list(find_match(v, lstFiles))

    def _findChildWidget(self, widgetName):
        return self.window().findChild(QtGui.QWidget, widgetName)

    def _hasSameCommand(self, results):
        ret = False
        remove = None
        # match exact key, value from self.mCmd, and find the first match
        for i, cmd in enumerate(self.mCmds, start=0):
            # dict of cmd and results is the same as results, means cmd is already in results
            if dict(results, **cmd) == results:
                # need to handle which type of messengers the results comes back from,
                # i.e. dbus, serial, or web
                # if a command has all messenger types returned, remove the command,
                # which means when all commands are removed, it will then allow
                # the process flow go to validateResult by self.finish.emit()
                if 'status' in results and (results['status'] == 'success' or results['status'] == 'failure'):
                    if 'cmd' in results and 'msger_id' in results and 'total_mgrs' in results:
                        self.mMsgs[i].update({results['msger_id']: 'msger_id'})
                        count = len([k for k, v in self.mMsgs[i].items() if v == 'msger_id'])
                        _logger.debug('{}: cmd: {}, msger id: {}, total remove: {}, total req: {}, total_mgrs: {}, count: {}, update mgr list: {}'.format(self.objectName(), results['cmd'], results['msger_id'], self.mTotalRemove, self.mTotalReq, results['total_mgrs'], count, self.mMsgs))
                        # if total messengers for the particular command is the same as total_mgrs then remove it
                        if count == int(results['total_mgrs']):
                            remove = i
                ret = True
                break
        if remove is not None:
            _logger.warn('{}: remove returned request: {} status: {} remaining cmds: {}'.format(self.objectName(), self.mMsgs[remove], results['status'], len(self.mCmds) - 1))
            self.mTotalRemove += 1
            self.mCmdEv.wait(0)
            self.mCmdEv.clear()
            del self.mCmds[remove]
            del self.mMsgs[remove]
            self.mCmdEv.set()

        return ret

    @pyqtSlot()
    def _reqDone(self):
        # validate results after request commands are finished
        self.validateResult()

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        """
        To be overridden
        """
        pass



@QProcessSlot.registerProcessSlot('scanStorage')
class scanStorageSlot(QProcessSlot):
    """
    Handle scanStorage callback slot
    """
    success = pyqtSignal(object) # QtGui.PyQt_PyObject

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mControllers = []
        self.mResults = []
        self.mMacAddr = '00:00:00:00:00:00'

    def process(self, inputs = None):
        """
        step 1: request for list of targets storage device
        """
        if self.sender().objectName() == 'diaWidget':
            QtCore.QTimer.singleShot(1000, self.__checkDbus)

    def __checkDbus(self):
        """
        Check if DBus is working on the running system
        """
        if self.mViewer and hasattr(self.mViewer, 'checkDbusConn'):
            if self.mViewer.checkDbusConn():
                if IsATargetBoard():
                    self.__detectStorage()
                else:
                    if hasattr(self.mViewer, 'checkSerialConn') and self.mViewer.checkSerialConn():
                        self.__detectStorage()
                    else:
                        # no serial connection, need to wait until target board ready
                        self.sendError({'NoSerial': True, 'ask': 'continue'})
                        if hasattr(self.mViewer, 'setupMsger'):
                            self.mViewer.setupMsger('serial')
                            QtCore.QTimer.singleShot(1000, self.__checkDbus)
            else:
                self.sendError({'NoDbus': True})
                # retry to check DBus
                QtCore.QTimer.singleShot(1000, self.__checkDbus)

    def __detectStorage(self):
        self.sendCommand({'cmd': 'info', 'target': 'emmc', 'location': 'controller'})

    def __parseTargetList(self, res, attrs):
        # Parse the target storage device info
        def findAttrs(keys, dc):
            # find in dictionary and dictionary within a dictionary
            for k, v in dc.items():
                if k in keys:
                    yield (k, v)
                elif isinstance(v, dict):
                    for ret in findAttrs(keys, v):
                        yield ret

        data = {}
        for k, v in res.items():
            if isinstance(v, dict) and 'device_type' in v and v['device_type'] != 'partition':
                data.update({k: {att[0]:att[1] for att in findAttrs(attrs, v)}})
        #return [(i, k, v) for i, (k, v) in enumerate(data.items())]
        return [(k, v) for k, v in data.items()]

    def parseResult(self, results):
        # query emmc disk if query emmc controller successful
        if 'cmd' in results and results['cmd'] == 'info' and \
            'target' in results and 'location' in results and \
            'msger_type' in results and 'status' in results and results['status'] == 'success':

            # query emmc disk if query controller successful
            if results['target'] == 'emmc' and results['location'] == 'controller':
                self.mControllers = self.__parseTargetList(results, ['device_node', 'device_type', 'serial', 'uevent'])
                _logger.debug('controllers: {}, so query for emmc disk info'.format(self.mControllers))
                self.sendCommand({'cmd': 'info', 'target': 'emmc', 'location': 'disk'})

            # query hd disk if query emmc disk successful
            if results['target'] == 'emmc' and results['location'] == 'disk':
                _logger.debug('query emmc disk info after got controllers, so query hd disk info')
                self.sendCommand({'cmd': 'info', 'target': 'hd', 'location': 'disk'})

            # parse a list of target devices for user to choose
            if (results['target'] == 'emmc' or results['target'] == 'hd') and \
                results['location'] == 'disk':
                listTarget = self.__parseTargetList(results, ['device_node', 'device_type', 'serial', 'id_bus', 'size', 'uevent'])
                if len(listTarget):
                    for tgt in listTarget:
                        # 'name', 'node path', 'disk size'
                        _logger.warn('{}: found target storage device: {}'.format(self.objectName(), tgt))
                        self.mResults.append({'name': tgt[0], \
                                              'path': tgt[1]['device_node'], \
                                              'device_type': tgt[1]['device_type'], \
                                              'serial': tgt[1]['serial'], \
                                              'conntype': results['msger_type'], \
                                              'size':int(tgt[1]['size']) * 512, \
                                              'id_bus': tgt[1]['id_bus'] if 'id_bus' in tgt[1] else None, \
                                              'uevent': tgt[1]['uevent'] if 'uevent' in tgt[1] else None})
                        # find matching serial from the controllers
                        for ctrl in self.mControllers:
                            if tgt[1]['serial'] == ctrl[1]['serial']:
                                self.mResults[-1].update({'uevent': ctrl[1]['uevent']})

    def validateResult(self):
        _logger.debug('{} validate results: {}'.format(self.objectName(), self.mResults))
        # flow comes here (gets called) after self.finish.emit()
        # Check for available storage disk in the self.mResult list
        if isinstance(self.mResults, list) and len(self.mResults):
            self._determineTargetDisk()
            _logger.debug('{} determined target disks: {}'.format(self.objectName(), self.mResults))
            self.success.emit(self.mResults)
        else:
            # no suitable storage found (on host pc or target board)
            _logger.error('{}: Cannot find available storage!!! Retry'.format(self.objectName()))
            self.sendError({'NoStorage': True, 'ask': 'retry'})
            QtCore.QTimer.singleShot(1000, self.__detectStorage)

    def _determineTargetDisk(self):
        # for Host PC
        # loop self.mResults and detemine emulated target emmc storage over the USB/Serial
        # find the emmc from target board first (serial conn type)
        if IsATargetBoard():
            mmcs = [disk for disk in self.mResults if 'mmc:block' in disk['uevent'] and "MMC_TYPE=SD" in disk['uevent']]
        else:
            mmcs = [disk for disk in self.mResults if 'mmc:block' in disk['uevent'] and disk['conntype'] == 'serial']
        if len(mmcs) > 0:
            # remove emmcs of targetboard from results list
            for mmc in mmcs:
                self.mResults.remove(mmc)
            # compare the scanned disks from serial and from dbus, match the
            # serial number and emmc size, and use found emmc in host pc rescue loader.
            for disk in self.mResults:
                if self.mMacAddr in disk['serial'] and disk['size'] > 0:
                    # find matching mac address, than match the emmc size
                    for mmc in mmcs:
                        if disk['size'] == mmc['size']:
                            # Copy the emmc properties over to the disk's id_bus conntype uevent
                            disk['id_bus'] = mmc['id_bus'][:] if mmc['id_bus'] != None else None
                            disk['conntype'] = mmc['conntype'][:]
                            disk['uevent'] = mmc['uevent'][:]
                            disk['mmc_path'] = mmc['name'][:] if 'dev/' in mmc['name'] else '/dev/{}'.format(mmc['name'])



@QProcessSlot.registerProcessSlot('mountStorage')
class mountStorageSlot(QProcessSlot):
    """
    Handle mounting the found emmc storage
    """
    success = pyqtSignal(object) # QtGui.PyQt_PyObject

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mDiskPath = None
        self.mResults = {}
        self.mMountFlag = False

    def process(self, inputs = None):
        """
        Mount the found emmc on target device, e.g. modprobe g_acm_ms file=/dev/mmcblk2
        and if successul, re-scan storage to allow resending storage info
        over the usb/serial connection
        """
        if self.sender().objectName() == 'scanStorage':
            # suitable storage device
            if isinstance(inputs, list):
                for disk in inputs:
                    if isinstance(disk, dict) and 'path' in disk and \
                       'device_type' in disk and disk['device_type'] == 'disk':
                        if IsATargetBoard():
                            # WILL cause sendError twice when multiple storages
                            # e.g. mmcblk2, mmcblk0 are found
                            if self.mDiskPath is None:
                                self.mDiskPath = disk['path'][:]
                                _logger.warn('{}: found disk: {}'.format(self.objectName(), self.mDiskPath))
                                #self.sendError({'SerialMode': True, 'ask': 'serial'})
                                # bypass asking for serial communication mode here on Target Device
                                # leave asking for after download failures
                                self.mResults.update({'cmd': 'connect', 'status': 'continue', 'src_filename': '{}'.format(self.mDiskPath)})
                                self.finish.emit()
                            else:
                                # already found last time, so finish emit and continue
                                _logger.warn('{}: already found disk: {}'.format(self.objectName(), self.mDiskPath))
                                self.finish.emit()
                        else:
                            if 'conntype' in disk and disk['conntype'] == 'serial':
                                self.mDiskPath = disk['path'][:]
                                self.__mountStorage()

        if self.sender().objectName() == 'processError':
            if 'accept' in inputs and inputs['accept']:
                # accept to run Serial Mode
                self.__mountStorage()
            elif 'reject' in inputs and inputs['reject']:
                # reject to continue
                self.mResults.update({'cmd': 'connect', 'status': 'continue', 'src_filename': '{}'.format(self.mDiskPath)})
                self.finish.emit()

        if self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'downloadImage':
            if IsATargetBoard():
                self.__mountStorage()

    def __mountStorage(self):
        if IsATargetBoard():
            # for target board: modprobe g_acm_ms file=/dev/mmcblkX
            if self.mDiskPath is not None:
                self.sendCommand({'cmd': 'connect', 'type': 'serialstorage', 'src_filename': '{}'.format(self.mDiskPath)})
            else:
                # No Disk Path found, something wrong, need to re-scan storage
                # for both host pc and target board
                self.sendError({'NoSerial': True, 'ask': 'retry'})
        else:
            # for host pc: check if has valid serialMessenger
            if self.mViewer and hasattr(self.mViewer, 'checkSerialConn'):
                if self.mViewer.checkSerialConn():
                    self.mResults.update({'cmd': 'connect', 'status': 'continue', 'src_filename': '{}'.format(self.mDiskPath)})
                else:
                    self.mResults.update({'cmd': 'connect', 'status': 'failure', 'src_filename': '{}'.format(self.mDiskPath)})
                self.finish.emit()

    def parseResult(self, results):
        # We are in SerialMode to communicate with host pc, so ask for reboot and wait for click
        self.mResults.update(results)

    def validateResult(self):
        _logger.warn('{}: validate results: {}'.format(self.objectName(), self.mResults))
        # flow comes here (gets called) after self.finish.emit()
        # Check for available storage disk in the self.mResult list
        if 'cmd' in self.mResults and self.mResults['cmd'] == 'connect' and 'status' in self.mResults:
            if self.mResults['status'] == 'success':
                # for target board
                if IsATargetBoard():
                    self.sendError({'SerialConnect': True, 'ask': 'reboot'})
            elif self.mResults['status'] == 'failure':
                # for host pc and target board modprobe failed
                self.sendError({'NoSerial': True, 'ask': 'retry'})
            elif self.mResults['status'] == 'continue':
                # for host pc or target board choose to continue
                self.success.emit({'path': '{}'.format(self.mDiskPath)})



@QProcessSlot.registerProcessSlot('detectDevice')
class detectDeviceSlot(QProcessSlot):
    """
    Handles detecting target device CPU and Form Factor information
    """
    success = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mCpu = None
        self.mForm = None
        self.mBaseboard = None
        self.mSentFlag = False

    def process(self, inputs = None):
        """
        Handle detect device callback slot
        """
        if self.sender().objectName() == 'mountStorage':
            self.sendCommand({'cmd': 'info', 'target': 'som'})

    def parseResult(self, results):
        """
        Handle returned SOM info from DBus or Serial messenger
        """
        if 'cmd' in results and results['cmd'] == 'info' and \
           'target' in results and results['target'] == 'som' and \
           'status' in results and results['status'] == 'success':
            if 'file_content' in results:
                panel=None
                # fall through to parse file content from /proc/device-tree/model returned from installerd
                # they are returned as array of strings, but dbus message turns them in to string withs ""
                lstWords = results['file_content'].lstrip("['").rstrip("']").rsplit('\\',1)[0].split()
                for i, w in enumerate(lstWords):
                    # get CPU and FORM
                    if '-' in w and 'imx' in w.lower():
                        self.mCpu = w.split('-')[1]
                        self.mForm = w.split('-')[0]
                    # get PANEL
                    if '-' in w and 'inch' in w.lower():
                        panel = '{}'.format(w)
                    elif 'inch' == w.lower():
                        panel = '{}-{}'.format(lstWords[i-1], w.lower())
                    # get BOARD
                    if 'board' == w.lower():
                        # for most edm system boards without baseboards
                        if any(bd in self.mForm for bd in ['TEP', 'TEK']):
                            self.mBaseboard = self.mForm
                            if (panel is not None and 'inch' in panel and 'inch' not in self.mBaseboard):
                                self.mBaseboard += '_{}'.format(panel)
                    elif 'baseboard' == w.lower():
                        self.mBaseboard = lstWords[i-1]
            if 'found_match' in results:
                # This is just to double confirm
                frm, cpu, brd = results['found_match'].split(',')
                if '-' in cpu and self.mCpu != cpu.split('-',1)[0]:
                    self.mCpu = cpu.split('-',1)[0]
                if self.mForm != frm:
                    self.mForm = frm

    def validateResult(self):
        _logger.warn('{} validate result: cpu:{} form:{} baseboard:{}'.format(self.objectName(), self.mCpu, self.mForm, self.mBaseboard))
        # flow comes here (gets called) after self.finish.emit()
        # Check for available cpu, form factor, and baseboard
        # if found matching CPU form and Board, emit success to scanStorage/scanPartition
        # before any remote host can be connected, this reduces time waiting for
        # rescue server checks
        if self.mCpu and self.mForm and self.mBaseboard:
            # update GUI
            _logger.info('{}: cpu:{} form:{} board:{}'.format(self.objectName(), self.mCpu, self.mForm, self.mBaseboard))
            self._findChildWidget('lblCpu').setText(self.mCpu)
            self._findChildWidget('lblForm').setText(self.mForm)
            self._findChildWidget('lblBaseboard').setText(self.mBaseboard)
            # tell the processError to display with no icons specified, i.e. hide
            if not self.mSentFlag:
                _logger.warn('{}: Success and emit: {} {} {}'.format(self.objectName(), self.mCpu, self.mForm, self.mBaseboard))
                self.success.emit({'cpu': self.mCpu, 'form': self.mForm, 'board':self.mBaseboard})
                self.mSentFlag = True
                # successfully detect a technexion rescue server
        else:
            self.sendError({'NoCpuForm': True, 'ask': 'reboot' if IsATargetBoard() else 'quit'})



@QProcessSlot.registerProcessSlot('scanPartition')
class scanPartitionSlot(QProcessSlot):
    """
    Search the mounted points from exiting partitions in the system
    """
    success = pyqtSignal(object) # QtGui.PyQt_PyObject

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = {}

    def process(self, inputs):
        """
        issue commands to find partitions with mount points
        """
        if self.sender().objectName() == 'detectDevice':
            self.__detectMountedPartition()

    def __detectMountedPartition(self):
        self.sendCommand({'cmd': 'info', 'target': 'emmc', 'location': 'partition'})

    def parseResult(self, results):
        if 'cmd' in results and results['cmd'] == 'info' and \
           'target' in results and results['target'] == 'emmc' and \
           'location' in results and results['location'] == 'partition' and \
           'status' in results and (results['status'] == 'success' or results['status'] == 'failure'):
            self.sendCommand({'cmd': 'info', 'target': 'hd', 'location': 'partition'})

        # parse the returned partitions from dbus only and send them off
        if isinstance(results, dict) and 'msger_type' in results and results['msger_type'] == 'dbus' and \
           'status' in results and results['status'] == "success":
            for k, v in results.items():
                _logger.debug('{} result item: {}, {}'.format(self.objectName(), k, v))
                if isinstance(v, dict) and 'device_type' in v and v['device_type'] == 'partition' and \
                   'mount_point' in v and v['mount_point'].startswith('/'):
                    self.mResults.update({k: v})

    def validateResult(self):
        _logger.warn('{} validate results: {}'.format(self.objectName(), self.mResults))
        # flow comes here (gets called) after self.finish.emit()
        # Signal available partitions in the self.mResults dictionary
        if isinstance(self.mResults, dict):
            if len(self.mResults):
                # emit results to the next QProcessSlot, i.e. crawlLocalfs
                self.sendError({'Show': False})
            else:
                self.sendError({'NoPartition': True})
            self.success.emit(self.mResults)



@QProcessSlot.registerProcessSlot('crawlLocalfs')
class crawlLocalfsSlot(QProcessSlot):
    """
    Potentially the Crawling Mechanism is done in a long process thread.
    If the long process is needed, it could possibly be done using QThread in Qt.
    """
    success = pyqtSignal(object) # QtGui.PyQt_PyObject

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = []
        self.mSentFlag = False

    def process(self, inputs):
        """
        Handle crawling xz files from inputs, i.e. lists of mount points
        """
        if self.sender().objectName() == 'scanPartition':
            mount_points = []
            # parse the returned partition results to find mount points
            if isinstance(inputs, dict):
                for k, v in inputs.items():
                    if isinstance(v, dict) and 'mount_point' in v and v['mount_point'].startswith('/'):
                        if 'media' in v['mount_point']:
                            mount_points.append(v['mount_point'])

            # make up the request params
            params = {'target': socket.gethostname()}
            if isinstance(mount_points, list):
                if len(mount_points) == 0:
                    mount_points.append('~/')

                self._findChildWidget('waitingIndicator').show()
                for mntpt in mount_points:
                    params.update({'location': mntpt if mntpt.endswith('/') else (mntpt + '/')})
                    _logger.debug('{}: start crawl localfs: {}'.format(self.objectName(), params))
                    self.sendCommand({'cmd': 'info', 'target': params['target'], 'location': params['location']})

    def parseResult(self, results):
        # Parse the return local xz files
        if 'status' in results and results['status'] == 'success' and \
           'file_list' in results and isinstance(results['file_list'], dict):
            # We know that file_list is a dictionary because we send it from the server
            for fname, finfo in results['file_list'].items():
                # extract form, cpu, board, display, and filename of the XZ filename
                try:
                    form, cpu, board, display, os, other = self.__parseProp(fname)
                    size = finfo['total_uncompressed'] if ('total_uncompressed' in finfo and int(finfo['total_uncompressed']) > 0) else finfo['total_size']
                    url = finfo['file_path'] if 'file_path' in finfo else None
                    if form is not None and cpu is not None and board is not None and display is not None and os is not None and other is not None and size is not None and url is not None:
                        # add {cpu, form, board, display, os, ver, size(uncompsize), url}
                        if '-' in other:
                            ver, extra = other.split('-', 1)
                        else:
                            ver, extra = other, ''
                        self.mResults.append({'cpu': cpu, 'form': form, 'board': board, 'display': display, 'os': os, 'ver': ver, 'size': size, 'url': url, 'extra': extra})
                except:
                    _logger.warn('{}: skip parsing {} to extract form, cpu, board, display, os, and version info.'.format(self.objectName(), fname))

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        _logger.debug('{}: validate results: {}'.format(self.objectName(), self.mResults))
        if isinstance(self.mResults, list) and len(self.mResults):
            self._findChildWidget('waitingIndicator').hide()
            # if found suitable xz files, send them on to the next process slot
            self.sendError({'Show': False})
        else:
            # Did not find any suitable xz file on mounted partitions
            self.sendError({'NoLocal': True})
        if not self.mSentFlag:
            self.success.emit(self.mResults)
            self.mSentFlag = True

    def __parseProp(self, filename):
        # '{}-{}_{}-{}_{}-{}{}.xz' => 'form' 'cpu', 'board', 'display', 'os', {'ver', 'extra'}
        p = re.compile('(\w+)[_|-](\w+)[_|-](\w+)[_|-](\w+)[_|-](\w+)[_|-](.+)\.xz', re.IGNORECASE)
        m = p.match(filename)
        if m:
            return m.groups()



@QProcessSlot.registerProcessSlot('scanNetwork')
class scanNetworkSlot(QProcessSlot):
    """
    Handles detecting target device network information
    """
    success = pyqtSignal(list)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mNicErr = {'NoNIC': True, 'NoIface': True, 'NoCable': True, 'Show': True}
        self.mNetErr = {'NoIP': True, 'NoDNS': True, 'NoServer': True, 'Show': True}
        self.mTgtNICs = {}
        self.mHosts = []
        self.mLocalIPs = {}
        self.mNICNames = {}
        self.mNIC = None
        self.mSockets = {}
        self.mRepeatTimerId = None
        self.mRepeatFlag = False
        self.mConnectCounter = 0

    # overridden
    def sendError(self, err):
        if self.mRepeatTimerId is None:
            _logger.debug('{}: sendError: {}'.format(self.objectName(), err))
            self.fail.emit(err)
        else:
            # when mSentFlag already set, that means scanStorage and scanPartition has started
            # crawlWeb is not waiting for connectable server and then potentially any further eror
            if 'Repeat' in err and err['Repeat']:
                self.mRepeatFlag = False
                self.mNetErr.pop('Repeat', None)
                allerrors = {}
                allerrors.update(self.mNicErr)
                allerrors.update(self.mNetErr)
                allerrors.pop('Show', None)
                _logger.warn('{}: sendError: re-direct errors to crawlWeb/downloadImage: {}'.format(self.objectName(), allerrors))
                self.success.emit(list(allerrors.items()))

    def process(self, inputs = None):
        """
        Handle detect device callback slot
        """
        if self.sender().objectName() == 'diaWidget':
            # get the default remote http server host_name from defconfig in self.mViewer
            remotehosts = self.mViewer.getRemoteHostUrls() if self.mViewer is not None and hasattr(self.mViewer, "getRemoteHostUrls") else None
            for host in remotehosts:
                _logger.info('{}: remote hosts: {}'.format(self.objectName(), remotehosts))
                url = urlparse('{}://{}'.format(host['protocol'], host['name']))
                if all([url.scheme, url.netloc]):
                    self.mHosts.append({'protocol': '{}'.format(host['protocol'].lower()), 'name': '{}'.format(host['name']), 'port': int(host['port']), 'path': '{}'.format(host['path'])})
            if self.mHosts == {}:
                self.mHosts.append({'protocol': 'http', 'name': 'rescue.technexion.net', 'port': 80, 'path': 'images'})

        if self.sender().objectName() == 'detectDevice':
            # check 1: the NIC interface
            QtCore.QTimer.singleShot(1000, self.__checkNIC)

        if self.sender().objectName() == 'downloadImage':
            if isinstance(inputs, dict) and 'flashed' in inputs and inputs['flashed']:
                if self.mRepeatTimerId:
                    self.killTimer(self.mRepeatTimerId)

    def parseResult(self, results):
        """
        Handle returned SOM info from DBus or Serial messenger
        Handle returned nic ifname and ip
        Handle returned detect network device results from DBus server
        """
        if 'subcmd' in results and results['subcmd'] == 'nic' and 'status' in results and \
           'config_id' in results and 'msger_type' in results:

            # results from dbus messenger
            if results['msger_type'] == 'dbus':
                # results from NIC check, i.e. ifconf
                if results['config_id'] == 'ifconf' and results['status'] == 'success':
                    if 'iflist' in results and isinstance(results['iflist'], dict):
                        # 3a-1. getting the ifconfig names,
                        if len(results['iflist']) > 0:
                            # get the list of nics and figure out NIC ifs for both target device and host pc
                            self.mLocalIPs.update(results['iflist'])
                            self.mNICNames.clear()

                            for k, v in self.mLocalIPs.items():
                                if k.startswith('eth') or k.startswith('enp'):
                                    _logger.warn('{}: found ifname:{} ip:{}'.format(self.objectName(), k, v))
                                    self.mNICNames.update({k: {'ip':v}})
                                elif v not in ['unknown', '127.0.0.1', '0.0.0.0']:
                                    _logger.warn('{}: found ifname:{} ip:{}'.format(self.objectName(), k, v))
                                    self.mNICNames.update({k: {'ip':v}})

                            self.mNicErr.update({'NoNIC': False})
                        else:
                            self.mNicErr.update({'NoNIC': True})

                        self.sendError(self.mNicErr)
                        # redo the check NIC, to continue to 3b.
                        if self.mNICNames != {}:
                            # i.e. send another query to query for ifflags with proper NIC I/F name
                            QtCore.QTimer.singleShot(1000, self.__checkNIC)

                # results from I/F check and Cable check, i.e. ifflags
                elif results['config_id'] == 'ifflags' and results['status'] == 'success':
                    _logger.warn('{}: found ifname: {} state: {}'.format(self.objectName(), results['target'], results['state']))
                    if 'state' in results and 'flags' in results:
                        # 3b-1. Check whether NIC hardware available (do we have mac?)
                        #if 'LOWER_UP' in results['state']:
                        # 3b-2. Check NIC connection is up (flag says IFF_UP?)
                        for name, value in self.mNICNames.items():
                            if name == results['target']:
                                value.update({'state': results['state']})
                        _logger.warn('{}: NICNames: {}'.format(self.objectName(), self.mNICNames))
                        if all('state' in v for v in self.mNICNames.values()):
                            QtCore.QTimer.singleShot(1000, self.__checkDNS)

                # results from DNS Network Checks, i.e. from __checkDNS
                elif results['config_id'] == 'dns' and (results['status'] == 'success' or results['status'] == 'failure'):
                    for host in self.mHosts:
                        if isinstance(host, dict):
                            if host['name'] == results['target']:
                                host.update({'host_ip': results['host_ip']})
                    if all('host_ip' in host for host in self.mHosts):
                        QtCore.QTimer.singleShot(1000, self.__checkIP)

                # results from IP Network Checks, i.e. from __checkIP
                elif results['config_id'] == 'ip' and results['status'] == 'success':
                    # for both target device and host pc from installerd
                    # check 5: find matching IP for the NIC Name
                    for k, v in self.mLocalIPs.items():
                        if k == results['target']:
                            if v == results['ip']:
                                _logger.warn('Found matched ip:{} on NIC iface: {}'.format(v, k))
                                self.mNetErr.update({'NoIP': False, 'NoDNS': False})
                                self.sendError(self.mNetErr)
                                # check 6. connectivity to TN server
                                QtCore.QTimer.singleShot(1000, self.__checkTNServer)
                            elif v == 'unknown':
                                _logger.warn('Found ip:{} on NIC iface: {}'.format(v, k))
                                self.mNetErr.update({'NoIP': False, 'NoDNS': False})
                                self.sendError(self.mNetErr)
                                # check 6. connectivity to TN server
                                QtCore.QTimer.singleShot(1000, self.__checkTNServer)
                            else:
                                self.mNetErr.update({'NoIP': False, 'NoDNS': True})
                                self.sendError(self.mNetErr)
                                # no ip from socket connecting to DNS server, retry from check DNS step
                                QtCore.QTimer.singleShot(1000, self.__checkDNS)

            # results from serial messenger (for Host PC version)
            elif results['msger_type'] == 'serial':
                # results from NIC Checks via serial messenger from host pc's at step 3a-1
                if results['config_id'] == 'ifconf' and results['status'] == 'success':
                    if 'iflist' in results and isinstance(results['iflist'], dict):
                        # 3a-1. getting the ifconfig names,
                        self.mTgtNICs.clear()
                        if len(results['iflist']) > 0:
                            # get the list of nics and figure out NIC ifs for both target device and host pc
                            for k, v in results['iflist'].items():
                                if k == 'eth0':
                                    _logger.warn('{}: found ifname:{} ip:{}'.format(self.objectName(), k, v))
                                    self.mTgtNICs.update({k: {'ip':v}})
                                elif v not in ['unknown', '127.0.0.1', '0.0.0.0']:
                                    _logger.warn('{}: found ifname:{} ip:{}'.format(self.objectName(), k, v))
                                    self.mTgtNICs.update({k: {'ip':v}})

                        if self.mTgtNICs != {}:
                            for name in self.mTgtNICs.keys():
                                # query for mac with tgt board proper NIC I/F name
                                self.sendCommand({'cmd': 'config', 'subcmd': 'nic', \
                                                    'config_id': 'ifhwaddr', \
                                                    'config_action': 'get', \
                                                    'target': name})
                # results from ifhwaddr via serial messenger to get target board MacAddr
                if results['config_id'] == 'ifhwaddr' and results['status'] == 'success':
                    # serial messenger returns target nic mac
                    if 'hwaddr' in results and len(results['hwaddr']) > 0:
                        self.mTgtNICs.update({results['target']: {'macaddr': results['hwaddr'][:]}})
                    _logger.warn('{}: found target board NICs: {}'.format(self.objectName(), self.mTgtNICs))

    def validateResult(self):
        _logger.warn('{} validate results: mHosts:{}'.format(self.objectName(), self.mHosts))
        # flow comes here (gets called) after self.finish.emit()
        # tell the processError to display with no icons specified, i.e. hide
        if all(('alive' in host) for host in self.mHosts):
            if any(host['alive'] for host in self.mHosts):
                # successfully detect any technexion rescue server update dialogbox
                self.mNetErr.update({'NoServer': False, 'Show': False})
            else:
                # the system cannot connect to all our rescue servers, retry from user
                self.mNetErr.update({'NoServer': True})
            # emit the hosts information gathered
            _logger.warn('{}: alive rescue servers: {}'.format(self.objectName(), self.mHosts))
            self.success.emit(self.mHosts)
            self.sendError(self.mNetErr)
            # finish all network checks, set repeat check flag for checking
            # nic/net every 2 minutes to update the alive list
            if self.mRepeatTimerId is None:
                _logger.warn('{}: start timer at 2m interval'.format(self.objectName()))
                self.mRepeatTimerId = self.startTimer(120000)
                # send/re-direct 1st set of list of errors to crawlWeb
                self.mNetErr.update({'Repeat': True})
                self.sendError(self.mNetErr)

    def timerEvent(self, event):
        # start checking network again
        _logger.warn('{}: timed up, re-check network'.format(self.objectName()))
        self.mConnectCounter = 0
        self.mRepeatFlag = True
        self.mNICNames.clear()
        for host in self.mHosts:
            host.pop('alive', None)
            host.pop('host_ip', None)
        self.__checkNIC()

    def __checkNIC(self):
        # send request to installerd.service to request for network status.
        if self.mNICNames == {}:
            # 3a. didn't get nic iface name, so query ifconfig first,
            _logger.warn('{}: check ifconfig for all local nic interfaces...'.format(self.objectName()))
            self.sendCommand({'cmd': 'config', 'subcmd': 'nic', 'config_id': 'ifconf', 'config_action': 'get', 'target': 'any'})
        else:
            _logger.warn('{}: check ifflags on found local nic interface: {}...'.format(self.objectName(), self.mNICNames))
            # 3b. check ifflags on local nic interfaces
            for name, ip in self.mNICNames.items():
                self.sendCommand({'cmd': 'config', 'subcmd': 'nic', 'config_id': 'ifflags', 'config_action': 'get', 'target': name})

    def __checkDNS(self):
        _logger.warn('{}: __checkDNS: {}'.format(self.objectName(), self.mNICNames))
        if all('state' in value for value in self.mNICNames.values()):
            for value in self.mNICNames.values():
                if 'UP' in value['state']:
                    value.update({'NoIface': False})
                    # 3b-3. Check NIC connection is running (flag says IFF_RUNNING?)
                    #self.mNicErr.update({'NoIface': False})
                    if 'RUNNING' in value['state']:
                        # 3b-4. when all is running, check to see if we can connect to our rescue server.
                        value.update({'NoCable': False})
                        #self.mNicErr.update({'NoCable': False, 'Show': False})
                    else:
                        value.update({'NoCable': True})
                        #self.mNicErr.update({'NoCable': True})
                else:
                    value.update({'NoIface': True})
                    #self.mNicErr.update({'NoIface': True})
        if all(('NoIface' in v and 'NoCable' in v) for v in self.mNICNames.values()):
            if any((v['NoIface'] is False and v['NoCable'] is False) for v in self.mNICNames.values()):
                # if any nic i/f is up and running, carry on to check host by name
                self.mNicErr.update({'NoIface': False, 'NoCable': False})
                self.sendError(self.mNetErr)
                _logger.warn('{}: check whether we can find host by name...'.format(self.objectName()))
                # check 4a. get IP from socket connected to DNS
                for host in self.mHosts:
                    self.sendCommand({'cmd': 'config', 'subcmd': 'nic', 'config_id': 'dns', 'config_action': 'get', 'target': host['name']})
            else:
                if all(v['NoIface'] is True for v in self.mNICNames.values()):
                    self.mNicErr.update({'NoIface': True})
                elif all(v['NoCable'] is True for v in self.mNICNames.values()):
                    self.mNicErr.update({'NoCable': True})
                # retry check 3. for NIC if failed
                _logger.debug('{}: ifflags has errors, re-check NICs...'.format(self.objectName()))
                self.sendError(self.mNicErr)
                QtCore.QTimer.singleShot(1000, self.__checkNIC)

    def __checkIP(self):
        _logger.warn('{}: __checkIP: {}'.format(self.objectName(), self.mHosts))
        if all('host_ip' in host for host in self.mHosts):
            if all(host['host_ip'] is 'None' for host in self.mHosts):
                self.mNetErr.update({'NoDNS': True})
                self.sendError(self.mNetErr)
                _logger.warn('{}: check whether we have IP and connectable to 8.8.8.8...'.format(self.objectName()))
                # check 4b. all host ip are 'None', means cannot resolve hostnames
                for nicname in self.mNICNames:
                    self.sendCommand({'cmd': 'config', 'subcmd': 'nic', 'config_id': 'ip', 'config_action': 'get', 'target': nicname})
            else:
                if all(v['ip'] is 'unknown' for n, v in self.mNICNames.items() if n.startswith('e')):
                    self.mNetErr.update({'NoIP': True})
                    self.sendError(self.mNetErr)
                    for n, v in self.mNICNames.items():
                        if n.startswith('e'):
                            self.sendCommand({'cmd': 'config', 'subcmd': 'nic', 'config_id': 'ip', 'config_action': 'get', 'target': n})
                else:
                    self.mNetErr.update({'NoIP': False, 'NoDNS': False})
                    self.sendError(self.mNetErr)
                    QtCore.QTimer.singleShot(1000, self.__checkTNServer)

    def __checkTNServer(self):
        # check connectivity to TechNexion server
        _logger.warn('{}: check whether we have connectivity to server... {} sockets: {}'.format(self.objectName(), self.mHosts, self.mSockets))
        for host in self.mHosts:
            if host['name'] not in self.mSockets:
                self.mSockets.update({host['name']: QtNetwork.QTcpSocket()})
                # setup callback slot for connected and error signals
                self.mSockets[host['name']].disconnected.connect(self._socketDisconnected)
                self.mSockets[host['name']].connected.connect(self._socketConnected)
                self.mSockets[host['name']].error.connect(self._socketError)
            self.mSockets[host['name']].abort()
            self.mSockets[host['name']].connectToHost(host['name'], host['port'])

    def _socketError(self):
        _logger.warn('{}: QTcpSocket Error on {}: {}'.format(self.objectName(), self.sender().peerName(), self.sender().errorString()))
        for host in self.mHosts:
            # flag false as not reachable for probed host url
            if self.sender().peerName() in host['name']:
                host.update({'alive': False})
        self.sender().abort()
        self.sender().close()
        self.mNetErr.update({'Repeat': True} if self.mRepeatFlag else {})
        self.mConnectCounter += 1
        if self.mConnectCounter == len(self.mSockets):
            self.finish.emit()

    def _socketConnected(self):
        _logger.warn('{}: QTcpSocket Connected to: {}'.format(self.objectName(), self.sender().peerName()))
        for host in self.mHosts:
            # flag true as connectable for probed host url
            if self.sender().peerName() in host['name']:
                host.update({'alive': True})
        self.sender().disconnectFromHost()

    def _socketDisconnected(self):
        _logger.warn('{}: QTcpSocket Disconnected from: {}'.format(self.objectName(), self.sender().peerName()))
        self.sender().close()
        self.mNetErr.update({'Repeat': True} if self.mRepeatFlag else {})
        self.mConnectCounter += 1
        if self.mConnectCounter == len(self.mSockets):
            self.finish.emit()



@QProcessSlot.registerProcessSlot('crawlWeb')
class crawlWebSlot(QProcessSlot):
    """
    Potentially the Crawling Mechanism is done in a long process thread.
    If the long process is needed, it could possibly be done using QThread in Qt.
    """
    success = pyqtSignal(object) # QtGui.PyQt_PyObject)
    mount = pyqtSignal()

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mDefaultPorts = {'http': 80, 'https': 443, 'ftp': 21}
        self.mInputs = {}
        self.mDetects = {}
        self.mResults = []
        self.mCpu = None
        self.mForm = None
        self.mBoard = None
        self.mHosts = []
        self.mHostName = None
        self.mRemoteDir = None
        self.mRescueChecked = False
        self.mStartCrawlFlag = False

    def __mountStorage(self):
        try:
            self.mount.disconnect()
        except:
            pass
        if hasattr(self._findChildWidget('mountStorage'), 'processSlot'):
            self.mount.connect(self._findChildWidget('mountStorage').processSlot)
            self.mount.emit()
            self.mount.disconnect()

    def __parseURL(self, host):
        # Need to check server alive and available
        if self.mHostName is None and self.mRemoteDir is None and \
           'alive' in host and host['alive'] and not 'available' in host:
            remoteurl = '{}://{}{}'.format(host['protocol'], host['name'], \
                '' if (host['protocol'] in self.mDefaultPorts.keys() and \
                       self.mDefaultPorts[host['protocol']] == host['port']) \
                   else ':{}'.format(host['port']))
            url = self.__checkUrl(remoteurl)
            if url is not None:
                self.mHostName = url.geturl()
            self.mRemoteDir = '/{}/'.format(host['path'].strip('/'))
            return True
        return False

    def __parseHosts(self, hosts=None):
        # all hosts must contain 'alive' and 'name'
        if hosts is not None and isinstance(hosts, list) and \
           all(('alive' in h and 'name' in h) for h in hosts):
            if self.mHosts == []:
                # get the first alive TechNexion server host
                for h in hosts:
                    self.mHosts.append(dict(h))
            else:
                # update locally kept hosts
                for host in self.mHosts:
                    for h in hosts:
                        if host['name'] == h['name']:
                            if host['alive'] != h['alive']:
                                host['alive'] = h['alive']
            _logger.info('{}: hosts updated to {}'.format(self.objectName(), self.mHosts))

    def __checkNetworkError(self):
        # 0. no alives, so ask for serial connect mode (quit on host PC)
        # First set of errors passed in: (indicate by NO StartCrawlFlag)
        # 1. no NIC/NET error, has alive, so start Crawling
        # 2. has NIC/NET error, has alive, so show error message
        # Second+ set of errors passed in: (indicate by StartCrawlFlag)
        # 3. no NIC/NET error, has alive, has available, so ignore
        # 4. no NIC/NET error, has alive, has available but all false, so ask serial
        # 5. no NIC/NET error, has alive, has some avilable, so NoCrawl, try next alive server
        # 6. no NIC/NET error, has alive, has no avaiable, so NoDLFile, not found any file, ask retry.
        # 7. NIC/NET error, has alive, has available, so serial connect mode
        if any(h['alive'] for h in self.mHosts):
            if not self.mStartCrawlFlag: # StartCrawlFlag not set, parse second+ set of errors
                if all(v is False for v in self.mDetects.values()):
                    # mDetects are errors passed in from scanNetwork, so start crawling if all NIC/NET valid
                    _logger.warn('{}: Alive servers, Not started crawling, No NIC/NET errors, start crawling... mHosts:{}'.format(self.objectName(), self.mHosts))
                    self.mHostName = None
                    self.mRemoteDir = None
                    for host in self.mHosts:
                        if self.__parseURL(host):
                            _logger.info('{}: first connectable hostname:{} dir:{}'.format(self.objectName(), self.mHostName, self.mRemoteDir))
                            self.__checkInputs()
                            break
                else:
                    _logger.error('{}: Alive servers, Not started crawling, But nic/net errors... mHosts:{}'.format(self.objectName(), self.mHosts))
                    self.sendError({'NoNetwork': True, 'ask': 'serial' if IsATargetBoard() else 'quit'})

            else: # StartCrawlFlag set, parse second+ set of errors
                if all(v is False for v in self.mDetects.values()):
                    if any('available' in host for host in self.mHosts):
                        if any(('available' in host and host['available']) for host in self.mHosts):
                            # ignore any further error messages from scanNetwork
                            # as we have available files on server.
                            _logger.warn('{}: Alive and available servers, Started crawl, No NIC/NET errors, so ignore... mHosts:{}'.format(self.objectName(), self.mHosts))
                            pass
                        elif all(('available' in host and not host['available']) for host in self.mHosts):
                            # Alive servers but NONE has available files
                            _logger.error('{}: Alive rescue servers but NONE has available file to download... mHosts:{}'.format(self.objectName(), self.mHosts))
                            self.sendError({'NoNetwork': True, 'ask': 'serial' if IsATargetBoard() else 'quit'})
                        else:
                            # rescue server un-available, possible due to incorrect location or port,
                            # time out comes here, and we switch to another server because we didn't find
                            # any matching files
                            _logger.error('{}: Alive rescue servers but some has un-available file to download, try another host... mHosts:{}'.format(self.objectName(), self.mHosts))
                            self.sendError({'NoCrawl': True, 'ask': 'continue'})
                            self.mStartCrawlFlag = False
                            self.mHostName = None
                            self.mRemoteDir = None
                            for host in self.mHosts:
                                if self.__parseURL(host):
                                    _logger.info('{}: next connectable hostname:{} dir:{}'.format(self.objectName(), self.mHostName, self.mRemoteDir))
                                    self.__checkInputs()
                                    break
                    else:
                        # None of the servers are available and did not find any suitable xz file
                        if self.mTotalReq > 0 and self.mTotalReq == self.mTotalRemove and self.mResults == []:
                            _logger.info('{}: crawlWeb receive all request/response, but no results... mHosts:{}'.format(self.objectName(), self.mHosts))
                            self.sendError({'NoDLFile': True, 'ask': 'retry'})
                else:
                    # NIC/NET error after found URL successfully
                    _logger.error('{}: Alive and available servers, Started crawl, But nic/net errors... mHosts:{}'.format(self.objectName(), self.mHosts))
                    self.sendError({'NoNetwork': True, 'ask': 'serial' if IsATargetBoard() else 'quit'})

        else: # none of servers are alive
            _logger.error('{}: Connect to TechNexion rescue server failed, and no-more rescue servers alive...'.format(self.objectName()))
            self.sendError({'NoNetwork': True, 'ask': 'serial' if IsATargetBoard() else 'quit'})

    def process(self, inputs):
        """
        Handle crawlWeb process slot (signalled by initialised signal)
        """
        # get the default remote http server host_name from defconfig in self.mViewer
        if self.sender().objectName() == 'scanNetwork':
            # 4 possible conditions coming from scanNetwork
            # a) any of the connectable hosts list is alive (list of dict)
            # b) none of the connectable hosts list are alive (list of dict)
            # c) any of the network detection has error (list of tuples)
            # d) none of the network detection has error (list of tuples)
            if isinstance(inputs, list):
                if all(isinstance(item, dict) for item in inputs):
                    # parse alive/connectable rescue servers
                    self.__parseHosts(inputs)
                elif all(isinstance(item, tuple) for item in inputs):
                    # scanStorage errors, only updates when network detects are
                    # different or when no network errors
                    if dict(self.mDetects, **dict(inputs)) != self.mDetects or \
                       all(v is False for v in dict(inputs).values()):
                        self.mDetects.update(dict(inputs))
                        self.__checkNetworkError()

        if self.sender().objectName() == 'processError':
            if 'accept' in inputs and 'reject' in inputs:
                if inputs['accept']:
                    if 'NoNetwork' in inputs and inputs['NoNetwork']:
                        # accept to run Serial Mode
                        _logger.info('{}: accept to serial connect mode...'.format(self.objectName()))
                        self.__mountStorage()
                elif inputs['reject']:
                    if 'NoNetwork' in inputs and inputs['NoNetwork']:
                        # reject to continue, set all server to be alive and wait
                        # for network rescan to fix the server alive status
                        _logger.info('{}: reject to retry, so to clear everything and wait for time-out...'.format(self.objectName()))
                        self.mStartCrawlFlag = False
                        self.mHostName = None
                        self.mRemoteDir = None
                        self.mHosts.clear()

    def __checkInputs(self):
        # setup rescue server and location if there isn't any
        self.mInputs.update({'location': self.mRemoteDir if self.mRemoteDir else '/'})
        self.mInputs.update({'target': self.mHostName if self.mHostName else None})

        if 'location' in self.mInputs and self.mInputs['location'] is not None and \
           'target' in self.mInputs and self.mInputs['target'] is not None and \
           not self.mStartCrawlFlag:
            # start the crawl process
            _logger.info('{}: start crawl url: {}'.format(self.objectName(), self.mInputs))
            self._findChildWidget('waitingIndicator').show()
            self.__crawlUrl(self.mInputs) # e.g. /pico-imx7/pi-070/
            self.mStartCrawlFlag = True

    def __crawlUrl(self, inputs):
        params = {}
        params.update(inputs)
        self.sendCommand({'cmd': 'info', 'target': params['target'], 'location': params['location']})

    def parseResult(self, results):
        if 'msger_type' in results and results['msger_type'] == 'dbus':
            if 'total_uncompressed' in results or 'total_size' in results:
                # step 3: figure out the xz file to download
                # extract total uncompressed size of the XZ file
                if 'total_uncompressed' in results:
                    uncompsize = results['total_uncompressed']
                elif 'total_size' in results:
                    uncompsize = results['total_size']
                else:
                    uncompsize = 0
                # extract form, cpu, board, display, and filename of the XZ file
                form, cpu, board, display, fname = self.__parseSOMInfo('/{}'.format(results['location'].split(self.mRemoteDir,1)[1]))
                # extract the os and ver number from the extracted filename of the XZ file
                os, ver, extra = self.__parseFilename(fname.rstrip('.xz'))
                # make up the XZ file URL
                url = results['target'] + results['location']
                # add {cpu, form, board, display, os, ver, size(uncompsize), url, extra}
                if os in ['rescue', 'android', 'ubuntu', 'boot2qt', 'yocto', 'androidthings']:
                    _logger.debug('{}: append result: {} {} {} {} {} {} {} {} {}'.format(self.objectName(), cpu, form, board, display, os, ver, uncompsize, url, extra))
                    self.mResults.append({'cpu': cpu, 'form': form, 'board': board, 'display': display, 'os': os, 'ver': ver, 'size': uncompsize, 'url': url, 'extra': extra})
                    for host in self.mHosts:
                        if host['name'] in results['target']:
                            host.update({'available': True})

            elif 'file_list' in results:
                # recursively request into the rescue server directories to find XZ files
                parsedList = self.__parseWebList(results)
                if len(parsedList) > 0 and isinstance(parsedList, list):
                    for item in parsedList:
                        if item[1].endswith('/'):
                            pobj = self.__checkUrl(item[2])
                            if pobj is not None:
                                _logger.debug('internet item path: {}'.format(pobj.path))
                                self.__crawlUrl({'cmd': results['cmd'], 'target':self.mHostName, 'location':pobj.path})
                        elif item[1].endswith('.xz'):
                            # match against the target device, and send request to obtain uncompressed size
                            _logger.debug('internet xzfile {} path: {}'.format(item[1], item[2]))
                            if self.__matchDevice(item[2].split(self.mHostName, 1)[1]):
                                self.__crawlUrl({'cmd': results['cmd'], 'target':self.mHostName, 'location': '{}'.format(item[2].split(self.mHostName, 1)[1])})

            if results['status'] == 'failure' and \
               results['target'] == self.mInputs['target'] and \
               self.mInputs['location'] in results['location']:
                # rescue server with location directory un-available, possibly
                # due to incorrect location or port or server failure, so flag
                # false and wait for time out to check another alive server
                _logger.warn('{} parse mHostName:{} and mRemoteDir:{} failed, set host un-available.'.format(self.objectName(), results['target'], results['location']))
                for host in self.mHosts:
                    if host['name'] in results['target']:
                        host.update({'available': False})
                        self.mHostName = None
                        self.mRemoteDir = None

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

    def __matchDevice(self, filename):
        # get the default cpu, form and board setting from detectDevice
        if self.mCpu is None:
            self.mCpu = self._findChildWidget('lblCpu').text().lower()
        if self.mForm is None:
            self.mForm = self._findChildWidget('lblForm').text().lower()
        if self.mBoard is None:
            self.mBoard = self._findChildWidget('lblBaseboard').text().lower()

        _logger.debug('{}: matching xzfile: {} to cpu: {} form: {}'.format(self.objectName(), filename, self.mCpu, self.mForm))

        # step 2: find menu items that matches as cpu, form, but not baseboard
        if self.mCpu in filename.lower() and self.mForm in filename.lower():
            # exact match of cpu in the filename, including imx6ul, imx6ull
            if self.mCpu == 'imx6' and 'imx6ul' in filename.lower():
                return False
            else:
                return True
        else:
            if self.mCpu.lower() == 'imx6ul' or self.mCpu.lower() == 'imx6ull' or self.mCpu[0:4].lower() == 'imx8':
                return False
            if self.mCpu[0:4] in filename.lower():
                if self.mForm.lower() in filename.lower():
                    return True
        return False

    def __parseSOMInfo(self, path):
        p = re.compile('\/(\w+)[_|-](\w+)\/(\w+)-(\w+)\/(.+)\.xz', re.IGNORECASE)
        m = p.match(path)
        if m:
            return m.groups()

    def __parseFilename(self, fname):
        if ('-' in fname):
            os, other = fname.split('-', 1)
        else:
            os, other = fname, ''
        if ('-' in other):
            ver, extra = other.split('-', 1)
        else:
            ver, extra = other, ''
        return os, ver, extra

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        if isinstance(self.mResults, list) and len(self.mResults):
            self._findChildWidget('waitingIndicator').hide()
            _logger.debug('{}: validate result: {}'.format(self.objectName(), self.mResults))
            # if found suitable xz files, send them on to the next process slot
            # but check for rescue update first.
            if not self.mRescueChecked:
                self.__checkForRescueUpdate()
                self.success.emit(self.mResults)
            self.sendError({'Show': False})

    def __checkForRescueUpdate(self):
        if not self.mRescueChecked:
            # check for rescue.xz in the extrated list
            year1, month1, day1, minor1 = self._findChildWidget('lblVersion').text().lower().split(' ')[1].split('.')
            date1 = datetime.date(int(year1), int(month1), int(day1))
            # get the latest rescue version
            year2, month2, day2, minor2 = (2000, 1, 1, 0)
            rescue_index = None
            rescues = []
            for item in self.mResults:
                if item['os'] == 'rescue':
                    rescues.append(item)
                    # has to match the target board
                    if item['board'] == self.mBoard and item['ver'] and len(item['ver']):
                        y, m, d, r = item['ver'].split('.')
                        d1 = datetime.date(int(year2), int(month2), int(day2))
                        d2 = datetime.date(int(y), int(m), int(d))
                        if d2 > d1 or (d2 == d1 and int(r) > int(minor2)):
                            year2 = y
                            month2 = m
                            day2 = d
                            minor2 = r
                            rescue_index = item

            date2 = datetime.date(int(year2), int(month2), int(day2))
            _logger.debug('{}: Check whether rescue needs update date1: {} / {} date2: {} / {} items: {} index: {}'.format(self.objectName(), date1, minor1, date2, minor2, rescues, rescue_index))
            if date2 > date1 or (date2 == date1 and int(minor2) > int(minor1)):
                # if needs updates, remove all other xz files from results
                # keep only the RescueIndexed item in self.mResults
                # found a rescue
                if rescue_index is not None:
                    rescues.remove(rescue_index)
                    del self.mResults[:]
                    self.mResults.append(rescue_index)
                    self.sendError({'Update': True, 'ask': 'continue'})

            # if no need for updates, remove all rescue files from xz file list
            if len(self.mResults) > 1 and len(rescues) > 0:
                for item in rescues:
                    self.mResults.remove(item)
            self.mRescueChecked = True



###############################################################################
#
# QChooseSlot subclassed from QProcessSlot for user selection
#
###############################################################################
class QChooseSlot(QProcessSlot):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = []
        self.mPick = {'board': None, 'os': None, 'ver': None, 'display': None, 'storage': None}

    def _parseResultList(self, listOfFileDict):
        # crawlWeb's results, i.e.
        # {
        #     'os': 'ubuntu', 'size': '3420454912', 'ver': '16.04', 'display': 'lcd800x480',
        #     'cpu': 'imx7', 'form': 'pico', 'board': 'dwarf',
        #     'url': 'http://rescue.technexion.net/rescue/pico-imx7/dwarf-lcd800x480/ubuntu-16.04.xz'
        # }
        #
        # scanStorage's results, i.e.
        # {
        #     'name': tgt[1], 'path': tgt[2]['device_node'], 'device_type': tgt[2]['device_type'],
        #     'size':int(tgt[2]['size']) * 512, 'id_bus': tgt[2]['id_bus'], 'id_serial': tgt[2]['id_serial'],
        #     'id_model': tgt[2]['id_model']
        # }
        #
        self.mResults.extend([d for d in listOfFileDict if int(d['size']) > 0])
        _logger.info('{}: list of storage/xz devices/files: {}'.format(self.objectName(), self.mResults))

    def _extractUIList(self):
        """
        To be overridden
        """
        pass

    def _filterList(self, key, pick, parsedUIList, origList):

        def enableList(key, parsedUIList, enabledSet):
            _logger.info('{}: Enable following ui: {}'.format(self.objectName(), enabledSet))
            if parsedUIList is not None:
                for ui in parsedUIList:
                    if ui[key] is not None:
                        ui['disable'] = True
                for enable in enabledSet:
                    for ui in parsedUIList:
                        if (enable in ui[key]):
                            ui['disable'] = False

        # filter picked options to construct a disabled set list
        enabled = []
        filteredDispAttr = []
        filteredAttr = []
        filteredAttr.extend(v for k, v in pick.items() if (v is not None and k != 'storage' and k != 'display'))
        if pick['display'] is not None and isinstance(pick['display'], list) and len(pick['display']):
            for disp in pick['display']:
                filteredDispAttr.append(disp)
                filteredDispAttr.extend(filteredAttr)
                enabled.extend(item[key] for item in self._findSubset(filteredDispAttr, origList) if item[key] is not None)
                filteredDispAttr.clear()
        else:
            if len(filteredAttr):
                enabled.extend(item[key] for item in self._findSubset(filteredAttr, origList) if item[key] is not None)
            else:
                enabled.extend(item[key] for item in origList if item[key] is not None)
        enabledSet = list(set(enabled))
        _logger.debug('{}: Enabled set: {}'.format(self.objectName(), enabledSet))
        enableList(key, parsedUIList, enabledSet)

    def _updateDisplay(self):
        self._findChildWidget('tabOS').hide()
        self._findChildWidget('tabBoard').hide()
        self._findChildWidget('tabDisplay').hide()
        self._findChildWidget('tabStorage').hide()
        self._findChildWidget('tabInstall').hide()
        if self.mPick['os'] is None:
            self._findChildWidget('tabOS').show()
            self._findChildWidget('lblInstruction').setText('Choose an OS')
        elif self.mPick['board'] is None:
            self._findChildWidget('tabBoard').show()
            self._findChildWidget('lblInstruction').setText('Choose your baseboard type')
        elif self.mPick['display'] is None:
            self._findChildWidget('tabDisplay').show()
            self._findChildWidget('lblInstruction').setText('Choose your panel type')
        elif self.mPick['storage'] is None:
            self._findChildWidget('tabStorage').show()
            self._findChildWidget('lblInstruction').setText('Choose a storage device to program')
        else:
            self._findChildWidget('tabInstall').show()
            self._findChildWidget('lblInstruction').setText('Click on selection (top right) icons to choose again')



@QProcessSlot.registerProcessSlot('chooseOS')
class chooseOSSlot(QChooseSlot):
    """
    Handles button click event to issue cmd to choose os
    """
    success = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mOSUIList = None
        self.mLstWgtOS = None
        self.mLstWgtSelection =None
        self.mUserData = None

    def process(self, inputs):
        # update Display the dynamic UI from the available list of found rescue files passed in inputs
        # update the UI element for later use
        if self.mLstWgtOS is None: self.mLstWgtOS = self._findChildWidget('lstWgtOS')
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')

        if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
            # parse the download files into selectable options, i.e. board, OS, ver, display
            self._parseResultList(inputs)
            self._extractUIList()
            if self.mOSUIList is not None and len(self.mOSUIList) == 1:
                # if crawlWeb only send 1 item in the inputs, automatically select it.
                for item in self.mOSUIList:
                    item['disable'] = False
                _insertToContainer(self.mOSUIList, self.mLstWgtOS, self.mLstWgtOS.itemClicked)
            else:
                _insertToContainer(self.mOSUIList, self.mLstWgtOS, None)

        if self.sender().objectName() == 'chooseOS' or self.sender().objectName() == 'chooseBoard' or \
           self.sender().objectName() == 'chooseDisplay' or self.sender().objectName() == 'chooseStorage' or \
           self.sender().objectName() == 'chooseSelection':
            # chooseOS or chooseBoard or chooseDisplay or chooseStorage, then sends a picked choice
            if isinstance(inputs, dict) and all(field in inputs for field in ['board', 'os', 'ver', 'display', 'storage']):
                _logger.info('self:{} sender:{}, old pick:{}, new pick:{}'.format(self.objectName(), self.sender().objectName(), self.mPick, inputs))
                self.mPick.update(inputs)
                self._filterList('os', self.mPick, self.mOSUIList, self.mResults)
                _insertToContainer(self.mOSUIList, self.mLstWgtOS, None)
                if 'edm' in self._findChildWidget('lblForm').text().lower() and self.mOSUIList is not None and len(self.mOSUIList) == 1 and inputs['os'] is None:
                    self.finish.emit()

        if self.sender() == self.mLstWgtOS:
            # inputs is the item chosen from the OS list widget
            if isinstance(inputs, QtGui.QListWidgetItem):
                # extract clicked item's user data
                self.mUserData = inputs.data(QtCore.Qt.UserRole)
                # setup picked os
                if (int(inputs.flags()) & QtCore.Qt.ItemIsEnabled):
                    self.mPick['os'] = self.mUserData['os'][:]
                else:
                    self.mPick['os'] = None

                # setup latest version
                #self.mPick['ver'] = self.__extractLatestVersion()
                if (int(inputs.flags()) & QtCore.Qt.ItemIsEnabled):
                    self.mPick['ver'] = self.mUserData['ver'][:]
                else:
                    self.mPick['ver'] = None

                # add to lstWgtSelection if not disabled
                if not self.mUserData['disable']:
                    item = QtGui.QListWidgetItem(inputs)
                    self.mUserData['ver'] = self.mPick['ver']
                    item.setData(QtCore.Qt.UserRole, self.mUserData)
                    item.setText("")
                    rowNum = self.mLstWgtSelection.count()
                    if rowNum:
                        for s in self.mLstWgtSelection.findItems('.*', QtCore.Qt.MatchRegExp):
                            if 'os' in s.data(QtCore.Qt.UserRole):
                                if int(s.flags()) & ~QtCore.Qt.ItemIsEnabled:
                                    # if selection item has an disabled existing item, remove it
                                    rowNum = self.mLstWgtSelection.row(s)
                                    taken = self.mLstWgtSelection.takeItem(rowNum)
                                    del taken
                    # else insert into the selection list
                    self.mLstWgtSelection.insertItem(rowNum, item)
                    self.mLstWgtSelection.clearSelection()
            self.finish.emit()

    def _extractUIList(self):
        # gets the unique set of available boards, OS, version, Display from the crawled list
        #self.mOSNames = list(set(dlfile['os'] for dlfile in self.mResults if ('os' in dlfile)))
        uilist = [{'os':dlfile['os'], 'ver':dlfile['ver']} for dlfile in self.mResults if ('os' in dlfile and 'ver' in dlfile)]
        self.mOSNames = list({(v['os'], v['ver']):v for v in uilist}.values())
        _logger.debug('{}: extract os uilist: {} os names: {}'.format(self.objectName(), uilist, self.mOSNames))
        self.mVerList = []
        for d in [{'os':dlfile['os'], 'ver':dlfile['ver']} for dlfile in self.mResults if ('os' in dlfile and 'ver' in dlfile)]:
            if all(not (d == n) for n in self.mVerList):
                self.mVerList.append(d)
        # come up with a new list to send to GUI container, i.e. QListWidget
        #self.mOSUIList = list({'name': name, 'os': name, 'disable': False} for name in self.mOSNames)
        self.mOSUIList = list({'name': '{}-{}'.format(item['os'], item['ver']), 'os': item['os'], 'ver': item['ver'], 'disable': False} for item in self.mOSNames)

    def __extractLatestVersion(self):
        def parseVersion(strVersion):
            try:
                if strVersion.count('.') > 1:
                    strVersion.replace('.', '', strVersion.count('.') - 1)
                found = float(re.search('\d+\.\d+', strVersion).group(0))
            except:
                found = 0.0
            return found

        # Find newest version from the picked os
        version = 0.0
        for item in self.mVerList:
            if self.mPick['os'] == item['os'] and version < parseVersion(item['ver']):
                version = parseVersion(item['ver'])
                retVer = item['ver']
        return retVer if version > 0.0 else None

    # NOTE: Not using the resultSlot() and in turn parseResult(), because we did not send a request via DBus
    # to get results from installerd
    #def parseResult(self, results):
    #    pass

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # so check for valid storage to flash selected Url file here
        if self.mPick['os'] is not None:
            # show/hide GUI components
            self.mLstWgtOS.clearSelection()
            self.success.emit(self.mPick)
            self._updateDisplay()
        else:
            if 'edm' in self._findChildWidget('lblForm').text().lower() and len(self.mOSUIList) == 1:
                self.mPick['os'] = self.mOSUIList[0]['os'][:]
                self.mLstWgtOS.clearSelection()
                self.success.emit(self.mPick)
            else:
                _logger.info('{}: failed to choose a valid option'.format(self.objectName()))



@QProcessSlot.registerProcessSlot('chooseBoard')
class chooseBoardSlot(QChooseSlot):
    """
    Handles button click event to issue cmd to choose board
    """
    success = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mBoardUIList = None
        self.mLstWgtBoard = None
        self.mLstWgtSelection =None
        self.mUserData = None

    def process(self, inputs):
        # update Display the dynamic UI from the available list of found rescue files passed in inputs
        # update the UI element for later use
        if self.mLstWgtBoard is None: self.mLstWgtBoard = self._findChildWidget('lstWgtBoard')
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')

        if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
            # parse the download files into selectable options, i.e. board, OS, ver, display
            self._parseResultList(inputs)
            self._extractUIList()
            if self.mBoardUIList is not None and len(self.mBoardUIList) == 1:
                # if crawlWeb only send 1 item in the inputs, automatically select it.
                for item in self.mBoardUIList:
                    item['disable'] = False
                _insertToContainer(self.mBoardUIList, self.mLstWgtBoard, self.mLstWgtBoard.itemClicked)
            else:
                _insertToContainer(self.mBoardUIList, self.mLstWgtBoard, None)

        if self.sender().objectName() == 'chooseOS' or self.sender().objectName() == 'chooseBoard' or \
           self.sender().objectName() == 'chooseDisplay' or self.sender().objectName() == 'chooseStorage' or \
           self.sender().objectName() == 'chooseSelection':
            # chooseOS or chooseBoard or chooseDisplay or chooseStorage, then sends a picked choice
            if isinstance(inputs, dict) and all(field in inputs for field in ['board', 'os', 'ver', 'display', 'storage']):
                _logger.info('self:{}, sender:{}, old pick:{}, new pick:{}'.format(self.objectName(), self.sender().objectName(), self.mPick, inputs))
                self.mPick.update(inputs)
                self._filterList('board', self.mPick, self.mBoardUIList, self.mResults)
                _insertToContainer(self.mBoardUIList, self.mLstWgtBoard, None)
                if 'edm' in self._findChildWidget('lblForm').text().lower() and self.mBoardUIList is not None and len(self.mBoardUIList) == 1 and inputs['board'] is None:
                    self.finish.emit()

        if self.sender() == self.mLstWgtBoard:
            # inputs is the item chosen from the OS list widget
            if isinstance(inputs, QtGui.QListWidgetItem):
                # add to lstWgtSelection
                self.mUserData = inputs.data(QtCore.Qt.UserRole)
                if (int(inputs.flags()) & QtCore.Qt.ItemIsEnabled):
                    self.mPick['board'] = self.mUserData['board'][:]
                else:
                    self.mPick['board'] = None
                if not self.mUserData['disable']:
                    item = QtGui.QListWidgetItem(inputs)
                    item.setData(QtCore.Qt.UserRole, self.mUserData)
                    rowNum = self.mLstWgtSelection.count()
                    if rowNum:
                        for s in self.mLstWgtSelection.findItems('.*', QtCore.Qt.MatchRegExp):
                            if 'board' in s.data(QtCore.Qt.UserRole):
                                if int(s.flags()) & ~QtCore.Qt.ItemIsEnabled:
                                    # if selection item has an disabled existing item, remove it
                                    rowNum = self.mLstWgtSelection.row(s)
                                    taken = self.mLstWgtSelection.takeItem(rowNum)
                                    del taken
                    # else insert into the selection list
                    self.mLstWgtSelection.insertItem(rowNum, item)
                    self.mLstWgtSelection.clearSelection()
            self.finish.emit()

    def _extractUIList(self):
        # gets the unique set of available boards, OS, version, Display from the crawled list
        self.mBoardNames = set(dlfile['board'] for dlfile in self.mResults if ('board' in dlfile))
        # come up with a new list to send to GUI container, i.e. QListWidget
        self.mBoardUIList = list({'name': name, 'board': name, 'disable': False} for name in self.mBoardNames)

    # NOTE: Not using the resultSlot() and in turn parseResult(), because we did not send a request via DBus
    # to get results from installerd
    #def parseResult(self, results):
    #    pass

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # so check for valid storage to flash selected Url file here
        if self.mPick['board'] is not None:
            self.mLstWgtBoard.clearSelection()
            self.success.emit(self.mPick)
            # show/hide GUI components
            self._updateDisplay()
        else:
            if 'edm' in self._findChildWidget('lblForm').text().lower() and len(self.mBoardUIList) == 1:
                self.mPick['board'] = self.mBoardUIList[0]['board'][:]
                self.mLstWgtBoard.clearSelection()
                self.success.emit(self.mPick)
            else:
                _logger.info('{}: failed to choose a valid option'.format(self.objectName()))



@QProcessSlot.registerProcessSlot('chooseDisplay')
class chooseDisplaySlot(QChooseSlot):
    """
    Handles button click event to issue cmd to choose display
    """
    success = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mDisplayUIList = []
        self.mLstWgtDisplay = None
        self.mLstWgtSelection =None
        self.mIfaceTypes = ['lvds', 'hdmi', 'ttl', 'vga', 'dsi', 'dpi']

    def process(self, inputs):
        # update Display the dynamic UI from the available list of found rescue files passed in inputs
        # update the UI element for later use
        if self.mLstWgtDisplay is None: self.mLstWgtDisplay = self._findChildWidget('lstWgtDisplay')
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')

        if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
            # parse the download files into selectable options, i.e. board, OS, ver, display
            self._parseResultList(inputs)
            self._extractUIList()
            if self.mDisplayUIList is not None and len(self.mDisplayUIList) == 1:
                # if crawlWeb only send 1 item in the inputs, automatically select it.
                for item in self.mDisplayUIList:
                    item['disable'] = False
                _insertToContainer(self.mDisplayUIList, self.mLstWgtDisplay, self.mLstWgtDisplay.itemClicked)
            else:
                _insertToContainer(self.mDisplayUIList, self.mLstWgtDisplay, None)

        if self.sender().objectName() == 'chooseOS' or self.sender().objectName() == 'chooseBoard' or \
           self.sender().objectName() == 'chooseDisplay' or self.sender().objectName() == 'chooseStorage' or \
           self.sender().objectName() == 'chooseSelection':
            # chooseOS or chooseBoard or chooseDisplay or chooseStorage, then sends a picked choice
            if isinstance(inputs, dict) and all(field in inputs for field in ['board', 'os', 'ver', 'display', 'storage']):
                _logger.info('self:{}, sender:{}, old pick:{}, new pick:{}'.format(self.objectName(), self.sender().objectName(), self.mPick, inputs))
                self.mPick.update(inputs)
                self._filterList('display', self.mPick, self.mDisplayUIList, self.mResults)
                _insertToContainer(self.mDisplayUIList, self.mLstWgtDisplay, None)
                if 'edm' in self._findChildWidget('lblForm').text().lower() and self.mDisplayUIList is not None and len(self.mDisplayUIList) == 1 and inputs['display'] is None:
                    self.finish.emit()

        if self.sender() == self.mLstWgtDisplay:
            # inputs is the item chosen from the OS list widget
            if isinstance(inputs, QtGui.QListWidgetItem):
                # add to lstWgtSelection
                self.mUserData = inputs.data(QtCore.Qt.UserRole)
                # setup the user display pick
                if (int(inputs.flags()) & QtCore.Qt.ItemIsEnabled):
                    self.mPick['display'] = self.mUserData['display']
                else:
                    self.mPick['display'] = None
                if not self.mUserData['disable']:
                    item = QtGui.QListWidgetItem(inputs)
                    item.setData(QtCore.Qt.UserRole, self.mUserData)
                    rowNum = self.mLstWgtSelection.count()
                    if rowNum:
                        for s in self.mLstWgtSelection.findItems('.*', QtCore.Qt.MatchRegExp):
                            if 'display' in s.data(QtCore.Qt.UserRole):
                                if int(s.flags()) & ~QtCore.Qt.ItemIsEnabled:
                                    # if selection item has an disabled existing item, remove it
                                    rowNum = self.mLstWgtSelection.row(s)
                                    taken = self.mLstWgtSelection.takeItem(rowNum)
                                    del taken
                    # else insert into the selection list
                    self.mLstWgtSelection.insertItem(rowNum, item)
                    self.mLstWgtSelection.clearSelection()
            self.finish.emit()

    def _extractUIList(self):
        lstTemp = []
        # gets the unique set of available boards, OS, version, Display from the crawled list
        self.mDisplayNames = set(dlfile['display'] for dlfile in self.mResults if ('display' in dlfile))
        for name in self.mDisplayNames:
            if any(sz in name for sz in ['050', 'lcd']):
                iftype = 'ttl'
            elif any(sz in name for sz in ['070']):
                # filter out 050, 070 they are mostly lcds
                iftype = 'lvds' if any (sz in self._findChildWidget('lblForm').text().lower() for sz in ['edm']) else 'ttl'
            elif any(sz in name for sz in ['101', '150']):
                iftype = 'lvds'
            elif any(sz in name for sz in ['mipi', 'dsi', 'dpi']):
                iftype = 'dpi' if 'dpi' in name else 'dsi'
            elif any(sz in name for sz in ['hdmi']):
                iftype = 'hdmi'
            else:
                iftype = 'vga'

            if iftype is not None:
                lstTemp.append({'name': name, 'display': name, 'ifce_type': iftype, 'disable': False})

        # come up with a new list to send to GUI container, i.e. QListWidget
        for t in self.mIfaceTypes:
            disps = list(l['name'] for l in lstTemp if (l['ifce_type'] == t))
            if len(disps) > 0:
                self.mDisplayUIList.append({'name': t, 'display': disps, 'ifce_type': t, 'disable': False})

    # NOTE: Not using the resultSlot() and in turn parseResult(), because we did not send a request via DBus
    # to get results from installerd
    #def parseResult(self, results):
    #    pass

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # so check for valid storage to flash selected Url file here
        if self.mPick['display'] is not None:
            # show/hide GUI components
            self.mLstWgtDisplay.clearSelection()
            self.success.emit(self.mPick)
            self._updateDisplay()
        else:
            if 'edm' in self._findChildWidget('lblForm').text().lower() and len(self.mDisplayUIList) == 1:
                self.mPick['display'] = self.mDisplayUIList[0]['display'][:]
                self.mLstWgtDisplay.clearSelection()
                self.success.emit(self.mPick)
            else:
                _logger.info('{}: failed to choose a valid option'.format(self.objectName()))



@QProcessSlot.registerProcessSlot('chooseStorage')
class chooseStorageSlot(QChooseSlot):
    """
    Handles button click event to issue cmd to choose board, os, and display
    """
    success = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mStorageUIList = None
        self.mLstWgtStorage = None
        self.mLstWgtSelection =None
        self.mPick = {'board': None, 'os': None, 'ver': None, 'display': None, 'storage': None}

    def process(self, inputs):
        # Display the dynamic UI from the available list of found target storage passed in inputs
        # get the UI element to update
        if self.mLstWgtStorage is None: self.mLstWgtStorage = self._findChildWidget('lstWgtStorage')
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')

        if self.sender().objectName() == 'scanStorage' and isinstance(inputs, list):
            # parse the available storage devices into selectable options,
            self._parseResultList(inputs)
            self._extractUIList()
            _insertToContainer(self.mStorageUIList, self.mLstWgtStorage, None)

        if self.sender().objectName() == 'chooseOS' or self.sender().objectName() == 'chooseBoard' or \
           self.sender().objectName() == 'chooseDisplay' or self.sender().objectName() == 'chooseStorage' or \
           self.sender().objectName() == 'chooseSelection':
            # chooseOS or chooseBoard or chooseDisplay or chooseStorage, then sends a picked choice
            if isinstance(inputs, dict) and all(field in inputs for field in ['board', 'os', 'ver', 'display', 'storage']):
                _logger.info('self:{}, sender:{}, old pick:{}, new pick:{}'.format(self.objectName(), self.sender().objectName(), self.mPick, inputs))
                self.mPick.update(inputs)
                #self._disableList('storage', self.mStorageUIList, self.mResults)
            if self.mPick['os'] is not None and self.mPick['ver'] is not None and \
               self.mPick['board'] is not None and self.mPick['display'] is not None and \
               self.mStorageUIList is not None and len(self.mStorageUIList) == 1:
                # if scanStorage only send 1 item in the inputs, automatically select it.
                for item in self.mStorageUIList:
                    item['disable'] = False
                _insertToContainer(self.mStorageUIList, self.mLstWgtStorage, self.mLstWgtStorage.itemClicked)

        if self.sender() == self.mLstWgtStorage:
            # parse the QListWidgetItem to get the chosen storage
            if isinstance(inputs, QtGui.QListWidgetItem):
                self.mUserData = inputs.data(QtCore.Qt.UserRole)
                # setup the user storage pick
                if (int(inputs.flags()) & QtCore.Qt.ItemIsEnabled):
                    self.mPick['storage'] = self.mUserData['storage'][:]
                else:
                    self.mPick['storage'] = None
                if not self.mUserData['disable']:
                    # add to lstWgtSelection
                    item = QtGui.QListWidgetItem(inputs)
                    item.setData(QtCore.Qt.UserRole, self.mUserData)
                    rowNum = self.mLstWgtSelection.count()
                    if rowNum:
                        for s in self.mLstWgtSelection.findItems('.*', QtCore.Qt.MatchRegExp):
                            if 'storage' in s.data(QtCore.Qt.UserRole):
                                if int(s.flags()) & ~QtCore.Qt.ItemIsEnabled:
                                    # if selection item has an disabled existing item, remove it
                                    rowNum = self.mLstWgtSelection.row(s)
                                    taken = self.mLstWgtSelection.takeItem(rowNum)
                                    del taken
                    # else insert into the selection list
                    self.mLstWgtSelection.insertItem(rowNum, item)
                    self.mLstWgtSelection.clearSelection()
                self.finish.emit()

    def _extractUIList(self):
        # come up with a new list to send to GUI container, i.e. QListWidget
        self.mStorageUIList = list({'name': item['name'], \
                                  'storage': item['path'], \
                                  'device_type': item['device_type'], \
                                  'conntype': item['conntype'], \
                                  'size': item['size'], \
                                  'id_bus': item['id_bus'], \
                                  'uevent': item['uevent'], \
                                  'disable': False} for item in self.mResults if item['id_bus'] != 'ata')
        _logger.debug('{}: mStorageUIList: {}'.format(self.objectName(), self.mStorageUIList))

    # NOTE: Not using the resultSlot() and in turn parseResult(), because we did not send a request via DBus
    # to get results from installerd
    #def parseResult(self, results):
    #    pass

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # so check for valid storage to flash selected Url file here
        if self.mPick['storage'] is not None:
            # show/hide GUI components
            if 'conntype' in self.mPick: self.mPick.pop('conntype')
            self.mLstWgtStorage.clearSelection()
            self.success.emit(self.mPick)
            self._updateDisplay()
        else:
            _logger.info('{}: failed to choose a valid storage to program'.format(self.objectName()))



@QProcessSlot.registerProcessSlot('chooseSelection')
class chooseSelectionSlot(QChooseSlot):
    """
    Handles button click event to issue cmd to handle re-choose of os, board, display, and storage
    """
    success = pyqtSignal(dict)
    chosen = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = {}
        self.mLstWgtSelection =None
        self.mLstWgtStorage = None
        self.mLstWgtOS = None
        self.mLstWgtBoard = None
        self.mLstWgtDisplay = None
        self.mUserData = None
        self.mPartitions = {}

    def process(self, inputs):
        # Display the dynamic UI from the available list of found target storage passed in inputs
        # get the UI element to update
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')
        if self.mLstWgtStorage is None: self.mLstWgtStorage = self._findChildWidget('lstWgtStorage')
        if self.mLstWgtOS is None: self.mLstWgtOS = self._findChildWidget('lstWgtOS')
        if self.mLstWgtBoard is None: self.mLstWgtBoard = self._findChildWidget('lstWgtBoard')
        if self.mLstWgtDisplay is None: self.mLstWgtDisplay = self._findChildWidget('lstWgtDisplay')

        if self.sender().objectName() == 'chooseOS' or self.sender().objectName() == 'chooseBoard' or \
           self.sender().objectName() == 'chooseDisplay' or self.sender().objectName() == 'chooseStorage':
            # chooseOS or chooseBoard or chooseDisplay or chooseStorage, then sends a picked choice
            if isinstance(inputs, dict) and all(field in inputs for field in ['board', 'os', 'ver', 'display', 'storage']):
                _logger.debug('self:{}, sender:{}, old pick:{}, new pick:{}'.format(self.Name(), self.sender().objectName(), self.mPick, inputs))
                self.mPick.update(inputs)
                self._updateOutputLabel()

        if self.sender().objectName() == 'btnFlash':
            # receive the btnFlash click signal
            if 'storage' in self.mPick and self.mPick['storage'] is not None:
                ret = self._backupRescue()
                if ret == 0:
                    self.mResults.update(self.mPick)
                    self.mResults.update({'status': 'success', 'cmd': 'dd'})
                    self.finish.emit()

        if self.sender() == self.mLstWgtSelection:
            # parse the QListWidgetItem to get data that indicate which choice it came from
            if isinstance(inputs, QtGui.QListWidgetItem):
                # get the user data and update the pick
                self.mUserData = inputs.data(QtCore.Qt.UserRole)
                if 'os' in self.mUserData:
                    self.mPick['os'] = None
                    self.mPick['ver'] = None
                elif 'board' in self.mUserData:
                    self.mPick['board'] = None
                elif 'display' in self.mUserData:
                    self.mPick['display'] = None
                elif 'storage' in self.mUserData:
                    self.mPick['storage'] = None
                # disable the clicked/selected item from the lstWgtSelection
                self.mRowToRemove = self.mLstWgtSelection.row(inputs)
                if inputs.flags() & QtCore.Qt.ItemIsEnabled:
                    inputs.setFlags(inputs.flags() & ~QtCore.Qt.ItemIsEnabled)
                # show/hide GUI components
                self.mLstWgtSelection.clearSelection()
                self._updateDisplay()
                # send the self.mPick to appropriate QProcSlot so picking
                # process can be restarted from where it is disgarded
                self.success.emit(self.mPick)

        if self.sender().objectName() == 'scanPartition' and isinstance(inputs, dict):
            # figure out the partition size to backup
            for k, v in inputs.items():
                if isinstance(v, dict) and 'sys_number' in v and int(v['sys_number']) == 1 and \
                   'sys_name' in v and 'mmcblk' in v['sys_name'] and \
                   'attributes' in v and isinstance(v['attributes'], dict) and \
                   'size' in v['attributes'] and 'start' in v['attributes']:
                        self.mPartitions.update({v['device_node']: int(v['attributes']['start']) + int(v['attributes']['size'])})
                        _logger.info('{}: {}: Start: {}, Size: {}, Partition: {}'.format(self.objectName(), k, int(v['attributes']['start']), int(v['attributes']['size']), self.mPartitions))

    def _backupRescue(self):
        self._findChildWidget('lblInstruction').setText('Backing up Rescue System...')
        chunks = '64'
        if '{}p1'.format(self.mPick['storage']) in self.mPartitions:
            # dd first partition (size extract from self.mPartitions of /dev/mmcblkXp1 to target storage
            bsize = int(self.mPartitions['{}p1'.format(self.mPick['storage'])] * 8) # 512/64 = 8
        else:
            # dd the first 139264 sectors(71,303,168 bytes, i.e. mbr boot sector + SPL), NOTE: bs = 1114112 = 71,303,168 * 512 / 64
            bsize = 1114112
        try:
            _logger.info('{}: dd if={} of=/tmp/rescue.img bs={} count={} conv=notrunc'.format(self.objectName(), self.mPick['storage'], bsize, chunks))
            ret = subprocess.check_call(['dd', 'if={}'.format(self.mPick['storage']), 'of=/tmp/rescue.img', 'bs={}'.format(bsize), 'count={}'.format(chunks), 'conv=notrunc'])
        except subprocess.CalledProcessError as err:
            return err.returncode
        return ret

    def parseResult(self, results):
        # flash command complete and the results are updated/parsed here
        self.mResults.update(results)

    def validateResult(self):
        # flow comes here after self.finish.emit() - gets called or when cmd is removed from self.mCmds
        if self.mResults['status'] == 'success' and self.mResults['cmd'] == 'dd':
            # send the mPick to downloadImage procslot
            if all(p is not None for p in self.mPick if (key in self.mPick for key in ['os', 'board', 'display', 'storage'])):
                if hasattr(self._findChildWidget('downloadImage'), 'processSlot'):
                    try:
                        self.chosen.disconnect()
                        # disconnect chosen signal first
                    except:
                        _logger.debug('{}: disconnect chosen signal first'.format(self.objectName()))
                    self.chosen.connect(getattr(self._findChildWidget('downloadImage'), 'processSlot'))
                    self.chosen.emit(self.mPick)

    def _updateDisplay(self):
        if 'os' in self.mUserData:
            self._findChildWidget('tabInstall').hide()
            self._findChildWidget('tabBoard').hide()
            self._findChildWidget('tabDisplay').hide()
            self._findChildWidget('tabStorage').hide()
            self._findChildWidget('tabOS').show()
            self._findChildWidget('lblInstruction').setText('Choose an OS')
        elif 'board' in self.mUserData:
            self._findChildWidget('tabInstall').hide()
            self._findChildWidget('tabOS').hide()
            self._findChildWidget('tabDisplay').hide()
            self._findChildWidget('tabStorage').hide()
            self._findChildWidget('tabBoard').show()
            self._findChildWidget('lblInstruction').setText('Choose your baseboard type')
        elif 'display' in self.mUserData:
            self._findChildWidget('tabInstall').hide()
            self._findChildWidget('tabOS').hide()
            self._findChildWidget('tabBoard').hide()
            self._findChildWidget('tabStorage').hide()
            self._findChildWidget('tabDisplay').show()
            self._findChildWidget('lblInstruction').setText('Choose your panel type')
        elif 'storage' in self.mUserData:
            self._findChildWidget('tabInstall').hide()
            self._findChildWidget('tabOS').hide()
            self._findChildWidget('tabBoard').hide()
            self._findChildWidget('tabDisplay').hide()
            self._findChildWidget('tabStorage').show()
            self._findChildWidget('lblInstruction').setText('Choose a storage device to program')

    def _updateOutputLabel(self):
        for item in self._findChildWidget('lstWgtSelection').findItems('.*', QtCore.Qt.MatchRegExp):
            data = item.data(QtCore.Qt.UserRole)
            if 'os' in self.mPick and self.mPick['os'] is not None and 'os' in data and data['os'] is not None and self.mPick['os'] == data['os']:
                # update text/icon on lblOS with chosen OS name and version number
                self._findChildWidget('lblOS').setPixmap(item.icon().pixmap(self._findChildWidget('lblOS').size()))
                self._findChildWidget('lblOSTxt').setText('{}\n{}'.format(self.mPick['os'], self.mPick['ver'] if self.mPick['ver'] is not None else ''))

            elif 'board' in self.mPick and self.mPick['board'] is not None and 'board' in data and data['board'] is not None and self.mPick['board'] == data['board']:
                # update text/icon on lblBoard with chosen board
                self._findChildWidget('lblBoard').setPixmap(item.icon().pixmap(self._findChildWidget('lblBoard').size()))
                self._findChildWidget('lblBoardTxt').setText('{}'.format(self.mPick['board']))

            elif 'display' in self.mPick and self.mPick['display'] is not None and 'display' in data and data['display'] is not None and self.mPick['display'] == data['display']:
                # self.mPick['display'] could be a list of '050', '070' etc
                # update text/icon on lblDisplay with chosen display
                self._findChildWidget('lblDisplay').setPixmap(item.icon().pixmap(self._findChildWidget('lblDisplay').size()))
                self._findChildWidget('lblDisplayTxt').setText('{}'.format('/\n'.join(self.mPick['display'])))

            elif 'storage' in self.mPick and self.mPick['storage'] is not None and 'storage' in data and data['storage'] is not None and self.mPick['storage'] == data['storage']:
                # update text/icon on lblStorage with chosen storage
                self._findChildWidget('lblStorage').setPixmap(item.icon().pixmap(self._findChildWidget('lblStorage').size()))
                # determine eMMC vs SDCard
                if 'MMC_TYPE=MMC' in data['uevent']:
                    text = 'eMMC'
                elif 'id_bus' in data and data['id_bus'] == 'ata':
                    text = 'HD'
                else:
                    text = 'SDCard'
                if data['conntype'] == 'serial':
                    text = text + '\non Target'
                    self._findChildWidget('lblStorageTxt').setText(text)



@QProcessSlot.registerProcessSlot('downloadImage')
class downloadImageSlot(QProcessSlot):
    """
    Handles button click event to issue cmd to download and flash
    """
    progress = pyqtSignal(int)
    success = pyqtSignal(dict)
    mount = pyqtSignal()

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mFileList = []
        self.mDetects = {}
        self.mResults = {}
        self.mFileUrl = None
        self.mTgtStorage = None
        self.mFlashFlag = False
        self.mAvSpeed = 0
        self.mLastWritten = 0
        self.mRemaining = 0
        self.mTimerId = None
        self.mLblRemain = None
        self.mLblDownloadFlash = None
        self.mLstWgtSelection = None
        self.mProgressBar = None
        self.mPick = {'board': None, 'os': None, 'ver': None, 'display': None, 'storage': None}
        self.mTotalMem = None
        self.mHosts = []
        self.mAlternativeFlag = False
        self.mDefaultPorts = {'http': 80, 'https': 443, 'ftp': 21}

    def _queryResult(self, percent = 0):
        """
        A callback function acting as a slot for timer's timeout signal.
        Here we calculate the remaining time for the download and flash and update UI accordingly.
        """
        if self.mViewer:
            try:
                # this will issue query results to all the different messengers
                res = self.mViewer.queryResult('dbus')
            except:
                _logger.warn('{}: query result from DBus Server Failed... Recover Rescue System...'.format(self.objectName()))
                # cannot query installerd dbus server anymore, something wrong.
                # stop the timer, and recover the rescue system
                if self.mTimerId:
                    self.killTimer(self.mTimerId)
                # use subprocess to restor the rescue system
                # i.e. subprocess.check_call(['mmc', 'bootpart', 'enable', '0', '1', '/dev/mmcblk2'])
                try:
                    subprocess.check_call(['dd', 'if=/tmp/rescue.img', 'of={}'.format(self.mTgtStorage), 'bs=1M', 'conv=notrunc,fsync'])
                except subprocess.CalledProcessError as err:
                    _logger.error('{}: cmd: {} return code:{} output: {}'.format(self.objectName(), err.cmd, err.returncode, err.output))
                    raise
                self.sendError({'NoDbus': True, 'ask': 'reboot'})
                return
            else:
                if res == {}:
                    _logger.debug('{}: query returns nothing, set to percent passed in.'.format(self.objectName()))
                    self.progress.emit(percent)
                else:
                    if 'total_uncompressed' in res and 'bytes_written' in res:
                        smoothing = 0.005
                        lastSpeed = int(res['bytes_written']) - self.mLastWritten
                        # averageSpeed = SMOOTHING_FACTOR * lastSpeed + (1-SMOOTHING_FACTOR) * averageSpeed;
                        self.mAvSpeed = smoothing * lastSpeed + (1 - smoothing) * self.mAvSpeed
                        self.mRemaining = float((int(res['total_uncompressed']) - int(res['bytes_written'])) / self.mAvSpeed if self.mAvSpeed > 0 else 0.0001)
                        self.mLastWritten = int(res['bytes_written'])
                        _logger.debug('{}: total: {} written:{} av:{} remain: {}'.format(self.objectName(), int(res['total_uncompressed']), int(res['bytes_written']), self.mAvSpeed, self.mRemaining))
                        self.mLblRemain.setText('Remaining Time: {:02}:{:02}'.format(int(self.mRemaining / 60), int(self.mRemaining % 60)))
                        pcent = int(round(float(res['bytes_written']) / float(res['total_uncompressed']) * 100))
                        self.progress.emit(pcent)

    def __mountStorage(self):
        try:
            self.mount.disconnect()
        except:
            pass
        if hasattr(self._findChildWidget('mountStorage'), 'processSlot'):
            self.mount.connect(self._findChildWidget('mountStorage').processSlot)
            self.mount.emit()
            self.mount.disconnect()

    def __parseHosts(self, hosts=None):
        if hosts is not None and isinstance(hosts, list) and \
           all(('alive' in host and 'name' in host) for host in hosts):
            if self.mHosts == []:
                # get the first alive TechNexion server host
                for h in hosts:
                    self.mHosts.append(dict(h))
            else:
                for host in self.mHosts:
                    for h in hosts:
                        if host['name'] == h['name']:
                            # if alive flag is different, then something is wrong
                            if host['alive'] != h['alive']:
                                host['alive'] = h['alive']
            _logger.info('{} hosts updated to:{}'.format(self.objectName(), self.mHosts))

    def __checkNetworkError(self):
        _logger.debug('{}: check NIC/NET error... mDetects:{}'.format(self.objectName(), self.mDetects))
        if self.mFlashFlag:
            # mDetects are errors passed in from scanNetwork after crawling has started
            if any(v is True for v in self.mDetects.values()):
                _logger.error('{}: NIC/NET error detected during flash... so ask for serial connect mode'.format(self.objectName()))
                # the system cannot connect to our rescue server, try a different server
                self.sendError({'NoNetwork': True, 'ask': 'serial' if IsATargetBoard() else 'quit'})

    def __checkMemory(self):
        self.sendCommand({'cmd': 'info', 'target': 'mem', 'location': 'total'})

    def __checkBeforeFlash(self):
        cpu = self._findChildWidget('lblCpu').text().lower()
        if self.mPick['os'] == 'android' and 'imx7' in cpu:
            self.sendError({'NoResource': True, 'ask': 'continue'})
        else:
            _logger.info('{}: download from {} and flash to {}'.format(self.objectName(), self.mFileUrl, self.mTgtStorage))
            self.sendCommand({'cmd': 'download', 'dl_url': self.mFileUrl, 'tgt_filename': self.mTgtStorage})
            # show/hide GUI components
            self._updateDisplay()

    def __retryAlternativeServer(self):
        if self.mAlternativeFlag:
            if self.__setAlternativeServer():
                # reset the progress bar
                self.progress.emit(0)
                if self.mTimerId:
                    self.killTimer(self.mTimerId)
                    self.mTimerId = None
                self.__checkBeforeFlash()
            else:
                # prompt error message for no alternative servers
                self.sendError({'NoAlternative': True, 'ask': 'continue'})
                self.success.emit(self.mPick)

    def process(self, inputs):
        #
        # grab the dl_url and tgt_filename from the tableRescueFile and tableTargetStorage itemClicked() signals
        # when signal sender is from btnFlash, issue flash command with clicked rescue file and target storage.
        #
        if self.mLblRemain is None:
            self.mLblRemain = self._findChildWidget('lblRemaining')
        if self.mLblDownloadFlash is None:
            self.mLblDownloadFlash = self._findChildWidget('lblDownloadFlash')
        if self.mLstWgtSelection is None:
            self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')
        if self.mProgressBar is None:
            self.mProgressBar = self._findChildWidget('progressBarStatus')
            if self.mProgressBar:
                self.progress.connect(self.mProgressBar.setValue)

        # get the default remote http server host_name from defconfig in self.mViewer
        if self.sender().objectName() == 'scanNetwork':
            if all(isinstance(item, dict) for item in inputs):
                # found hosts, parse alive/connectable rescue servers
                self.__parseHosts(inputs)
            elif all(isinstance(item, tuple) for item in inputs):
                # scanNetwork errors
                if dict(self.mDetects, **dict(inputs)) != self.mDetects:
                    self.mDetects.update(dict(inputs))
                    self.__checkNetworkError()

        if self.sender().objectName() == 'processError':
            if isinstance(inputs, dict) and 'alternative' in inputs.keys():
                _logger.debug('{}: ask:alternative signal from processError: alternative:{}'.format(self.objectName(), inputs['alternative']))
                self.mAlternativeFlag = inputs['alternative']
                # Queue the retry on alternative server in 1s
                self.__retryAlternativeServer()

            if isinstance(inputs, dict) and 'accept' in inputs.keys() and 'reject' in inputs.keys():
                _logger.debug('{}: ask:serial signal from processError: accept:{} reject:{}'.format(self.objectName(), inputs['accept'], inputs['reject']))
                if self.inputs('accept'):
                    self.__mountStorage()
                else:
                    # Queue the retry on alternative server in 1s
                    self.__retryAlternativeServer()

        if not self.mFlashFlag:
            # keep the available file list for lookup with a signalled self.mPick later
            if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
                self.mFileList.extend([d for d in inputs if (int(d['size']) > 0)])

            # step 6: make up the command to download and flash and execute it
            # Need to grab or keep the chooses from file list selection and target list selection
            if self.sender().objectName() == 'chooseSelection':
                _logger.warn('{}: selected choices: {}'.format(self.objectName(), inputs))
                self.mPick.update(inputs)
                # extract URL and Target
                self.__getUrlStorageFromPick(inputs)
                # reset the progress bar
                self.progress.emit(0)
                # if has URL and Target, then send command to download and flash
                if self.mFileUrl and self.mTgtStorage:
                    self.__checkBeforeFlash()
                else:
                    # prompt error message for incorrectly chosen URL and Storage selection
                    self.sendError({'NoSelection': True, 'ask': 'continue'})
        else:
            # prompt error message for trying to interrupt flashing with other user inputs
            if self.sender().objectName() != 'scanNetwork':
                self.sendError({'NoInterrupt': True, 'ask': 'continue'})

    def __getUrlStorageFromPick(self, pick):
        filteredAttr = []
        urls = []
        # use picked items from lstWgtSelection to find the download URL
        # from filtered subset of the original download file list
        for disp in pick['display']:
            filteredAttr.clear()
            filteredAttr.append(disp)
            filteredAttr.extend(v for k, v in pick.items() if (v is not None and k != 'storage' and k != 'display'))
            filteredList = self._findSubset(filteredAttr, self.mFileList)
            # remove duplicate urls from filteredList
            for f in filteredList:
                if len(urls):
                    for l in urls:
                        if not (f['os'] == l['os'] and f['ver'] == l['ver'] and f['board'] == l['board'] and f['display'] == l['display'] and f['size'] == l['size']):
                            urls.append(f)
                else:
                    urls.append(f)

        # if we have an unique filtered file list, get the file url and storage
        if len(urls):
            self.mFileUrl = urls[0]['url'][:]

        # when there are OS images that run on different display panel sizes
        # specifically edms, choose one that matches the board
        if len(urls) > 1:
            # match the display size from board name
            brd = self._findChildWidget('lblBaseboard').text().lower()
            for item in urls:
                if '0700' in brd and '070' in item['url']:
                    self.mFileUrl = item['url'][:]
                    break
                elif '1000' in brd and '101' in item['url']:
                    self.mFileUrl = item['url'][:]
                    break
                elif '10-inch' in brd and '101' in item['url']:
                    self.mFileUrl = item['url'][:]
                    break
                elif '15-inch' in brd and '150' in item['url']:
                    self.mFileUrl = item['url'][:]
                    break

        self.mTgtStorage = pick['storage'][:]
        _logger.warn('{}: found URL: {}, STORAGE: {}'.format(self.objectName(), self.mFileUrl, self.mTgtStorage))

    def parseResult(self, results):
        # Start a timer to query results every 1 second
        self.mResults.update(results)

        if 'cmd' in results and results['cmd'] == 'info' and results['target'] == 'mem' and results['status'] == 'success':
            self.mTotalMem = int(results['total'])

        # ignore downloadImage on serial msger entirely
        elif 'cmd' in results and results['cmd'] == 'download' and 'status' in results and \
            'msger_type' in results and results['msger_type'] == 'dbus':
            if results['status'] == 'processing':
                if self.mTimerId is None:
                    self.mTimerId = self.startTimer(1000) # 1000 ms
                self.mFlashFlag = True
            else:
                # stop flash job either success or failure
                if self.mTimerId:
                    self.killTimer(self.mTimerId)
                self.mFlashFlag = False

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        _logger.debug('{}: validate results: {}'.format(self.objectName(), self.mResults))

        # if download and flash is successful, emit success signal to go to next stage
        if isinstance(self.mResults, dict) and self.mResults['cmd'] == 'download' and 'status' in self.mResults:
            if self.mResults['status'] == 'success' and int(self.mResults['total_uncompressed']) == int(self.mResults['bytes_written']):
                # succeed programming the eMMC
                self.progress.emit(100)
                self.mLblRemain.setText('Remaining Time: 00:00')
                self.mLblDownloadFlash.setText('')
                self.mPick.update({'url': self.mFileUrl, 'flashed': True, 'bytes_written': int(self.mResults['bytes_written'])})
                _logger.debug('{}: successfully flashed to emmc and emit signal: {}'.format(self.objectName(), self.mPick))
                self.success.emit(self.mPick)
                self.sendError({'Show': False})
            else:
                # succeed but not all bytes written, something wrong with network connection
                # or failed programming the eMMC
                self.mLblRemain.setText('Remaining Time: --:--')
                self.mLblDownloadFlash.setText('')
                self.mPick.update({'url': self.mFileUrl, 'flashed': False, 'total_uncompressed': int(self.mResults['total_uncompressed']), 'bytes_written': int(self.mResults['bytes_written'])})
                _logger.debug('{}: emit signal: {}'.format(self.objectName(), self.mPick))
                self.sendError({'NoDownload': True, 'ask': 'alternative'})
                if not self.mAlternativeFlag:
                    self.success.emit(self.mPick)

    def _updateDisplay(self):
        # show and hide some Gui elements
        self.mLstWgtSelection.setDisabled(True)
        self._findChildWidget('btnFlash').hide()
        self._findChildWidget('progressBarStatus').show()
        self.mLblRemain.show()
        self.mLblDownloadFlash.setStyleSheet('color: red; font-weight: bold;')
        self.mLblDownloadFlash.setText('Please do not power off the device')
        self.mLblDownloadFlash.show()
        self._findChildWidget('lblInstruction').setText('Downloading and flashing...')

    def timerEvent(self, event):
        # query the processing result from server
        self._queryResult()

    def __setAlternativeServer(self):
        _logger.debug('{}: original Url: {}'.format(self.objectName(), self.mFileUrl))
        alives = [host for host in self.mHosts if ('alive' in host and host['alive'])]
        for (idx, host) in enumerate(alives, start=0):
            if host['name'] in self.mFileUrl:
                orghost = alives.pop(idx)
        _logger.debug('{}: remaining alive-hosts:{}'.format(self.objectName(), alives))
        if len(alives) > 0:
            # replace remote hosts
            if (alives[0]['protocol'] in self.mDefaultPorts.keys() and self.mDefaultPorts[alives[0]['protocol']] == alives[0]['port']):
                # alternative host using protocol's standard port
                if (orghost['protocol'] in self.mDefaultPorts.keys() and self.mDefaultPorts[orghost['protocol']] == orghost['port']):
                    # original host using protocol's standard port
                    self.mFileUrl = self.mFileUrl.replace('{}'.format(orghost['name']), '{}'.format(alives[0]['name']))
                else:
                    # original using non standard port
                    self.mFileUrl = self.mFileUrl.replace('{}:{}'.format(orghost['name'], orghost['port']), '{}'.format(alives[0]['name']))
            else:
                # alternative host using non standard port
                if (orghost['protocol'] in self.mDefaultPorts.keys() and self.mDefaultPorts[orghost['protocol']] == orghost['port']):
                    # original host using protocol's standard port
                    self.mFileUrl = self.mFileUrl.replace('{}'.format(orghost['name']), '{}:{}'.format(alives[0]['name'], alives[0]['port']))
                else:
                    # original using non standard port
                    self.mFileUrl = self.mFileUrl.replace('{}:{}'.format(orghost['name'], orghost['port']), '{}:{}'.format(alives[0]['name'], alives[0]['port']))
            # replace remote directory
            if (orghost['path'] in self.mFileUrl and not alives[0]['path'] in self.mFileUrl):
                self.mFileUrl = self.mFileUrl.replace('/{}/'.format(orghost['path']), '/{}/'.format(alives[0]['path']))
            _logger.debug('{}: replaced Url: {}'.format(self.objectName(), self.mFileUrl))
            return True
        return False



@QProcessSlot.registerProcessSlot('postDownload')
class postDownloadSlot(QProcessSlot):
    """
    Handles post actions after successful download and flash
    """
    progress = pyqtSignal(int)
    success = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = {}
        self.mErr = []
        self.mFlashFlag = False
        self.mAvSpeed = 0
        self.mLastWritten = 0
        self.mRemaining = 0
        self.mTimerId = None
        self.mLblRemain = None
        self.mProgressBar = None
        self.mPick = {'board': None, 'os': None, 'ver': None, 'display': None, 'storage': None, 'target': None, 'url': None}
        self.mQRIcon = None
        self.mCheckSumFlag = False
        self.mDisks = []

    def _queryResult(self, percent = 0):
        """
        A callback function acting as a slot for timer's timeout signal.
        Here we calculate the remaining time for the download and flash and update UI accordingly.
        """
        if self.mViewer:
            try:
                res = self.mViewer.queryResult(self.mConnType)
            except:
                # cannot query installerd dbus server anymore, something wrong.
                # stop the timer, and recover the rescue system
                if self.mTimerId:
                    self.killTimer(self.mTimerId)
                self._recoverRescue()
                self.sendError({'NoDbus': True, 'ask': 'reboot' if IsATargetBoard() else 'quit'})
                return
            else:
                if res == {}:
                    _logger.debug('{}: query returns nothing, set to percent passed in.'.format(self.objectName()))
                    self.progress.emit(percent)
                else:
                    if 'total_size' in res and 'bytes_written' in res:
                        smoothing = 0.005
                        lastSpeed = int(res['bytes_written']) - self.mLastWritten
                        # averageSpeed = SMOOTHING_FACTOR * lastSpeed + (1-SMOOTHING_FACTOR) * averageSpeed;
                        self.mAvSpeed = smoothing * lastSpeed + (1 - smoothing) * self.mAvSpeed
                        self.mRemaining = float((int(res['total_size']) - int(res['bytes_written'])) / self.mAvSpeed if self.mAvSpeed > 0 else 0.0001)
                        self.mLastWritten = int(res['bytes_written'])
                        _logger.debug('{}: total: {} written:{} av:{} remain: {}'.format(self.objectName(), int(res['total_size']), int(res['bytes_written']), self.mAvSpeed, self.mRemaining))
                        self.mLblRemain.setText('Remaining Time: {:02}:{:02}'.format(int(self.mRemaining / 60), int(self.mRemaining % 60)))
                        pcent = int(round(float(res['bytes_written']) / float(res['total_size']) * 100))
                        self.progress.emit(pcent)

    def _recoverRescue(self):
        # copy back the backed up /tmp/rescue.img to target eMMC
        self._findChildWidget('lblInstruction').setText('Restoring Rescue System...')
        try:
            _logger.info('{}: dd if=/tmp/rescue.img of={} bs=1M conv=notrunc,fsync'.format(self.objectName(), self.mPick['storage']))
            subprocess.check_call(['dd', 'if=/tmp/rescue.img', 'of={}'.format(self.mPick['storage']), 'bs=1M', 'conv=notrunc,fsync'])
        except subprocess.CalledProcessError as err:
            _logger.error('cmd: {} return code:{} output: {}'.format(err.cmd, err.returncode, err.output))
            raise

    def process(self, inputs):
        """
        Called by downloadImage's success signal, do post actions, i.e. get qrcode and determine whether to clear
        emmc boot partition option 1 or enable it
        """
        if self.mLblRemain is None: self.mLblRemain = self._findChildWidget('lblRemaining')
        if self.mProgressBar is None:
            self.mProgressBar = self._findChildWidget('progressBarStatus')
            if self.mProgressBar:
                self.progress.connect(self.mProgressBar.setValue)

        if self.sender().objectName() == 'downloadImage':
            # get the pick choices and target torage and url from downloadImage
            self.mPick.update(inputs)
            if 'flashed' in self.mPick:
                if self.mPick['flashed']:
                    # flash succeeded
                    _logger.warn('{}: download and flash success: generate qrcode from from URL {}, STORAGE {}'.format(self.objectName(), self.mPick['url'], self.mPick['storage']))
                    self.sendCommand({'cmd': 'qrcode', 'dl_url': self.mPick['url'], 'tgt_filename': self.mPick['storage'], 'img_filename': '/tmp/qrcode.svg'})
                else:
                    # flash failed
                    _logger.error('{}: flash failed: recover rescues system to target storage {}'.format(self.objectName(), self.mPick['storage']))
                    self._recoverRescue()

        if self.sender().objectName() == 'scanStorage' and isinstance(inputs, list):
            # parse the available storage for checking
            self.mDisks = [d for d in inputs if 'size' in d and d['size'] > 0]
            _logger.warn('{}: disks: {}'.format(self.objectName(), self.mDisks))

    def parseResult(self, results):
        self.mResults.clear()
        self.mResults.update(results)

        # Get qrcode and display
        if results['cmd'] == 'qrcode' and results['msger_type'] == 'dbus' and results['status'] == 'success':
            self.mQRIcon = True if 'svg_buffer' in results else False
            # do checksum
            self._findChildWidget('lblInstruction').setText('Perform md5 checksum on {}...'.format(self.mPick['storage']))
            _logger.warn('{}: qrcode success: do checksum for mPick: {}'.format(self.objectName(), self.mPick))
            self.sendCommand({'cmd': 'check', 'tgt_filename': '{}.md5.txt'.format(self.mPick['url'].rstrip('.xz')), 'src_filename': self.mPick['storage'], 'total_sectors': str(int(self.mPick['bytes_written']/512))})

        # for target board
        if results['cmd'] == 'check' and results['msger_type'] == 'dbus':
            if results['status'] == 'success':
                # match the received md5s
                for k, v in results.items():
                    if k in '{}.md5.txt'.format(self.mPick['url'].rstrip('.xz')):
                        md5url = v[:]
                    if k in self.mPick['storage']:
                        md5dsk = v[:]
                _logger.warn('{}: url md5:{} disk md5:{}'.format(self.objectName(), md5url, md5dsk))
                if md5url == md5dsk:
                    self.mCheckSumFlag = True
                else:
                    self.mCheckSumFlag = False
                    self.sendError({'NoChecksum': True, 'ask': 'reboot' if IsATargetBoard() else 'quit'})
            elif results['status'] == 'failure':
                # if checksum failed due to HTTP Error 404: Not Found, just fail and continue
                self.mCheckSumFlag = False
                self.sendError({'NoChecksum': True, 'ask': 'continue'}) # 'ask': 'reboot' if IsATargetBoard() else 'quit'
            # check for sdcard or emmc
            # NOTE: on PC-version, need to know storage device path of the target board
            if results['status'] == 'success' or results['status'] == 'failure':
                _logger.info('{}: check whether target storage {} is emmc'.format(self.objectName(), self.mPick['storage']))
                if self._isTargetEMMC(self.mPick['storage']):
                    self._findChildWidget('lblInstruction').setText('{} target emmc boot partition...'.format('Flash' if 'androidthings' in self.mPick['os'] else 'Clear'))
                    # 1. disable mmc boot partition 1 boot option
                    # {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'readonly', 'config_action': 'disable', 'boot_part_no': '1', 'target': self.mTgtStorage]}
                    _logger.warn('{}: issue command to enable emmc:{} boot partition with write access'.format(self.objectName(), self.mPick['storage']))
                    self.sendCommand({'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'readonly', \
                                      'config_action': 'disable', 'boot_part_no': '1', 'send_ack':'1', 'target': self.mPick['storage']})
                else:
                    if IsATargetBoard():
                        # if not emmc, don't do anything, but emit complete and reboot
                        self.sendError({'NoTgtEmmc': True, 'ask': 'reboot'})
                    else:
                        # if not emmc, on host pc, just emit complete and quit
                        self.sendError({'Complete': True, 'QRCode': self.mQRIcon, 'ask': 'quit'})

        # target emmc has been set to writable
        if results['cmd'] == 'config' and results['subcmd'] == 'mmc' and results['config_id'] == 'readonly':
            if results['status'] == 'success':
                if 'androidthings' in self.mPick['os']:
                    _logger.debug('issue command to flash androidthings emmc boot partition')
                    self.sendCommand({'cmd': 'flash', 'src_filename': 'u-boot.imx', 'tgt_filename': '{}boot0'.format(self.mPick['storage']), 'chunk_size': '524288'})
                else:
                    # 2. clear the mmc boot partition
                    # {'cmd': 'flash', 'src_filename': '/dev/zero', 'tgt_filename': self.mPick['storage'] + 'boot0'}
                    _logger.warn('issue command to clear {} boot partition'.format(self.mPick['storage']))
                    self.sendCommand({'cmd': 'flash', 'src_filename': '/dev/zero', 'tgt_filename': '{}boot0'.format(self.mPick['storage']), 'chunk_size': '524288'})
            elif results['status'] == 'failure':
                if IsATargetBoard():
                    # failed to disable mmc write boot partition option
                    self.sendError({'NoEmmcWrite': True, 'ask': 'interrupt'})

        # flashed either zero, rescue, or androidthing uboot.imx into emmc boot part
        if results['cmd'] == 'flash':
            if results['status'] == 'processing':
                _logger.warn('{}: start timer to update progressbar for clearing emmc {} boot partition'.format(self.objectName(), self.mPick['storage']))
                if self.mTimerId is None:
                    self.mTimerId = self.startTimer(1000) # 1000 ms
                self.mFlashFlag = True
            elif (results['status'] == 'success' or results['status'] == 'failure'):
                # flash job either success or failure, stop the timer
                if self.mTimerId:
                    self.killTimer(self.mTimerId)
                # do one last query result before killing the timer
                if results['status'] == 'success':
                    self._queryResult(100)
                    self.mLblRemain.setText('Remaining Time: 00:00')
                elif results['status'] == 'failure':
                    self._queryResult(0)
                    self.mLblRemain.setText('Remaining Time: --:--')
                self.mFlashFlag = False

                # handling various image flashed in postDownloads.
                if results['src_filename'] == '/tmp/rescue.img':
                    # recover rescue system success or failure
                    if results['status'] == 'success':
                        # recover rescue system success
                        self.sendError({'Restore': True, 'ask': 'reboot' if IsATargetBoard() else 'quit'})
                    else:
                        # critical error, cannot recover the boot image and also failed to download and flash
                        self.sendError({'NoFlash': True, 'ask': 'halt' if IsATargetBoard() else 'quit'})

                elif results['src_filename'] == '/dev/zero' or results['src_filename'] == 'u-boot.imx':
                    # target emmc has been flashed with zeros or androidthings bootloader, so
                    # 3. set the mmc boot partition option no matter if emmc boot partition is cleared or not
                    # {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', 'config_action': 'enable/disable', 'boot_part_no': '1', 'send_ack':'1', 'target': self.mTgtStorage}
                    _logger.debug('{}: issue command to {} emmc boot partition'.format(self.objectName(), 'enable' if 'androidthings' in self.mPick['os'] else 'disable'))
                    if IsATargetBoard(): # for target device
                        self.sendCommand({'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', \
                                      'config_action': 'enable' if 'androidthings' in self.mPick['os'] else 'disable', \
                                      'boot_part_no': '1', 'send_ack':'1', 'target': self.mPick['storage']})
                    else: # for host pc
                        if results['msger_type'] == 'serial':
                            self.sendCommand({'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', \
                                        'config_action': 'enable' if 'androidthings' in self.mPick['os'] else 'disable', \
                                        'boot_part_no': '1', 'send_ack':'1', 'target': self.mPick['storage']})

        # target emmc boot option disabled
        if results['cmd'] == 'config' and results['subcmd'] == 'mmc' and results['config_id'] == 'bootpart':
            if self.mResults['status'] == 'success':
                # Final notification, all successful, reboot
                self.sendError({'Complete': True, 'QRCode': self.mQRIcon, 'ask': 'poweroff' if IsATargetBoard() else 'quit'})
            elif self.mResults['status'] == 'failure':
                if IsATargetBoard():
                    # failed to set emmc boot option, still reboot or quit for PC-host
                    self.sendError({'NoEmmcBoot': True, 'ask': 'reboot' if IsATargetBoard() else 'quit'})

    def _isTargetEMMC(self, storage_path):
        _logger.info('{}: isTargetEMMC:\ndisks: {}\npick: {}'.format(self.objectName(), self.mDisks, self.mPick))
        for d in self.mDisks:
            # find the disk info first from storage_path
            if storage_path == d['path']:
                # use info in disk to find the correct partition size
                if 'mmc_path' in d:
                    self.mPick['storage'] = d['mmc_path'][:] if 'dev' in d['mmc_path'] else '/dev/{}'.format(d['mmc_path'])
                    self.mConnType = 'serial'
                    return True
                else:
                    if 'MMC' in d['uevent']:
                        self.mConnType = 'dbus'
                        return True
        return False

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # but when click on reboot button, the flow doesn't reach here.
        pass

    def timerEvent(self, event):
        self._queryResult()



@QProcessSlot.registerProcessSlot('processError')
class processErrorSlot(QProcessSlot):
    """
    Handles all errors
    """
    user_response = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mErrors = {}
        self.mAsk = None
        self.mDisplay = None
        self.mModal = None
        self.mMsgBox = None

    def process(self, inputs):
        """
        Called by all other procslots to handle errors
        """
        if not self.mMsgBox:
            self.mMsgBox = self._findChildWidget('msgbox')
        self.mErrors.update(inputs)
        self.mAsk = inputs['ask'] if 'ask' in inputs else None
        self.mErrors.pop('ask', None)
        self.mDisplay = inputs['Show'] if 'Show' in inputs else True
        self.mErrors.pop('Show', None)
        self.__handleError()
        self.mErrors.clear()

    def __handleError(self):
        # Display appropriate messagebox
        self.mMsgBox.clearCheckFlags()
        self.mMsgBox.clearMessage()

        if 'NoCpuForm' in self.mErrors:
            # Add NoCpuForm icon and critical notice
            self.mMsgBox.setMessage('NoCpuForm')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('{}: No CPU or Form Factor Detected!!!'.format(self.objectName()))
        if 'NoDbus' in self.mErrors:
            # add NoDbus icon
            self.mMsgBox.setMessage('NoDbus')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.critical('{}: DBus session bus or installer dbus server not available!!! {}'.format(self.objectName(), 'Retrying...' if self.mAsk is None else 'Restore Rescue System'))
        if 'NoCable' in self.mErrors and self.mErrors['NoCable']:
            # add NoCable icon
            self.mMsgBox.setMessage('NoCable')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('{}: Network cable not connected!!! Retrying...'.format(self.objectName()))
        if 'NoIface' in self.mErrors and self.mErrors['NoIface']:
            # add NoIface icon
            self.mMsgBox.setMessage('NoIface')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('{}: NIC I/F not available!!! Retrying...'.format(self.objectName()))
        if 'NoNIC' in self.mErrors and self.mErrors['NoNIC']:
            # add NoNIC icon
            self.mMsgBox.setMessage('NoNIC')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('{}: DBus session bus or installer dbus server not available!!! Retrying...'.format(self.objectName()))
        if 'NoServer' in self.mErrors and self.mErrors['NoServer']:
            # add NoServer icon
            self.mMsgBox.setMessage('NoServer')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('{}: Cannot connect to TechNexion Rescue Server!!! Retrying...'.format(self.objectName()))
        if 'NoDNS' in self.mErrors and self.mErrors['NoDNS']:
            # add NoCable icon
            self.mMsgBox.setMessage('NoDNS')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('{}: Cannot resolve domain name!!! Retrying...'.format(self.objectName()))
        if 'NoIP' in self.mErrors and self.mErrors['NoIP']:
            # add NoCable icon
            self.mMsgBox.setMessage('NoIP')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('{}: No IP address assigned!!! Retrying...'.format(self.objectName()))
        if 'NoNetwork' in self.mErrors:
            self.mMsgBox.setMessage('NoNetwork')
            _logger.warn('{}: No Network connection or No Servers available...'.format(self.objectName()))
        if 'NoSerial' in self.mErrors:
            self.mMsgBox.setMessage('NoSerial')
            _logger.warn('{}: No serial connection available...'.format(self.objectName()))
        if 'NoDLFile' in self.mErrors:
            self.mMsgBox.setMessage('NoDLFile')
            _logger.warn('{}: No matching file from TechNexion Rescue Server.'.format(self.objectName()))
        if 'NoCrawl' in self.mErrors:
            self.mMsgBox.setMessage('NoCrawl')
            _logger.warn('{}: Not all crawling of the TechNexion Rescue Service succeeded.'.format(self.objectName()))
        if 'NoLocal' in self.mErrors:
            # not critical, ignore
            self.mMsgBox.setMessage('NoLocal')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.warn('{}: No Flashable File from Local Storage.'.format(self.objectName()))
            self.mMsgBox.display(False)
            return
        if 'NoStorage' in self.mErrors:
            # error, ask to insert an SDCard
            self.mMsgBox.setMessage('NoStorage')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('{}: No Local Storage Media for installation!!! Retrying...'.format(self.objectName()))
        if 'NoPartition' in self.mErrors:
            # not critical, ignore
            self.mMsgBox.setMessage('NoPartition')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.warn('{}: No Mounted Partition Found.'.format(self.objectName()))
            self.mMsgBox.display(False)
            return
        if 'NoResource' in self.mErrors:
            self.mMsgBox.setMessage('NoResource')
            _logger.error('{}: Limited Resources on Target Board.'.format(self.objectName()))
        if 'NoSelection' in self.mErrors:
            # serious error
            self.mMsgBox.setMessage('NoSelection')
            _logger.error('{}: User selections are incorrect.'.format(self.objectName()))
        if 'NoDownload' in self.mErrors:
            # critical, but continue
            self.mMsgBox.setMessage('NoDownload')
            _logger.warn('{}: Downloading and Flashing failed!!! Retry with another server or Continue to restore Bootable Rescue System...'.format(self.objectName()))
        if 'NoAlternative' in self.mErrors:
            self.mMsgBox.setMessage('NoAlternative')
            _logger.warn('{}: No other connectable servers for download and flash...'.format(self.objectName()))
        if 'NoFlash' in self.mErrors:
            # not critical, ignore
            self.mMsgBox.setMessage('NoFlash')
            _logger.warn('{}: Flashing failed!!! Restore Bootable Rescue System...'.format(self.objectName()))
        if 'NoChecksum' in self.mErrors:
            self.mMsgBox.setMessage('NoChecksum')
            _logger.warn('{}: Checksum failed!!!'.format(self.objectName()))
        if 'NoInterrupt' in self.mErrors:
            # not critical, ignore
            self.mMsgBox.setMessage('NoInterrupt')
            _logger.warn('{}: Flashing in progress. Ignore all user inputs'.format(self.objectName()))
        if 'NoEmmcWrite' in self.mErrors:
            # emmc boot partition option error, not critical.
            self.mMsgBox.setMessage('NoEmmcWrite')
            _logger.warn('{}: Unable to set writable to emmc boot partition!!! continue...'.format(self.objectName()))
        if 'NoEmmcBoot' in self.mErrors:
            # emmc boot partition option error, not critical.
            self.mMsgBox.setMessage('NoEmmcBoot')
            _logger.warn('{}: Unable to set emmc boot options!!! continue...'.format(self.objectName()))
        if 'NoTgtEmmcCheck' in self.mErrors:
            # emmc boot partition option error, not critical.
            self.mMsgBox.setMessage('Complete')
            _logger.warn('{}: Flash complete, ignore checking target storage for emmc failed...'.format(self.objectName()))
        if 'NoTgtEmmc' in self.mErrors:
            # target is not emmc.
            self.mMsgBox.setMessage('Complete')
            _logger.warn('{}: Flash complete, ignore target storage not emmc...'.format(self.objectName()))
        if 'Update' in self.mErrors:
            self.mMsgBox.setMessage('Update')
            _logger.warn('{}: New Rescue Loader Release, please update your rescue loader...'.format(self.objectName()))
        if 'Restore' in self.mErrors:
            self.mMsgBox.setMessage('Restore')
            _logger.warn('{}: Restore complete, reboot the system into Rescue...'.format(self.objectName()))
        if 'Complete' in self.mErrors:
            # target is not emmc.
            self.mMsgBox.setMessage('Complete')
            _logger.warn('{}: Flash complete, reboot the system into new OS...'.format(self.objectName()))
        if 'SerialMode' in self.mErrors:
            self.mMsgBox.setMessage('SerialMode')
            _logger.warning('{}: Set to SerialMode for PC-Host version...'.format(self.objectName()))
        if 'SerialConnect' in self.mErrors:
            self.mMsgBox.setMessage('SerialConnect')
            _logger.warning('{}: Established serial connections to PC-Host version of rescue loader...'.format(self.objectName()))
        if 'QRCode' in self.mErrors:
            self.mMsgBox.setMessage('QRCode')
            _logger.warn('{}: Set QRCode for the download files.'.format(self.objectName()))

        # Handles prompt for user response in the dialogue box
        if self.mAsk:
            self.mMsgBox.setModal(True) # modal dialog
            if self.mAsk == 'reboot':
                self.mMsgBox.setAskButtons(self.mAsk)
                ret = self.mMsgBox.display(True)
                if ret:
                    try:
                        # reset/reboot the system
                        subprocess.check_call(['reboot'])
                    except:
                        raise
            elif self.mAsk == 'poweroff':
                self.mMsgBox.setAskButtons(self.mAsk)
                ret = self.mMsgBox.display(True)
                if ret:
                    try:
                        # power off the system
                        subprocess.check_call(['poweroff'])
                    except:
                        raise
            elif self.mAsk == 'retry':
                self.mMsgBox.setAskButtons(self.mAsk)
                ret = self.mMsgBox.display(True)
                if ret:
                    try:
                        # reset/reboot the system
                        subprocess.check_call(['systemctl', 'restart', 'guiclientd.service'])
                    except:
                        raise
            elif self.mAsk == 'interrupt':
                self.mMsgBox.setAskButtons(self.mAsk)
                ret = self.mMsgBox.display(True)
                if ret == QtGui.QDialog.Rejected:
                    try:
                        if IsATargetBoard():
                            # reset/reboot the system
                            subprocess.check_call(['systemctl', 'stop', 'guiclientd.service'])
                        else:
                            os.kill(os.getpid(), signal.SIGUSR1)
                    except:
                        raise
            elif self.mAsk == 'serial':
                self.mMsgBox.setAskButtons(self.mAsk)
                ret = self.mMsgBox.display(True)
                if ret == QtGui.QDialog.Accepted:
                    self.mErrors.update({'reject': False, 'accept': True})
                    self.__returnResponse(self.mErrors)
                elif ret == QtGui.QDialog.Rejected:
                    self.mErrors.update({'reject': True, 'accept': False})
                    self.__returnResponse(self.mErrors)
            elif self.mAsk == 'quit':
                self.mMsgBox.setAskButtons(self.mAsk)
                ret = self.mMsgBox.display(True)
                if ret:
                    # exit the GUI
                    os.kill(os.getpid(), signal.SIGUSR1)
            elif self.mAsk == 'alternative':
                self.mMsgBox.setAskButtons(self.mAsk)
                ret = self.mMsgBox.display(True)
                if ret == QtGui.QDialog.Rejected:
                    # signal with retry response to the sender process
                    self.__returnResponse({'alternative': True})
            elif self.mAsk == 'continue':
                self.mMsgBox.setAskButtons(self.mAsk)
                ret = self.mMsgBox.display(True)
        else:
            self.mMsgBox.setModal(False)
            self.mMsgBox.display(self.mDisplay) # non modal dialog

    def __returnResponse(self, response):
        try:
            self.user_response.disconnect()
            # disconnect response signal first
        except:
            _logger.debug('{}: disconnect processError success signal first'.format(self.objectName()))

        if hasattr(self.sender(), 'processSlot') and isinstance(response, dict):
            # connect signal to sender's processSlot
            self.user_response.connect(self.sender().processSlot)
            self.user_response.emit(response)
            self.user_response.disconnect()



class QWaitingIndicator(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        palette = QtGui.QPalette(self.palette())
        palette.setColor(palette.Background, QtCore.Qt.transparent)
        self.setPalette(palette)
        self.mNodeCnt = 6
        self.mNodeSize = 10
        self.mRadius = 30
        self.mInterval = 100

    def nodeCount(self):
        return self.mNodeCnt

    def setNodeCount(self, nodeCount):
        self.mNodeCnt = nodeCount if (nodeCount > 0) else 6

    def nodeSize(self):
        return self.mNodeSize

    def setNodeSize(self, pxSize):
        self.mNodeSize = pxSize if (pxSize > 0) else 10

    def radius(self):
        return self.mRadius

    def setRadius(self, pxRadius):
        self.mRadius = pxRadius if (pxRadius > 0) else 30

    def interval(self):
        return self.mInterval

    def setInterval(self, msInterval):
        self.mInterval = msInterval if (msInterval > 0) else 100

    def paintEvent(self, event):
        painter = QtGui.QPainter()
        painter.begin(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(event.rect(), QtGui.QBrush(QtGui.QColor(63, 63, 63, 0)))
        painter.setPen(QtGui.QPen(QtCore.Qt.NoPen))

        for i in range(self.mNodeCnt):
            if (self.mCounter % self.mNodeCnt) == i:
                painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 63, 63)))
            else:
                painter.setBrush(QtGui.QBrush(QtGui.QColor(63, 63, 63)))
            painter.drawEllipse(self.width() / 2 + (self.mRadius * math.cos(2 * math.pi * i / self.mNodeCnt) - 10), \
                                self.height() / 2 + (self.mRadius * math.sin(2 * math.pi * i / self.mNodeCnt) - 10), \
                                self.mNodeSize, \
                                self.mNodeSize)
        painter.end()

    def showEvent(self, event):
        if self.parent():
            self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        self.timer = self.startTimer(self.mInterval)
        self.mCounter = 0

    def hideEvent(self, event):
        self.killTimer(self.timer)
        self.window().findChild(QtGui.QWidget, 'lblInstruction').setText('Choose an OS')

    def timerEvent(self, event):
        self.mCounter += 1
        self.update() # cause re-painting



class QMessageDialog(QtGui.QDialog):
    """
    Our own customized Message Dialog to display messages in our own TN styles
    """
    def __init__(self, parent=None):
        QtGui.QDialog.__init__(self, parent, QtCore.Qt.SplashScreen) # QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)

        # set background to transparent
        palette = QtGui.QPalette(self.palette())
        palette.setColor(palette.Background, QtCore.Qt.transparent)
        self.setPalette(palette)

        # sets fonts
        font = QtGui.QFont('Lato', QtGui.QApplication.font().pointSize() * 2, QtGui.QFont.Normal)
        self.setFont(font)
        self.mIcon = None
        self.mTitle = None
        self.mContent = None
        self.mStatus = None
        self.mQRcode = None
        self.mWgtContent = None
        self.mWgtContentLayout = None
        self.mCheckFlags = {}
        self.mButtons = {'accept': QtGui.QPushButton('ok'), 'reject': QtGui.QPushButton('cancel')}
        self.mButtons['accept'].clicked.connect(self.accept)
        self.mButtons['reject'].clicked.connect(self.reject)

    def resizeEvent(self, event):
        #rect = event.rect()
        self.mRect = self.rect()

        # draw and mask round corner
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(self.rect()), 20, 20)
        mask = QtGui.QRegion(path.toFillPolygon().toPolygon())
        self.setMask(mask)

        # draw background
        palette = QtGui.QPalette(self.palette())
        # and fill it with our technexion background image
        pixmap = QtGui.QIcon(':res/images/tn_bg.svg').pixmap(QtCore.QSize(self.rect().width() * 2, self.rect().height() * 2)).scaled(QtCore.QSize(self.rect().width(), self.rect().height()), QtCore.Qt.IgnoreAspectRatio)
        brush = QtGui.QBrush(pixmap)
        palette.setBrush(QtGui.QPalette.Background, brush)
        self.setPalette(palette)

#         # Create widgets
#         self.mIcon = QtGui.QLabel()
#         self.mIcon.setAlignment(QtCore.Qt.AlignCenter)
#         self.mTitle = QtGui.QLabel()
#         self.mContent = QtGui.QLabel()
#         self.mContent.setAlignment(QtCore.Qt.AlignCenter)
#         self.mButtons = {'accept': QtGui.QPushButton('ok'), 'reject': QtGui.QPushButton('cancel'), 'done': QtGui.QPushButton('done')}
#
#         # Set dialog layout
#         # Create grid layout for the MessageDialog widget and add widgets to layout
#         self.mLayout = QtGui.QGridLayout()
#         self.mLayout.addWidget(self.mIcon, 0, 0)
#         self.mLayout.addWidget(self.mTitle, 0, 1, 1, 4)  # row, col, rowspan, colspan
#         self.mLayout.addWidget(self.mContent, 1, 0, 3, 5)  # row, col, rowspan, colspan
#         self.mLayout.addWidget(self.mButtons['accept'], 6, 4)
#         self.mLayout.addWidget(self.mButtons['reject'], 6, 3)
#         self.setLayout(self.mLayout)
#
#         # Setup button signal to Dialog default slots
#         self.mButtons['accept'].clicked.connect(self.accept)
#         self.mButtons['reject'].clicked.connect(self.reject)
#         self.mButtons['done'].clicked.connect(self.done)

    def paintEvent(self, event):
        # draw the boundary edges
        painter = QtGui.QPainter()
        painter.begin(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtCore.Qt.black, 10))
        painter.drawRoundedRect(self.mRect, 20, 20)
        # unset drawing pen
        painter.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        painter.end()

    def setButtons(self, buttons):
        self.clearButtons()
        if isinstance(buttons, dict):
            if 'accept' in buttons.keys():
                self.mButtons['accept'].setText(buttons['accept'])
                self.layout().addWidget(self.mButtons['accept'], 4, 4, 1, 2)
            if 'reject' in buttons.keys():
                self.mButtons['reject'].setText(buttons['reject'])
                self.layout().addWidget(self.mButtons['reject'], 4, 2 if 'accept' in buttons.keys() else 4, 1, 2)

    def clearButtons(self):
        for k, btn in self.mButtons.items():
            btn.setParent(None)

    def setIcon(self, icon):
        if not self.mIcon: self.mIcon = self.window().findChild(QtGui.QLabel, 'msgIcon')
        if self.mIcon and isinstance(icon, QtGui.QIcon):
            d = self.rect().height() / 8 if self.rect().height() < self.rect().width() else self.rect().width() / 8
            iconsize = QtCore.QSize(d, d)
            pix = icon.pixmap(QtCore.QSize(iconsize.width() * 2, iconsize.height() * 2)).scaled(iconsize, QtCore.Qt.IgnoreAspectRatio)
            self.mIcon.setPixmap(pix)
            #self.mIcon.setMask(pix.mask())

    def clearIcon(self):
        if not self.mIcon: self.mIcon = self.window().findChild(QtGui.QLabel, 'msgIcon')
        if self.mIcon: self.mIcon.clear()

    def setTitle(self, title):
        if not self.mTitle: self.mTitle = self.window().findChild(QtGui.QLabel, 'msgTitle')
        if self.mTitle and isinstance(title, str):
            self.mTitle.setText(title)

    def clearTitle(self):
        if not self.mTitle: self.mTitle = self.window().findChild(QtGui.QLabel, 'msgTitle')
        if self.mTitle: self.mTitle.clear()

    def setContent(self, content):
        if not self.mContent: self.mContent = self.window().findChild(QtGui.QWidget, 'msgContent')
        if self.mContent:
            if isinstance(content, str):
                self.mContent.setText(content)
            elif isinstance(content, QtGui.QIcon):
                d = self.rect().height() / 8 if self.rect().height() < self.rect().width() else self.rect().width() / 8
                iconsize = QtCore.QSize(d, d)
                pix = content.pixmap(QtCore.QSize(iconsize.width() * 2, iconsize.height() * 2)).scaled(iconsize, QtCore.Qt.KeepAspectRatio)
                self.mContent.setPixmap(pix)
                #self.mIcon.setMask(pix.mask())
            elif isinstance(content, QtGui.QPixmap):
                self.mContent.setPixmap(content)
            elif isinstance(content, QtGui.QMovie):
                self.mContent.setMovie(content)
                content.start()

    def clearContent(self):
        if not self.mContent: self.mContent = self.window().findChild(QtGui.QWidget, 'msgContent')
        if self.mContent: self.mContent.clear()

    def setQrCode(self, icon):
        if not self.mQRcode: self.mQRcode = self.window().findChild(QtGui.QWidget, 'msgQRcode')

        if self.mQRcode:
            if isinstance(icon, QtGui.QIcon):
                w1 = self.rect().height() / 4 if self.rect().height() < self.rect().width() else self.rect().width() / 4
                w2 = self.mIcon.size().height() if self.mIcon.size().height() < self.mIcon.size().width() else self.mIcon.size().width()
                d = w1 if w1 < w2 else w2
                iconsize = QtCore.QSize(d, d)
                actualsz = icon.actualSize(iconsize)
                pix = icon.pixmap(QtCore.QSize(actualsz.width() * 2, actualsz.height() * 2)).scaled(actualsz, QtCore.Qt.KeepAspectRatio)
                self.mQRcode.setPixmap(pix)

    def clearQrCode(self):
        if not self.mQRcode: self.mQRcode = self.window().findChild(QtGui.QWidget, 'msgQRcode')
        if self.mQRcode: self.mQRcode.clear()

    def setStatus(self, status):
        if not self.mStatus: self.mStatus = self.window().findChild(QtGui.QWidget, 'msgStatus')
        if self.mStatus:
            if isinstance(status, str):
                self.mStatus.setText(status)
            elif isinstance(status, QtGui.QIcon):
                d = self.rect().height() / 8 if self.rect().height() < self.rect().width() else self.rect().width() / 8
                iconsize = QtCore.QSize(d, d)
                pix = status.pixmap(QtCore.QSize(iconsize.width() * 2, iconsize.height() * 2)).scaled(iconsize, QtCore.Qt.KeepAspectRatio)
                self.mStatus.setPixmap(pix)
                #self.mIcon.setMask(pix.mask())
            elif isinstance(status, QtGui.QPixmap):
                self.mStatus.setPixmap(status)
            elif isinstance(status, QtGui.QMovie):
                self.mStatus.setMovie(status)
                status.start()

    def clearStatus(self):
        if not self.mStatus: self.mStatus = self.window().findChild(QtGui.QWidget, 'msgStatus')
        if self.mStatus: self.mStatus.clear()

    def setBackgroundIcons(self, icons):
        if not self.mWgtContent: self.mWgtContent = self.window().findChild(QtGui.QWidget, 'wgtContent')

        d = self.rect().width() / 6
        if self.mWgtContent and isinstance(icons, dict):
            for key, res in icons.items():
                lbl = None
                if key == 'NoNic':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem0') # 'msgItem0'
                elif key == 'NoIface':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem1') # 'msgItem1'
                elif key == 'NoCable':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem2') # 'msgItem2'
                elif key == 'NoIP':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem0') # 'msgItem0'
                elif key == 'NoDNS':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem1') # 'msgItem1'
                elif key == 'NoServer':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem2') # 'msgItem3'
                else:
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem0')

                if lbl:
                    lbl.setPixmap(QtGui.QIcon(res).pixmap(QtCore.QSize(d * 2, d * 2)).scaled(QtCore.QSize(d, d), QtCore.Qt.IgnoreAspectRatio))

    def clearBackgroundIcons(self):
        if not self.mWgtContent: self.mWgtContent = self.window().findChild(QtGui.QWidget, 'wgtContent')
        if self.mWgtContent and not self.mWgtContentLayout: self.mWgtContentLayout = self.mWgtContent.layout()
        if self.mWgtContentLayout:
            for index in range(self.mWgtContentLayout.count()):
                self.mWgtContentLayout.itemAt(index).widget().clear() # call QLabel 's clear

    def setCheckFlags(self, flags):
        if not self.mWgtContent: self.mWgtContent = self.window().findChild(QtGui.QWidget, 'wgtContent')
        if self.mWgtContent and not self.mWgtContentLayout: self.mWgtContentLayout = self.mWgtContent.layout()

        d = self.rect().width() / 6
        if self.mWgtContent and isinstance(flags, dict):
            self.mCheckFlags.update(flags)

            # loop all current set flags
            for key, flag in self.mCheckFlags.items():
                # setup which label to show
                lbl = None
                if key == 'NoNIC':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem0_OL') # 'msgItem0'
                elif key == 'NoIface':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem1_OL') # 'msgItem1'
                elif key == 'NoCable':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem2_OL') # 'msgItem2'
                elif key == 'NoIP':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem0_OL') # 'msgItem0'
                elif key == 'NoDNS':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem1_OL') # 'msgItem1'
                elif key == 'NoServer':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem2_OL') # 'msgItem3'
                else:
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem0_OL')

                # setup which flag icon to use
                if flag: # True or False
                    pixmap = QtGui.QIcon(':res/images/cross.svg').pixmap(QtCore.QSize(d * 2, d * 2)).scaled(QtCore.QSize(d, d), QtCore.Qt.IgnoreAspectRatio)
                else:
                    if ('NoDbus' in flags or 'NoCpuForm' in flags):
                        pixmap = None
                    else:
                        pixmap = QtGui.QIcon(':res/images/tick.svg').pixmap(QtCore.QSize(d * 2, d * 2)).scaled(QtCore.QSize(d, d), QtCore.Qt.IgnoreAspectRatio)

                # set the label pixmap
                if lbl and pixmap:
                    lbl.setPixmap(pixmap)

    def clearCheckFlags(self):
        if not self.mWgtContent: self.mWgtContent = self.window().findChild(QtGui.QWidget, 'wgtContent')
        if self.mWgtContent and not self.mWgtContentLayout: self.mWgtContentLayout = self.mWgtContent.layout()
        if self.mWgtContentLayout:
            for index in range(self.mWgtContentLayout.count()):
                # call QLabel 's clear
                self.mWgtContentLayout.itemAt(index).widget().clear()
        self.mCheckFlags.clear()

    def setMessage(self, msgtype):
        if msgtype in ['NoNIC', 'NoIface', 'NoCable']:
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
            self.setTitle("System Check")
            self.setBackgroundIcons({'NoNIC': ':res/images/no_nic.svg', \
                                     'NoIface': ':res/images/no_iface.svg', \
                                     'NoCable': ':res/images/no_cable.svg'})
            if msgtype == 'NoNIC':
                self.setStatus('No network adaptor found.')
            elif msgtype == 'NoIface':
                self.setStatus('Ethernet interface is not available.')
            elif msgtype == 'NoCable':
                self.setStatus('Please connect a network cable.')
        elif msgtype in ['NoIP', 'NoDNS', 'NoServer']:
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
            self.setTitle("System Check")
            self.setBackgroundIcons({'NoIP': ':res/images/no_ip.svg', \
                                     'NoDNS': ':res/images/no_dns.svg', \
                                     'NoServer': ':res/images/no_server.svg'}) # {'NoNIC': ':res/images/no_nic.svg'}
            if msgtype == 'NoServer':
                self.setStatus('TechNexion server is temporary unavailable, try again later.')
            elif msgtype == 'NoDNS':
                self.setStatus('Cannot resolve domain name')
            elif msgtype == 'NoIP':
                self.setStatus('No IP address assigned')
        elif msgtype == 'NoCpuForm':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
            self.setTitle("System Check")
            self.setBackgroundIcons({'NoCpuForm': ':res/images/no_cpuform.svg'})
        elif msgtype == 'NoDbus':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
            self.setTitle("System Check")
            self.setBackgroundIcons({'NoDbus': ':res/images/no_dbus.svg'})
            self.setContent("Cannot connect to Dbus installerd.service.")
        elif msgtype in ['NoStorage', 'NoLocal', 'NoPartition']:
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
            self.setTitle("System Check")
            self.setBackgroundIcons({'NoStorage': ':res/images/no_storage.svg'})
        elif msgtype == 'NoNetwork':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("System Check")
            self.setContent("Could not connect to any servers or networks.")
            if IsATargetBoard():
                self.setStatus("SERIALMODE to start, CONTINUE to skip")
        elif msgtype == 'NoSerial':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("System Check")
            self.setContent("Cannot start serial communication.")
            self.setStatus("Make sure a USB data cable is connected")
        elif msgtype == 'NoDLFile':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Server Check")
            self.setContent("Cannot find suitable image file to download from TechNexion Rescue Server.")
        elif msgtype == 'NoCrawl':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Server Check")
            self.setContent("Exploring TechNexion rescue server failed. Check connectivity to TechNexion Rescue Server.")
            self.setStatus("CONTINUE to try alternative server.")
        elif msgtype == 'NoSelection':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Input Error")
            self.setContent("Please choose a valid image file to download and an existing storage device to flash.")
        elif msgtype == 'NoResource':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Input Error")
            self.setContent("Chosen image is not suitable due to limited resource, please contact TechNexion (sales@technexion.com) for advice.")
            self.setStatus("Or choose a different image file.")
        elif msgtype == 'NoInterrupt':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Input Error")
            self.setContent("Please do not interrupt the download and flash progress.")
        elif msgtype == 'NoDownload':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
            self.setTitle("Program Check")
            self.setContent("Download and flash failed. You could\n1. retry with another server,\n2. continue to restore rescue,\n3. program with uuu method.")
            self.setStatus("uuu info: https://www.technexion.com/support/\nknowledgebase/using-uuu-to-flash-emmc/")
        elif msgtype == 'NoAlternative':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Warning")
            self.setContent("No alternative rescue servers available for download and flash.")
            self.setStatus("Click continue to restore rescue system.")
        elif msgtype == 'NoFlash':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
            self.setTitle("Program Check")
            self.setContent("Download and flash failed.\nPlease retry to flash the image again.")
        elif msgtype == 'NoChecksum':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxInformation')))
            self.setTitle("Checksum")
            self.setContent("Checksum failed")
        elif msgtype == 'NoEmmcWrite':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Warning")
            self.setContent("Cannot set writable to emmc boot partition.\nRestart rescue to try again.")
        elif msgtype == 'NoEmmcBoot':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Warning")
            self.setContent("Cannot set emmc boot options.")
        elif msgtype == 'Update':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxInformation')))
            self.setTitle("System Update")
            self.setContent("Please update to the latest release of rescue loader.")
        elif msgtype == 'Restore':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxInformation')))
            self.setTitle("Restore Complete")
            self.setContent('Please reset your board.\n(For boards with a boot jumper, set it to eMMC BOOT MODE first.)')
        elif msgtype == 'Complete':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxInformation')))
            self.setTitle("Program Complete")
            # movie = QtGui.QMovie(':/res/images/error_edm-fairy_reset.gif')
            # movie.setScaledSize(QtCore.QSize(self.rect().width() / 2, self.rect().height() / 2))
            # self.setContent(movie)
            self.setContent('Please power off and restart your board.\n(For boards with a boot jumper, set it to eMMC BOOT MODE first.)')
        elif msgtype == 'Interrupt':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxQuestion')))
            self.setTitle("Flashing images.")
            self.setContent("Do you want to stop?")
        elif msgtype == 'SerialMode':
            # special serialmode setting
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxInformation')))
            self.setTitle("Serial Communication Mode")
            self.setContent("You can run host version of rescue loader on your PC to program target board...\nMake sure to connect an USB data cable.")
            self.setStatus("SERIALMODE to start, CONTINUE to skip")
        elif msgtype == 'SerialConnect':
            # special serial communication established
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Serial Communication Mode")
            self.setContent("Please run host version of rescue loader on your PC...\nDo not reboot while programming.")
            self.setStatus("REBOOT to restart the target board.")

        if msgtype == 'QRCode':
            # special qrcode setting
            qrIcon = QtGui.QIcon('/tmp/qrcode.svg')
            self.setQrCode(qrIcon)

    def setAskButtons(self, asktype):
        self.clearButtons()
        if asktype == 'reboot':
            self.setButtons({'accept': 'REBOOT'})
        elif asktype == 'poweroff':
            self.setButtons({'accept': 'POWEROFF'})
        elif asktype == 'retry':
            self.setButtons({'accept': 'RETRY'})
        elif asktype == 'continue':
            self.setButtons({'accept': 'CONTINUE'})
        elif asktype == 'quit':
            self.setButtons({'accept': 'QUIT'})
        elif asktype == 'interrupt':
            self.setButtons({'accept': 'CONTINUE', 'reject': 'STOP'})
        elif asktype == 'serial':
            self.setButtons({'accept': 'SERIALMODE', 'reject': 'CONTINUE'})
        elif asktype == 'alternative':
            self.setButtons({'accept': 'CONTINUE', 'reject': 'RETRY'})

    def clearMessage(self):
        self.clearIcon()
        self.clearTitle()
        self.clearContent()
        self.clearStatus()
        self.clearBackgroundIcons()
        self.clearButtons()

    def exit(self):
        self.close()

    def display(self, show=True):
        self.raise_()

        if not show:
            if self.isVisible():
                self.exit()
        else:
            if self.isModal():
                _logger.debug('exec Modal')
                ret = self.exec_()
                return ret
            else:
                if not self.isVisible():
                    _logger.debug('show non-Modal')
                    self.show()
                else:
                    _logger.debug('update non-Modal')
                    self.update()