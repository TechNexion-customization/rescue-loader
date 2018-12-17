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
import subprocess
import math
import socket
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
        _logger.warning('{} metaobject signature: {}'.format(qobj, metaobject.method(i).signature()))

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
    if isinstance(qContainer, QtGui.QListWidget):
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
                elif 'os' in row:
                    resName = ":/res/images/os_{}.svg".format(row['os'].lower())
                    item.setToolTip(row['os'].lower())
                elif 'board' in row:
                    #update the VERSION within the svg resources byte array, and draw the svg
                    resName = ":/res/images/board_{}.svg".format(row['board'].lower())
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

    elif isinstance(qContainer, QtGui.QTableWidget):
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

    elif isinstance(qContainer, QtGui.QTreeWidget):
        # TODO: Add support for insert into a treeWidget
        return False

    elif isinstance(qContainer, QtGui.QGroupBox):
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
                if row['os'].lower() == 'android':
                    radioItem.setIcon(QtGui.QIcon(QtGui.QPixmap(":/res/images/android.png")))
                elif row['os'].lower() == 'ubuntu':
                    radioItem.setIcon(QtGui.QIcon(QtGui.QPixmap(":/res/images/ubuntu.png")))
                elif row['os'].lower() == 'yocto':
                    radioItem.setIcon(QtGui.QIcon(QtGui.QPixmap(":/res/images/yocto.png")))
            layoutBox.addWidget(radioItem)
        if qContainer.layout() is None: qContainer.setLayout(layoutBox)

    elif isinstance(qContainer, QtGui.QGraphicsView):

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
                if row['os'].lower() == 'android':
                    resName = ":/res/images/android.png"
                elif row['os'].lower() == 'ubuntu':
                    resName = ":/res/images/ubuntu.png"
                elif row['os'].lower() == 'yocto':
                    resName = ":/res/images/yocto.png"
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

    def sendCommand(self, cmd):
        self.mTotalReq += 1
        self.mCmdEv.wait(0)
        self.mCmdEv.clear()
        self.mCmds.append(cmd)
        self.mMsgs.append(dict(cmd))
        self.mCmdEv.set()
        _logger.warn("{} queue cmd request: {} remaining cmds: {}".format(self.objectName(), self.mCmds[-1], len(self.mCmds)))
        self.request.emit(cmd)

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
        if self.mViewer is None and isinstance(inputs, dict) and 'viewer' in inputs:
            # this bit handles guiviewer's __emitInitSignal(),
            # i.e. root widget's initialised.emit() signal passing {'viewer': self} to all defined QProcessSlots
            # we are trying to keep QProcessSlot as generic as possible, i.e. remove dependency of viewer element
            # in the constructor, and only connect to viewer's request as necessary
            try:
                self.request.disconnect()
                # disconnect request signal first
            except:
                _logger.debug("disconnect request signal first")

            self.mViewer = inputs['viewer']
            self.request.connect(self.mViewer.request)
            _logger.debug("initialised: Setup {}.request signal to GuiViewer.request()\n".format(self.objectName(), self.sender().objectName()))
        _logger.debug('{} - sender: {} inputs: {}'.format(self.objectName(), self.sender().objectName(), inputs))
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
        self.parseResult(results)
        if ret and len(self.mCmds) == 0:
            _logger.warn('{} Requests Completed, emit finish signal to validate results'.format(self.objectName()))
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
                        _logger.warn('{} cmd: {}, msger id: {}, total remove: {}, total req: {}, total_mgrs: {}, count: {}, update mgr list: {}'.format(self.objectName(), results['cmd'], results['msger_id'], self.mTotalRemove, self.mTotalReq, results['total_mgrs'], count, self.mMsgs))
                        # if total messengers for the particular command is the same as total_mgrs then remove it
                        if count == int(results['total_mgrs']):
                            remove = i
                ret = True
                break
        if remove is not None:
            _logger.warn("{} remove returned request: {} remaining cmds: {}".format(self.objectName(), self.mMsgs[remove], len(self.mCmds) - 1))
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



@QProcessSlot.registerProcessSlot('detectDevice')
class detectDeviceSlot(QProcessSlot):
    """
    Handles detecting target device CPU and Form Factor information
    """
    success = pyqtSignal(str)
    fail = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = {}
        self.mCpu = None
        self.mForm = None
        self.mBaseboard = None
        # use QtNetwork NAMger to send a request to technexion's rescue server
        # when the request is finished, NAMger will signal its "finish" signal
        # which calls back to self._urlResponse() with reply
        # for checking network connectivity
        self.mNetMgr = QtNetwork.QNetworkAccessManager()
        # setup callback slot to self._networkResponse() for QtNetwork's NAMgr finish signal
        self.mNetMgr.finished.connect(self._urlResponse)
        self.mErr = {'NoIface': False, 'NoCable': False, 'NoServer': False}
        self.mSentFlag = False
        self.mIP = None
        self.mNICName = None

    def process(self, inputs = None):
        """
        Handle detect device callback slot
        """
        QtCore.QTimer.singleShot(1000, self.__checkDbus)

    def __checkCpuForm(self):
        self.sendCommand({'cmd': 'info', 'target': 'som'})

    def __checkDbus(self):
        """
        Check if DBus is working on the running system
        """
        if self.mViewer and hasattr(self.mViewer, 'checkDbusConn'):
            if self.mViewer.checkDbusConn():
                self.__checkCpuForm()
            else:
                self.fail.emit({'NoDbus': True})
                QtCore.QTimer.singleShot(1000, self.__checkDbus)

    def parseResult(self, results):
        """
        Handle returned SOM infor from DBus or Serial messenger
        Handle returned nic ifname and ip
        Handle returned detect network device results from DBus server
        """
        if 'subcmd' in results and results['subcmd'] == 'nic':
            _logger.warn('subcmd: nic, parse result: {}'.format(results))
            if 'status' in results and results['status'] == 'success':
                if 'msger_type' in results and results['msger_type'] == 'dbus':
                    if 'config_id' in results and results['config_id'] == 'ip':
                        self.mIP = results['ip']
                    elif 'config_id' in results and results['config_id'] == 'ifconf':
                        if 'iflist' in results and isinstance(results['iflist'], dict):
                            for k, v in results['iflist'].items():
                                if v == self.mIP:
                                    self.mNICName = k
                                    _logger.warn('found ifname: {} ip: {}'.format(k, v))
                    elif 'config_id' in results and results['config_id'] == 'ifflags':
                        if 'state' in results and 'flags' in results:
                            # a. Check whether NIC hardware available (do we have mac?)
                            #if 'LOWER_UP' in results['state']:
                            # b. Check NIC connection is up (flag says IFF_UP?)
                            if 'UP' in results['state']:
                                # c. Check NIC connection is running (flag says IFF_RUNNING?)
                                if 'RUNNING' in results['state']:
                                    # d. when all is running, check to see if we can connect to our rescue server.
                                    self.mErr.update({'NoIface': False, 'NoCable': False})
                                    self.__hasValidNetworkConnectivity()
                                    return
                                else:
                                    self.mErr.update({'NoCable': True, 'NoServer': True})
                            else:
                                self.mErr.update({'NoIface': True, 'NoCable': True, 'NoServer': True})
                            #else:
                            #    self.mErr.update({'NoNIC': True})
                            self.fail.emit(self.mErr)
                            self.mSentFlag = False
                            QtCore.QTimer.singleShot(1000, self.__checkNetwork)
            return

        if 'cmd' in results and results['cmd'] == 'info' and 'found_match' in results and \
           'status' in results and results['status'] == 'success':
            self.mForm, self.mCpu, self.mBaseboard = results['found_match'].split(',')
            if self.mCpu.find('-') != -1: self.mCpu = self.mCpu.split('-',1)[0]
            #if 'pico' in self.mForm.lower(): self._findChildWidget('lblBaseboard').hide()
            self._findChildWidget('lblCpu').setText(self.mCpu)
            self._findChildWidget('lblForm').setText(self.mForm)
            self._findChildWidget('lblBaseboard').setText(self.mBaseboard)
            # start the timer to check for network connection every 1 second
            self.__checkNetwork()

        self.mResults.update(results)

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # Check for available cpu anf form factor
        if 'cmd' in self.mResults and self.mResults['cmd'] == 'info' and \
           'found_match' not in self.mResults and \
           'status' in self.mResults and self.mResults['status'] == 'failure':
            self.mErr.update({'NoCpuForm': True, 'ask': 'reboot'})
            self.fail.emit(self.mErr)

        if 'found_match' in self.mResults and 'status' in self.mResults and self.mResults['status'] == 'success' and \
           'NoError' in self.mErr and self.mErr['NoError']:
            # tell the processError to display with no icons specified, i.e. hide
            if not self.mSentFlag:
                _logger.warning('Success and emit: {} {} ({})'.format(self.mCpu, self.mForm, self.mBaseboard))
                self.success.emit('{} {}\n'.format(self.mCpu, self.mForm, self.mBaseboard))
                self.fail.emit({'NoError': True})
                self.mSentFlag = True

    def __checkNetwork(self):
        # Check for networks, which means sending commands to installerd.service to request for network status
        # send request to installerd.service to request for network status.
        _logger.debug('send request to installerd to query network status...')
        if self.mNICName:
            self.sendCommand({'cmd': 'config', 'subcmd': 'nic', 'config_id': 'ifflags', 'config_action': 'get', 'target': self.mNICName})
        else:
            # didn't get nic iface name, so query nic iface name first, then queue another timer to do __checkNetwork
            self.sendCommand({'cmd': 'config', 'subcmd': 'nic', 'config_id': 'ip', 'config_action': 'get', 'target': 'any'})
            self.sendCommand({'cmd': 'config', 'subcmd': 'nic', 'config_id': 'ifconf', 'config_action': 'get', 'target': 'any'})
            QtCore.QTimer.singleShot(1000, self.__checkNetwork)

    def __hasValidNetworkConnectivity(self):
        _logger.debug('check whether we have connectivity to server...')
        url = 'http://rescue.technexion.net'
        req = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
        self.mNetMgr.get(req)

    def _urlResponse(self, reply):
        # Check whether network connection is active and can connect to our rescue server
        if hasattr(reply, 'error') and reply.error() != QtNetwork.QNetworkReply.NoError:
            _logger.error("Network Access Manager Error occured: {}, {}".format(reply.error(), reply.errorString()))
            # the system cannot connect to our rescue server
            self.mErr.update({'NoServer': True})
            self.fail.emit(self.mErr)
            _logger.error('TechNexion rescue server not available!!! Retrying...')
            self.mSentFlag = False
            QtCore.QTimer.singleShot(1000, self.__hasValidNetworkConnectivity)
            return
        else:
            self.mErr.update({'NoIface': False, 'NoCable': False, 'NoServer': False, 'NoError': True})
            self.fail.emit(self.mErr)
        self.mSentFlag = False
        self.finish.emit()



@QProcessSlot.registerProcessSlot('crawlWeb')
class crawlWebSlot(QProcessSlot):
    """
    Potentially the Crawling Mechanism is done in a long process thread.
    If the long process is needed, it could possibly be done using QThread in Qt.
    """
    success = pyqtSignal(object) # QtGui.PyQt_PyObject)
    fail = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mInputs = {}
        self.mResults = []
        self.mTimerId = None

    def process(self, inputs):
        """
        Handle crawlWeb process slot (signalled by initialized signal)
        """
        if self.sender().objectName() == 'scanStorage':
            # setup rescue server and location if there isn't any
            if 'location' not in inputs:
                self.mInputs.update({'location': '/'})
            if 'target' not in inputs:
                self.mInputs.update({'target': 'http://rescue.technexion.net'})

            _logger.debug('start the crawl process: {}'.format(self.mInputs))
            # start the crawl process
            self.mTimerId = self.startTimer(120000) # 2m
            self._findChildWidget('waitingIndicator').show()
            self.__crawlUrl(self.mInputs) # e.g. /pico-imx7/pi-070/

    def __crawlUrl(self, inputs):
        params = {}
        params.update(inputs)
        _logger.debug('crawl request: {}'.format({'cmd': 'info', 'target': params['target'], 'location': params['location']}))
        self.sendCommand({'cmd': 'info', 'target': params['target'], 'location': params['location']})

    def parseResult(self, results):
        #print('crawlWeb result: {}'.format(results))
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
                form, cpu, board, display, fname = self.__parseSOMInfo(results['location'])
                # extract the os and ver number from the extracted filename of the XZ file
                os, ver, extra = self.__parseFilename(fname.rstrip('.xz'))
                # make up the XZ file URL
                url = results['target'] + '/rescue' + results['location']
                # add {cpu, form, board, display, os, ver, size(uncompsize), url, extra}
                self.mResults.append({'cpu': cpu, 'form': form, 'board': board, 'display': display, 'os': os, 'ver': ver, 'size': uncompsize, 'url': url, 'extra': extra})

            elif 'file_list' in results:
                # recursively request into the rescue server directories to find XZ files
                parsedList = self.__parseWebList(results)
                if len(parsedList) > 0 and isinstance(parsedList, list):
                    for item in parsedList:
                        if item[1].endswith('/'):
                            pobj = self.__checkUrl(item[2])
                            if pobj is not None:
                                _logger.debug('internet item path: {}'.format(pobj.path))
                                self.__crawlUrl({'cmd': results['cmd'], 'target':'http://rescue.technexion.net', 'location':pobj.path.replace('/rescue/', '/')})
                        elif item[1].endswith('.xz'):
                            # match against the target device, and send request to obtain uncompressed size
                            _logger.debug('internet xzfile path: {} {} {}'.format(item[1], item[2], item[2].split('/rescue/',1)))
                            if self.__matchDevice(item[2].split('/rescue/', 1)[1]):
                                self.__crawlUrl({'cmd': results['cmd'], 'target':'http://rescue.technexion.net', 'location': '/' + item[2].split('/rescue/', 1)[1]})
                _logger.debug('Crawling url {} to find suitable xz file.\n'.format(results['location']))

        # Emit our own finished signal, because network check will cause a premature finish.emit()
        if len(self.mCmds) == 0:
            self.finish.emit()

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
        # step 2: find menu items that matches as cpu, form, but not baseboard
        cpu = self._findChildWidget('lblCpu').text().lower()
        form = self._findChildWidget('lblForm').text().lower()
        baseboard = self._findChildWidget('lblBaseboard').text().lower()
        if cpu in filename.lower() and form in filename.lower():
            # exact match of cpu in the filename, including imx6ul, imx6ull
            return True
        else:
            if cpu.lower() == 'imx6ul' or cpu.lower() == 'imx6ull':
                return False
            if cpu[0:4] in filename.lower():
                if form.lower() in filename.lower():
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
            _logger.debug('crawlWeb result: {}\n'.format(self.mResults))
            # if found suitable xz files, send them on to the next process slot
            self.success.emit(self.mResults)
            self.fail.emit({'NoError': True})
        else:
            # Did not find any suitable xz file
            self.fail.emit({'NoDLFile': False, 'ask': 'retry'})

    # FIXME: If we do not get reponses from all the requests to each URL \
    #        after 2 min, we should also issue an error
    def timerEvent(self, event):
        if self.mTotalReq == self.mTotalRemove:
            _logger.info('crawlWeb receive all request/response')
        else:
            self.fail.emit({'NoCrawl': False, 'ask': 'continue'})
            _logger.info('crawlWeb receive some request/response')
        self.killTimer(self.mTimerId)



@QProcessSlot.registerProcessSlot('crawlLocalfs')
class crawlLocalfsSlot(QProcessSlot):
    """
    Potentially the Crawling Mechanism is done in a long process thread.
    If the long process is needed, it could possibly be done using QThread in Qt.
    """
    success = pyqtSignal(object) # QtGui.PyQt_PyObject
    fail = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = []

    def process(self, inputs):
        """
        Handle crawling xz files from inputs, i.e. lists of mount points
        """
        if self.sender().objectName() == 'scanPartition':
            mount_points = []
            # parse the returned partition results to find mount points
            if isinstance(inputs, dict):
                for k, v in inputs.items():
                    if isinstance(v, dict) and 'mount_point' in v:
                        if 'mount_point' in v and v['mount_point'] != 'None':
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
                    _logger.debug('crawl localfs: {}'.format({'cmd': 'info', 'target': params['target'], 'location': params['location']}))
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
                    _logger.warning("skip parsing {} to extract form, cpu, board, display, os, and version info.".format(fname))

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        if isinstance(self.mResults, list) and len(self.mResults):
            self._findChildWidget('waitingIndicator').hide()
            _logger.debug('validateResult: crawlLocalfs result: {}\n'.format(self.mResults))
            # if found suitable xz files, send them on to the next process slot
            self.success.emit(self.mResults)
            self.fail.emit({'NoError': True})
            return
        else:
            # Did not find any suitable xz file on mounted partitions
            self.fail.emit({'NoLocal': True})

    def __parseProp(self, filename):
        # '{}-{}_{}-{}_{}-{}{}.xz' => 'form' 'cpu', 'board', 'display', 'os', {'ver', 'extra'}
        p = re.compile('(\w+)[_|-](\w+)[_|-](\w+)[_|-](\w+)[_|-](\w+)[_|-](.+)\.xz', re.IGNORECASE)
        m = p.match(filename)
        if m:
            return m.groups()



@QProcessSlot.registerProcessSlot('scanStorage')
class scanStorageSlot(QProcessSlot):
    """
    Handle scanStorage callback slot
    """
    success = pyqtSignal(object) # QtGui.PyQt_PyObject
    fail = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mControllers = []
        self.mResults = []
        self.mTimerId = None
        self.mFlag = False

    def process(self, inputs = None):
        """
        step 4: request for list of targets storage device
        """
        if self.sender().objectName() == 'detectDevice':
            if not self.mFlag:
                self.mFlag = True
                self.__detectStorage()

    def __detectStorage(self):
        _logger.debug('scan storage info: {}'.format({'cmd': 'info', 'target': 'emmc', 'location': 'controller'}))
        self.sendCommand({'cmd': 'info', 'target': 'emmc', 'location': 'controller'})

    def parseResult(self, results):
        def parse_target_list(res, attrs):
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

        # query emmc disk if query emmc controller successful
        if 'cmd' in results and results['cmd'] == 'info' and \
           'target' in results and results['target'] == 'emmc' and \
           'location' in results and results['location'] == 'controller' and \
           'status' in results and (results['status'] == 'success' or results['status'] == 'failure'):
            self.mControllers = parse_target_list(results, ['device_node', 'device_type', 'serial', 'uevent'])
            _logger.debug('scan emmc info: {}'.format({'cmd': 'info', 'target': 'emmc', 'location': 'disk'}))
            self.sendCommand({'cmd': 'info', 'target': 'emmc', 'location': 'disk'})

        # query hd disk if query emmc disk successful
        if 'cmd' in results and results['cmd'] == 'info' and \
           'target' in results and results['target'] == 'emmc' and \
           'location' in results and results['location'] == 'disk' and \
           'status' in results and (results['status'] == 'success' or results['status'] == 'failure'):
            _logger.debug('scan hd info: {}'.format({'cmd': 'info', 'target': 'hd', 'location': 'disk'}))
            self.sendCommand({'cmd': 'info', 'target': 'hd', 'location': 'disk'})

        # step 5: parse a list of target devices for user to choose
        if 'cmd' in results and results['cmd'] == 'info' and \
            'target' in results and (results['target'] == 'emmc' or results['target'] == 'hd') and \
            'location' in results and results['location'] == 'disk' and \
            'status' in results and results['status'] == "success" and 'msger_type' in results:
            listTarget = parse_target_list(results, ['device_node', 'device_type', 'serial', 'id_bus', 'size', 'uevent'])
            if len(listTarget):
                for tgt in listTarget:
                    # 'name', 'node path', 'disk size'
                    _logger.warn('found target storage device: {}'.format(tgt))
                    self.mResults.append({'name': tgt[0], \
                                          'path': tgt[1]['device_node'], \
                                          'device_type': tgt[1]['device_type'], \
                                          'conntype': results['msger_type'], \
                                          'size':int(tgt[1]['size']) * 512, \
                                          'id_bus': tgt[1]['id_bus'] if 'id_bus' in tgt[1] else None, \
                                          'uevent': tgt[1]['uevent'] if 'uevent' in tgt[1] else None})
                    # find matching serial from the controllers
                    for ctrl in self.mControllers:
                        if tgt[1]['serial'] == ctrl[1]['serial']:
                            self.mResults[-1].update({'uevent': ctrl[1]['uevent']})

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # Check for available storage disk in the self.mResult list
        if isinstance(self.mResults, list) and len(self.mResults):
            # emit results to the next QProcessSlot, i.e. chooseStorage, and crawlLocalfs
            self.success.emit(self.mResults)
            self.fail.emit({'NoError': True})
        else:
            # no suitable storage found, keep probing after click continue from the dialogbox
            _logger.error('Cannot find available storage!!! Insert a sdcard...')
            self.fail.emit({'NoStorage': True})
            QtCore.QTimer.singleShot(1000, self.__detectStorage)



@QProcessSlot.registerProcessSlot('scanPartition')
class scanPartitionSlot(QProcessSlot):
    """
    Search the mounted points from exiting partitions in the system
    """
    success = pyqtSignal(object) # QtGui.PyQt_PyObject
    fail = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = {}
        self.mFlag = False

    def process(self, inputs):
        """
        issue commands to find partitions with mount points
        """
        if self.sender().objectName() == 'detectDevice':
            if not self.mFlag:
                self.mFlag = True
                self.__detectMountedPartition()

    def __detectMountedPartition(self):
        self.sendCommand({'cmd': 'info', 'target': 'emmc', 'location': 'partition'})

    def parseResult(self, results):
        if 'cmd' in results and results['cmd'] == 'info' and \
           'target' in results and results['target'] == 'emmc' and \
           'location' in results and results['location'] == 'partition' and \
           'status' in results and (results['status'] == 'success' or results['status'] == 'failure'):
            self.sendCommand({'cmd': 'info', 'target': 'hd', 'location': 'partition'})

        # parse the returned partitions and send them off
        if isinstance(results, dict) and 'status' in results and results['status'] == "success":
            for k, v in results.items():
                if isinstance(v, dict) and 'device_type' in v.keys() and v['device_type'] == 'partition':
                    self.mResults.update({k: v})

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # Signal available partitions in the self.mResults dictionary
        if isinstance(self.mResults, dict) and len(self.mResults):
            # emit results to the next QProcessSlot, i.e. crawlLocalfs
            self.success.emit(self.mResults)
            self.fail.emit({'NoError': True})
        else:
            self.fail.emit({'NoPartition': True})
            # No need to scan for mounted partition again
            # QtCore.QTimer.singleShot(1000, self.__detectMountedPartition)



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
        self.mResults.extend([d for d in listOfFileDict if (int(d['size']) > 0)])
        _logger.info('list of storage/xz devices/files: {}'.format(self.mResults))

    def _extractUIList(self):
        """
        To be overridden
        """
        pass

    def _filterList(self, key, pick, parsedUIList, origList):

        def enableList(key, parsedUIList, enabledSet):
            _logger.info('enable following ui: {}'.format(enabledSet))
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
        _logger.debug('{}: Enbled Set: {}'.format(self.Name(), enabledSet))
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
    fail = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mOSUIList = None
        self.mLstWgtOS = None
        self.mLstWgtSelection =None
        self.mUserData = None

    def process(self, inputs):
        # update the UI element for later use
        if self.mLstWgtOS is None: self.mLstWgtOS = self._findChildWidget('lstWgtOS')
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')

        if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
            # parse the download files into selectable options, i.e. board, OS, ver, display
            self._parseResultList(inputs)
            self._extractUIList()
            _insertToContainer(self.mOSUIList, self.mLstWgtOS, None)

        if self.sender().objectName() == 'chooseOS' or self.sender().objectName() == 'chooseBoard' or \
           self.sender().objectName() == 'chooseDisplay' or self.sender().objectName() == 'chooseStorage' or \
           self.sender().objectName() == 'chooseSelection':
            # chooseOS or chooseBoard or chooseDisplay or chooseStorage, then sends a picked choice
            if isinstance(inputs, dict) and all(field in inputs for field in ['board', 'os', 'ver', 'display', 'storage']):
                _logger.info('self:{}, sender:{}, old pick:{}, new pick:{}'.format(self.objectName(), self.sender().objectName(), self.mPick, inputs))
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
                self.mPick['ver'] = self.__extractLatestVersion()
                # add to lstWgtSelection if not disabled
                if not self.mUserData['disable']:
                    item = QtGui.QListWidgetItem(inputs)
                    self.mUserData['ver'] = self.mPick['ver']
                    item.setData(QtCore.Qt.UserRole, self.mUserData)
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
        self.mOSNames = list(set(dlfile['os'] for dlfile in self.mResults if ('os' in dlfile)))
        self.mVerList = []
        for d in [{'os':dlfile['os'], 'ver':dlfile['ver']} for dlfile in self.mResults if ('os' in dlfile and 'ver' in dlfile)]:
            if all(not (d == n) for n in self.mVerList):
                self.mVerList.append(d)
        # come up with a new list to send to GUI container, i.e. QListWidget
        self.mOSUIList = list({'name': name, 'os': name, 'disable': False} for name in self.mOSNames) # if name.lower() != 'rescue')

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
                _logger.info('failed to choose a valid option')



@QProcessSlot.registerProcessSlot('chooseBoard')
class chooseBoardSlot(QChooseSlot):
    """
    Handles button click event to issue cmd to choose board
    """
    success = pyqtSignal(dict)
    fail = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mBoardUIList = None
        self.mLstWgtBoard = None
        self.mLstWgtSelection =None
        self.mUserData = None

    def process(self, inputs):
        # update the UI element for later use
        if self.mLstWgtBoard is None: self.mLstWgtBoard = self._findChildWidget('lstWgtBoard')
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')

        if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
            # parse the download files into selectable options, i.e. board, OS, ver, display
            self._parseResultList(inputs)
            self._extractUIList()
            _insertToContainer(self.mBoardUIList, self.mLstWgtBoard, None)
            if self.mBoardUIList is not None and len(self.mBoardUIList) == 1:
                self.finish.emit()

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
                _logger.info('failed to choose a valid option')



@QProcessSlot.registerProcessSlot('chooseDisplay')
class chooseDisplaySlot(QChooseSlot):
    """
    Handles button click event to issue cmd to choose display
    """
    success = pyqtSignal(dict)
    fail = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mDisplayUIList = []
        self.mLstWgtDisplay = None
        self.mLstWgtSelection =None
        self.mIfaceTypes = ['lvds', 'hdmi', 'ttl', 'vga', 'dsi', 'dpi']

    def process(self, inputs):
        # update the UI element for later use
        if self.mLstWgtDisplay is None: self.mLstWgtDisplay = self._findChildWidget('lstWgtDisplay')
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')

        if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
            # parse the download files into selectable options, i.e. board, OS, ver, display
            self._parseResultList(inputs)
            self._extractUIList()
            _insertToContainer(self.mDisplayUIList, self.mLstWgtDisplay, None)
            if self.mDisplayUIList is not None and len(self.mDisplayUIList) == 1:
                self.finish.emit()

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
        if 'pico' in self._findChildWidget('lblForm').text().lower():
            # PICO form factor display lists
            for name in self.mDisplayNames:
                if any(sz in name for sz in ['050', '070', '101', '150', 'lcd']):
                    iftype = 'ttl'
                elif any(sz in name for sz in ['mipi', 'dsi', 'dpi']):
                    if 'dsi' in name:
                        iftype = 'dsi'
                    else:
                        iftype = 'dpi'
                else:
                    for t in self.mIfaceTypes:
                        if t in name:
                            iftype = t
                            break
                lstTemp.append({'name': name, 'display': name, 'ifce_type': iftype, 'disable': False})

            # come up with a new list to send to GUI container, i.e. QListWidget
            for t in self.mIfaceTypes:
                disps = list(l['name'] for l in lstTemp if (l['ifce_type'] == t))
                if len(disps) > 0:
                    self.mDisplayUIList.append({'name': t, 'display': disps, 'ifce_type': t, 'disable': False})
        else:
            # EDM form factor display lists (1:1 relationship per baseboard)
            baseboard = self._findChildWidget('lblBaseboard').text().lower()
            if '1000' in baseboard:
                if len(self.mDisplayUIList) > 0:
                    if 'display' in self.mDisplayUIList[0] and '101' not in self.mDisplayUIList[0]['display']:
                        self.mDisplayUIList.append({'name': '101', 'display': ['101'], 'ifce_type': 'lvds', 'disable': False})
                else:
                    self.mDisplayUIList.append({'name': '101', 'display': ['101'], 'ifce_type': 'lvds', 'disable': False})
            elif '700' in baseboard:
                if len(self.mDisplayUIList) > 0:
                    if 'display' in self.mDisplayUIList[0] and '070' not in self.mDisplayUIList[0]['display']:
                        self.mDisplayUIList.append({'name': '070', 'display': ['070'], 'ifce_type': 'lvds', 'disable': False})
                else:
                    self.mDisplayUIList.append({'name': '070', 'display': ['070'], 'ifce_type': 'lvds', 'disable': False})

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
                _logger.info('failed to choose a valid option')



@QProcessSlot.registerProcessSlot('chooseStorage')
class chooseStorageSlot(QChooseSlot):
    """
    Handles button click event to issue cmd to choose board, os, and display
    """
    success = pyqtSignal(dict)
    fail = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mStorageUIList = None
        self.mLstWgtStorage = None
        self.mLstWgtSelection =None
        self.mPick = {'board': None, 'os': None, 'ver': None, 'display': None, 'storage': None}

    def process(self, inputs):
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
                #_insertToContainer(self.mStorageUIList, self.mLstWgtStorage, None)

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
                                  'disable': False} for item in self.mResults)
        _logger.debug('chooseStorage: mStorageUIList: {}'.format(self.mStorageUIList))

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
            self.fail.emit('failed to choose a valid storage to program')



@QProcessSlot.registerProcessSlot('chooseSelection')
class chooseSelectionSlot(QChooseSlot):
    """
    Handles button click event to issue cmd to handle re-choose of os, board, display, and storage
    """
    success = pyqtSignal(dict)
    chosen = pyqtSignal(dict)
    fail = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = {}
        self.mLstWgtSelection =None
        self.mLstWgtStorage = None
        self.mLstWgtOS = None
        self.mLstWgtBoard = None
        self.mLstWgtDisplay = None
        self.mUserData = None
        self.mTotalSectors = {}

    def process(self, inputs):
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
                if '{}p1'.format(self.mPick['storage']) in self.mTotalSectors.keys():
                    # issue command to copy first partition (size extract from self.mTotalSectors of /dev/mmcblkXp1 to target storage
                    _logger.warn('send flash command{}'.format({'cmd': 'flash', 'src_filename': self.mPick['storage'], 'tgt_filename': '/tmp/rescue.img', 'src_total_sectors': '{}'.format(int(self.mTotalSectors['{}p1'.format(self.mPick['storage'])]/4096)*512), 'chunk_size': '32768'}))
                    self.sendCommand({'cmd': 'flash', 'src_filename': self.mPick['storage'], 'tgt_filename': '/tmp/rescue.img', 'src_total_sectors': '{}'.format(int(self.mTotalSectors['{}p1'.format(self.mPick['storage'])]/4096)*512), 'chunk_size': '32768'})
                else:
                    # copy the first 69632 sectors(71,303,168 bytes) out first (mbr boot sector + SPL), NOTE: total sectors = 17408 because mmc blksize is 4096
                    _logger.warn('send flash command:{}'.format({'cmd': 'flash', 'src_filename': self.mPick['storage'], 'tgt_filename': '/tmp/rescue.img', 'src_total_sectors': '17408', 'chunk_size': '32768'}))
                    self.sendCommand({'cmd': 'flash', 'src_filename': self.mPick['storage'], 'tgt_filename': '/tmp/rescue.img', 'src_total_sectors': '17408', 'chunk_size': '32768'})
                self._findChildWidget('lblInstruction').setText('Backing up Rescue System...')

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

        if self.sender().objectName() == 'scanPartition':
            # figure out the partition size to backup
            if isinstance(inputs, dict):
                for k, v in inputs.items():
                    if isinstance(v, dict) and 'sys_number' in v.keys() and int(v['sys_number']) == 1 and \
                        'sys_name' in v.keys() and 'mmcblk' in v['sys_name'] and \
                        'attributes' in v.keys() and isinstance(v['attributes'], dict) and \
                        'size' in v['attributes'].keys() and 'start' in v['attributes'].keys():
                            self.mTotalSectors.update({v['device_node']: int(v['attributes']['start']) + int(v['attributes']['size']) + 8}) # add an additional block, i.e 4096/512
                            _logger.info('{} Start: {}, Size: {}, Total Sectors: {}'.format(k, int(v['attributes']['start']), int(v['attributes']['size']), self.mTotalSectors))

    def parseResult(self, results):
        # flash command complete and the results are updated/parsed here
        self.mResults.update(results)

    def validateResult(self):
        # flow comes here after self.finish.emit() - gets called or when cmd is removed from self.mCmds
        if self.mResults['status'] == 'success' and self.mResults['cmd'] == 'flash':
            # send the mPick to downloadImage procslot
            if all(p is not None for p in self.mPick if (key in self.mPick for key in ['os', 'board', 'display', 'storage'])):
                if hasattr(self._findChildWidget('downloadImage'), 'processSlot'):
                    try:
                        self.chosen.disconnect()
                        # disconnect chosen signal first
                    except:
                        _logger.debug("disconnect chosen signal first")
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
                    self._findChildWidget('lblStorageTxt').setText('eMMC')
                elif 'id_bus' in data and data['id_bus'] == 'ata':
                    self._findChildWidget('lblStorageTxt').setText('HD')
                else:
                    self._findChildWidget('lblStorageTxt').setText('SDCard')



@QProcessSlot.registerProcessSlot('downloadImage')
class downloadImageSlot(QProcessSlot):
    """
    Handles button click event to issue cmd to download and flash
    """
    progress = pyqtSignal(int)
    success = pyqtSignal(dict)
    fail = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mFileList = []
        self.mResults = {}
        self.mFileUrl = None
        self.mTgtStorage = None
        self.mFlashFlag = False
        self.mAvSpeed = 0
        self.mLastWritten = 0
        self.mRemaining = 0
        self.mTimerId = None
        self.mLblRemain = None
        self.mLstWgtSelection = None
        self.mProgressBar = None
        self.mPick = {'board': None, 'os': None, 'ver': None, 'display': None, 'storage': None}

    def _queryResult(self):
        """
        A callback function acting as a slot for timer's timeout signal.
        Here we calculate the remaining time for the download and flash and update UI accordingly.
        """
        if self.mViewer:
            try:
                res = self.mViewer.queryResult()
            except:
                _logger.warning('query result from DBus Server Failed... Recover Rescue System...')
                # cannot query installerd dbus server anymore, something wrong.
                # stop the timer, and recover the rescue system
                self.killTimer(self.mTimerId)
                # use subprocess to restor the rescue system
                # i.e. subprocess.check_call(['mmc', 'bootpart', 'enable', '0', '1', '/dev/mmcblk2'])
                try:
                    subprocess.check_call(['dd', 'if=/tmp/rescue.img', 'of={}'.format(self.mTgtStorage), 'bs=1M', 'oflag=dsync'])
                except subprocess.CalledProcessError as err:
                    _logger.error('cmd: {} return code:{} output: {}'.format(err.cmd, err.returncode, err.output))
                    raise
                self.fail.emit({'NoDbus': True, 'ask': 'reboot'})
                return
            else:
                if 'total_uncompressed' in res and 'bytes_written' in res:
                    smoothing = 0.005
                    lastSpeed = int(res['bytes_written']) - self.mLastWritten
                    # averageSpeed = SMOOTHING_FACTOR * lastSpeed + (1-SMOOTHING_FACTOR) * averageSpeed;
                    self.mAvSpeed = smoothing * lastSpeed + (1 - smoothing) * self.mAvSpeed
                    self.mRemaining = float((int(res['total_uncompressed']) - int(res['bytes_written'])) / self.mAvSpeed if self.mAvSpeed > 0 else 0.0001)
                    self.mLastWritten = int(res['bytes_written'])
                    _logger.debug('total: {} written:{} av:{} remain: {}'.format(int(res['total_uncompressed']), int(res['bytes_written']), self.mAvSpeed, self.mRemaining))
                    self.mLblRemain.setText('Remaining Time: {:02}:{:02}'.format(int(self.mRemaining / 60), int(self.mRemaining % 60)))
                    pcent = int(round(float(res['bytes_written']) / float(res['total_uncompressed']) * 100))
                    self.progress.emit(pcent)

    def process(self, inputs):
        """
        grab the dl_url and tgt_filename from the tableRescueFile and tableTargetStorage itemClicked() signals
        when signal sender is from btnFlash, issue flash command with clicked rescue file and target storage.
        """
        if self.mLblRemain is None: self.mLblRemain = self._findChildWidget('lblRemaining')
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')
        if self.mProgressBar is None:
            self.mProgressBar = self._findChildWidget('progressBarStatus')
            if self.mProgressBar:
                self.progress.connect(self.mProgressBar.setValue)

        if not self.mFlashFlag:
            # keep the available file list for lookup with a signalled self.mPick later
            if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
                self.mFileList.extend([d for d in inputs if (int(d['size']) > 0)])

            # step 6: make up the command to download and flash and execute it
            # Need to grab or keep the chooses from file list selection and target list selection
            if self.sender().objectName() == 'chooseSelection':
                _logger.warning('selected choices: {}'.format(inputs))
                self.mPick.update(inputs)
                # extract URL and Target
                self.__getUrlStorageFromPick(inputs)
                # reset the progress bar
                self.progress.emit(0)
                # if has URL and Target, then send command to download and flash
                if self.mFileUrl and self.mTgtStorage:
                    _logger.warn('download from {} and flash to {}'.format(self.mFileUrl, self.mTgtStorage))
                    if IsATargetBoard():
                        # send request to installerd
                        self.sendCommand({'cmd': 'download', 'dl_url': self.mFileUrl, 'tgt_filename': self.mTgtStorage})
                    else:
                        # send request to installerd on target board, via serial. So download to PC-host first
                        # send chunk by chunk over serial to be written.
                        self.sendCommand({'cmd': 'download', 'dl_url': self.mFileUrl, 'tgt_filename': '/tmp/targetboard.img'})

                    # show/hide GUI components
                    self._updateDisplay()
                else:
                    # prompt error message for incorrectly chosen URL and Storage selection
                    self.fail.emit({'NoSelection': True, 'ask': 'continue'})
        else:
            # prompt error message for trying to interrupt flashing with other user inputs
            if self.sender().objectName() != 'detectDevice':
                self.fail.emit({'NoInterrupt': True, 'ask': 'continue'})

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
        self.mTgtStorage = pick['storage'][:]
        _logger.warn('found URL: {}, STORAGE: {}'.format(self.mFileUrl, self.mTgtStorage))

    def parseResult(self, results):
        # step 7: parse the result in a loop until result['status'] != 'processing'
        # Start a timer to query results every 1 second
        self.mResults.update(results)
        if results['cmd'] == 'download' and results['status'] == 'processing':
            self.mTimerId = self.startTimer(1000) # 1000 ms
            self.mFlashFlag = True
        else:
            # do one last query result before killing the timer
            self._queryResult()
            # flash job either success or failure
            self.killTimer(self.mTimerId)
            self.mFlashFlag = False

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        _logger.debug('{} validateResult: {}'.format(self.objectName(), self.mResults))

        # if download and flash is successful, emit success signal to go to next stage
        if isinstance(self.mResults, dict) and self.mResults['cmd'] == 'download' and 'status' in self.mResults:
            if self.mResults['status'] == 'success':
                if 'tgt_filename' in self.mResults and self.mResults['tgt_filename'] == '/tmp/targetboard.img':
                    self.progress.emit(0)
                    self.sendCommand({'cmd': 'flash', 'src_filename': '/tmp/targetboard.img', 'tgt_filename': self.mTgtStorage })
                else:
                    self.progress.emit(100)
                    self.mLblRemain.setText('Remaining Time: 00:00')
                    self.mPick.update({'url': self.mFileUrl, 'flashed': True})
                    _logger.debug('{} emit signal: {}'.format(self.objectName(), self.mPick))
                    self.success.emit(self.mPick)
                    self.fail.emit({'NoError': True})
            elif self.mResults['status'] == 'failure':
                self.mPick.update({'url': self.mFileUrl, 'flashed': False})
                _logger.debug('{} emit signal: {}'.format(self.objectName(), self.mPick))
                self.fail.emit({'NoDownload': True, 'ask': 'continue'})
                self.success.emit(self.mPick)

    def _updateDisplay(self):
        # show and hide some Gui elements
        self.mLstWgtSelection.setDisabled(True)
        self._findChildWidget('btnFlash').hide()
        self._findChildWidget('progressBarStatus').show()
        self.mLblRemain.show()
        self._findChildWidget('lblInstruction').setText('Downloading and flashing...')

    def timerEvent(self, event):
        # query the processing result from server
        self._queryResult()



@QProcessSlot.registerProcessSlot('postDownload')
class postDownloadSlot(QProcessSlot):
    """
    Handles post actions after successful download and flash
    """
    progress = pyqtSignal(int)
    success = pyqtSignal(dict)
    fail = pyqtSignal(dict)

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
        self.mTotalSectors = {}

    def _queryResult(self):
        """
        A callback function acting as a slot for timer's timeout signal.
        Here we calculate the remaining time for the download and flash and update UI accordingly.
        """
        if self.mViewer:
            try:
                res = self.mViewer.queryResult()
            except:
                # cannot query installerd dbus server anymore, something wrong.
                # stop the timer, and recover the rescue system
                self.killTimer(self.mTimerId)
                # use subprocess to restor the rescue system
                # i.e. subprocess.check_call(['mmc', 'bootpart', 'enable', '0', '1', '/dev/mmcblk2'])
                try:
                    subprocess.check_call(['dd', 'if=/tmp/rescue.img', 'of={}'.format(self.mPick['storage']), 'bs=1M', 'oflag=dsync'])
                except subprocess.CalledProcessError as err:
                    _logger.error('cmd: {} return code:{} output: {}'.format(err.cmd, err.returncode, err.output))
                    raise
                self.fail.emit({'NoDbus': True, 'ask': 'reboot'})
                return

            if 'total_size' in res and 'bytes_written' in res:
                smoothing = 0.005
                lastSpeed = int(res['bytes_written']) - self.mLastWritten
                # averageSpeed = SMOOTHING_FACTOR * lastSpeed + (1-SMOOTHING_FACTOR) * averageSpeed;
                self.mAvSpeed = smoothing * lastSpeed + (1 - smoothing) * self.mAvSpeed
                self.mRemaining = float((int(res['total_size']) - int(res['bytes_written'])) / self.mAvSpeed if self.mAvSpeed > 0 else 0.0001)
                self.mLastWritten = int(res['bytes_written'])
                _logger.debug('total: {} written:{} av:{} remain: {}'.format(int(res['total_size']), int(res['bytes_written']), self.mAvSpeed, self.mRemaining))
                self.mLblRemain.setText('Remaining Time: {:02}:{:02}'.format(int(self.mRemaining / 60), int(self.mRemaining % 60)))
                pcent = int(round(float(res['bytes_written']) / float(res['total_size']) * 100))
                self.progress.emit(pcent)

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
                    # gen qrcode save it in /tmp/qrcode.svg and display it before reboot
                    _logger.info('flash success: generate qrcode from from URL {}, STORAGE {}'.format(self.mPick['url'], self.mPick['storage']))
                    self.sendCommand({'cmd': 'qrcode', 'dl_url': self.mPick['url'], 'tgt_filename': self.mPick['storage'], 'img_filename': '/tmp/qrcode.svg'})
                    # check for sdcard or emmc
                    _logger.info('flash success: check whether target storage {} is emmc'.format(self.mPick['storage']))
                    self.sendCommand({'cmd': 'info', 'target': 'emmc', 'location': 'controller'})
                else:
                    # flash failed
                    _logger.info('flash failed: recover rescues system to target storage {}'.format(self.mPick['storage']))
                    # copy back the first 69632 sectors - 35,651,584 bytes (mbr boot sector + SPL), 8704 because mmc blksize is 4096
                    if '{}p1'.format(self.mPick['storage']) in self.mTotalSectors.keys():
                        self.sendCommand({'cmd': 'flash', 'tgt_filename': self.mPick['storage'], 'src_filename': '/tmp/rescue.img', 'src_total_sectors': '{}'.format(int(self.mTotalSectors['{}p1'.format(self.mPick['storage'])]/4096)*512), 'chunk_size': '32768'})
                    else:
                        self.sendCommand({'cmd': 'flash', 'tgt_filename': self.mPick['storage'], 'src_filename': '/tmp/rescue.img', 'src_total_sectors': '14336', 'chunk_size': '32768'})
                    self._findChildWidget('lblInstruction').setText('Restoring Rescue System...')

        if self.sender().objectName() == 'scanPartition':
            # figure out the partition size to backup
            if isinstance(inputs, dict):
                for k, v in inputs.items():
                    if isinstance(v, dict) and 'sys_number' in v.keys() and int(v['sys_number']) == 1 and \
                        'sys_name' in v.keys() and 'mmcblk' in v['sys_name'] and \
                        'attributes' in v.keys() and isinstance(v['attributes'], dict) and \
                        'size' in v['attributes'].keys() and 'start' in v['attributes'].keys():
                            self.mTotalSectors.update({v['device_node']: int(v['attributes']['start']) + int(v['attributes']['size']) + 8}) # add an additional block, i.e 4096/512
                            _logger.info('{} Start: {}, Size: {}, Total Sectors: {}'.format(k, int(v['attributes']['start']), int(v['attributes']['size']), self.mTotalSectors))

    def parseResult(self, results):
        self.mResults.clear()
        self.mResults.update(results)

        # Get qrcode and display
        if results['cmd'] == 'qrcode' and results['status'] == 'success':
            self.mQRIcon = True if 'svg_buffer' in results else False

        # Get controller info back and determine whether target storage is emmc
        if results['cmd'] == 'info':
            if results['status'] == 'success':
                # determine whether target device is an emmc, if it is, then do the mmc boot partition clearing
                if self._isTargetEMMC(results):
                    self.progress.emit(0)
                    if 'androidthings' in self.mPick['os']:
                        self._findChildWidget('lblInstruction').setText('Flash target emmc boot partition...')
                    else:
                        self._findChildWidget('lblInstruction').setText('Clearing target emmc boot partition...')
                    # 1. disable mmc boot partition 1 boot option
                    # {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'readonly', 'config_action': 'disable', 'boot_part_no': '1', 'target': self.mTgtStorage]}
                    _logger.debug('issue command to enable emmc:{} boot partition with write access'.format(self.mPick['storage']))
                    self.sendCommand({'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'readonly', \
                                      'config_action': 'disable', 'boot_part_no': '1', 'send_ack':'1', 'target': self.mPick['storage']})
                else:
                    # if not emmc, don't do anything, but emit complete and reboot
                    self.fail.emit({'NoError': True, 'NoTgtEmmc': True, 'ask': 'reboot'})
            elif results['status'] == 'failure':
                # even if cmd 'info' to query target storage failed, still emit complete and reboot
                self.fail.emit({'NoError': True, 'NoTgtEmmcCheck': True, 'ask': 'reboot'})

        # target emmc has been set to writable
        if results['cmd'] == 'config' and results['subcmd'] == 'mmc' and results['config_id'] == 'readonly':
            if results['status'] == 'success':
                if 'androidthings' in self.mPick['os']:
                    _logger.debug('issue command to flash androidthings emmc boot partition')
                    self.sendCommand({'cmd': 'flash', 'src_filename': 'u-boot.imx', 'tgt_filename': self.mPick['storage'] + 'boot0'})
                else:
                    # 2. clear the mmc boot partition
                    # {'cmd': 'flash', 'src_filename': '/dev/zero', 'tgt_filename': self.mPick['storage'] + 'boot0'}
                    _logger.debug('issue command to clear {} boot partition'.format(self.mPick['storage']))
                    self.sendCommand({'cmd': 'flash', 'src_filename': '/dev/zero', 'tgt_filename': self.mPick['storage'] + 'boot0'})
            elif results['status'] == 'failure':
                # failed to disable mmc write boot partition option
                self.fail.emit({'NoEmmcWrite': True, 'ask': 'interrupt'})

        # target emmc boot option disabled
        if results['cmd'] == 'config' and results['subcmd'] == 'mmc' and results['config_id'] == 'bootpart':
            if self.mResults['status'] == 'success':
                # Final notification, all successful, reboot
                self.fail.emit({'NoError': True, 'Complete': True, 'QRCode': self.mQRIcon, 'ask': 'reboot'})
            elif self.mResults['status'] == 'failure':
                # failed to set emmc boot option, still reboot
                self.fail.emit({'NoEmmcBoot': True, 'ask': 'reboot'})

        if results['cmd'] == 'flash':
            if results['status'] == 'processing':
                _logger.debug('start timer to update progressbar for clearing emmc {} boot partition'.format(self.mPick['storage']))
                self.mTimerId = self.startTimer(1000) # 1000 ms
                self.mFlashFlag = True
            elif (results['status'] == 'success' or results['status'] == 'failure'):
                # do one last query result before killing the timer
                self._queryResult()
                # flash job either success or failure, stop the timer
                self.killTimer(self.mTimerId)
                self.mFlashFlag = False
                if results['src_filename'] == '/tmp/rescue.img':
                    # recover rescue system success or failure
                    if results['status'] == 'success':
                        self.fail.emit({'Restore': True, 'ask': 'reboot'})
                    else:
                        # critical error, cannot recover the boot image and also failed to download and flash
                        self.fail.emit({'NoFlash': True, 'ask': 'halt'})
                else:
                    # target emmc has been flashed with zeros or failed, so anyway
                    # 3. set the mmc boot partition option
                    # {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', 'config_action': 'enable/disable', 'boot_part_no': '1', 'send_ack':'1', 'target': self.mTgtStorage}
                    _logger.debug('issue command to {} emmc boot partition'.format('enable' if 'androidthings' in self.mPick['os'] else 'disable'))
                    self.sendCommand({'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', \
                                      'config_action': 'enable' if 'androidthings' in self.mPick['os'] else 'disable', \
                                      'boot_part_no': '1', 'send_ack':'1', 'target': self.mPick['storage']})

    def _isTargetEMMC(self, result):
        def parse_target_controller(res):
        # Parse the target storage controller info
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
                if isinstance(v, dict):
                    data.update({k: {att[0]:att[1] for att in findAttrs(['sys_name', 'subsystem', 'driver', 'type'], v)}})
            return [(k, v) for (k, v) in data.items()]

        lstTargets =  parse_target_controller(result)
        for tgt in lstTargets:
            sysname, sysno = tgt[1]['sys_name'].split(':', 1)
            nodepath = tgt[1]['driver'] + sysname.lstrip(tgt[1]['subsystem'])
            if nodepath in self.mPick['storage'] and tgt[1]['type'] == 'MMC':
                return True
        return False

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        _logger.debug('validateResult: {}'.format(self.mResults))
        if self.mResults['cmd'] == 'flash' and self.mResults['status'] == 'success':
            self.progress.emit(100)
            self.mLblRemain.setText('Remaining Time: 00:00')

    def timerEvent(self, event):
        self._queryResult()



@QProcessSlot.registerProcessSlot('processError')
class processErrorSlot(QProcessSlot):
    """
    Handles all errors
    """
    success = pyqtSignal(dict)
    fail = pyqtSignal(dict)

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
        if not self.mMsgBox: self.mMsgBox = self._findChildWidget('msgbox')

        self.mErrors.update(inputs)
        self.mAsk = inputs['ask'] if 'ask' in inputs else None
        self.mDisplay = False if ('NoError' in inputs and inputs['NoError']) else True
        self.__handleError()
        self.mErrors.clear()

    def __handleError(self):
        # Display appropriate messagebox
        self.mMsgBox.clearCheckFlags()

        if 'NoCpuForm' in self.mErrors:
            # Add NoCpuForm icon and critical notice
            self.mMsgBox.setMessage('NoCpuForm')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('No CPU or Form Factor Detected!!!')
        if 'NoDbus' in self.mErrors:
            # add NoDbus icon
            self.mMsgBox.setMessage('NoDbus')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.critical('DBus session bus or installer dbus server not available!!! {}'.format('Retrying...' if self.mAsk is None else 'Restore Rescue System'))
        if 'NoNIC' in self.mErrors:
            # add NoNic icon
            self.mMsgBox.setMessage('NoNIC')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('DBus session bus or installer dbus server not available!!! Retrying...')
        if 'NoIface' in self.mErrors:
            # add NoIface icon
            self.mMsgBox.setMessage('NoIface')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('NIC I/F not available!!! Retrying...')
        if 'NoCable' in self.mErrors:
            # add NoCable icon
            self.mMsgBox.setMessage('NoCable')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('Network cable not connected!!! Retrying...')
        if 'NoServer' in self.mErrors:
            # add NoServer icon
            self.mMsgBox.setMessage('NoServer')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('Cannot connect to TechNexion Rescue Server!!! Retrying...')
        if 'NoDLFile' in self.mErrors:
            self.mMsgBox.setMessage('NoDLFile')
            _logger.warning('No matching file from TechNexion Rescue Server.')
        if 'NoCrawl' in self.mErrors:
            self.mMsgBox.setMessage('NoCrawl')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.warning('Not all crawling of the TechNexion Rescue Service succeeded.')
        if 'NoLocal' in self.mErrors:
            # not critical, ignore
            self.mMsgBox.setMessage('NoLocal')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.warning('No Flashable File from Local Storage.')
            self.mMsgBox.display(False)
            return
        if 'NoStorage' in self.mErrors:
            # error, ask to insert an SDCard
            self.mMsgBox.setMessage('NoStorage')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.error('No Local Storage Media for installation!!! Retrying...')
        if 'NoPartition' in self.mErrors:
            # not critical, ignore
            self.mMsgBox.setMessage('NoPartition')
            self.mMsgBox.setCheckFlags(self.mErrors)
            _logger.warning('No Mounted Partition Found.')
            self.mMsgBox.display(False)
            return
        if 'NoSelection' in self.mErrors:
            # serious error
            self.mMsgBox.setMessage('NoSelection')
            _logger.error('User selections are incorrect.')
        if 'NoDownload' in self.mErrors:
            # critical, but continue
            self.mMsgBox.setMessage('NoDownload')
            _logger.warning('Flashing failed!!! Restore Bootable Rescue System...')
        if 'NoFlash' in self.mErrors:
            # not critical, ignore
            self.mMsgBox.setMessage('NoFlash')
            _logger.warning('Flashing failed!!! Restore Bootable Rescue System...')
        if 'NoInterrupt' in self.mErrors:
            # not critical, ignore
            self.mMsgBox.setMessage('NoInterrupt')
            _logger.warning('Flashing in progress. Ignore all user inputs')
        if 'NoEmmcWrite' in self.mErrors:
            # emmc boot partition option error, not critical.
            self.mMsgBox.setMessage('NoEmmcWrite')
            _logger.warning('Unable to set writable to emmc boot partition!!! continue...')
        if 'NoEmmcBoot' in self.mErrors:
            # emmc boot partition option error, not critical.
            self.mMsgBox.setMessage('NoEmmcBoot')
            _logger.warning('Unable to set emmc boot options!!! continue...')
        if 'NoTgtEmmcCheck' in self.mErrors:
            # emmc boot partition option error, not critical.
            self.mMsgBox.setMessage('Complete')
            _logger.warning('Flash complete, ignore checking target storage for emmc failed...')
        if 'NoTgtEmmc' in self.mErrors:
            # target is not emmc.
            self.mMsgBox.setMessage('Complete')
            _logger.warning('Flash complete, ignore target storage not emmc...')
        if 'Restore' in self.mErrors:
            self.mMsgBox.setMessage('Restore')
            _logger.warning('Restore complete, reboot the system into Rescue...')
        if 'Complete' in self.mErrors:
            # target is not emmc.
            self.mMsgBox.setMessage('Complete')
            _logger.warning('Flash complete, reboot the system into new OS...')
        if 'QRCode' in self.mErrors:
            self.mMsgBox.setMessage('QRCode')
            _logger.warning('Set QRCode for the download files')


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
                        # reset/reboot the system
                        subprocess.check_call(['systemctl', 'stop', 'guiclientd.service'])
                    except:
                        raise
            elif self.mAsk == 'continue':
                self.mMsgBox.setAskButtons(self.mAsk)
                ret = self.mMsgBox.display(True)
        else:
            self.mMsgBox.setModal(False)
            self.mMsgBox.display(self.mDisplay) # non modal dialog



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
        font = QtGui.QFont('Lato', 32, QtGui.QFont.Normal)
        self.setFont(font)
        self.mIcon = None
        self.mTitle = None
        self.mContent = None
        self.mQRcode = None
        self.mWgtContent = None
        self.mWgtContentLayout = None
        self.mButtons = {}
        self.mCheckFlags = {}

    def resizeEvent(self, event):
        #rect = event.rect()
        _logger.debug('resizeEvent: {}'.format(event.size()))
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
        _logger.debug('paintEvent: {}'.format(event.rect()))

        painter = QtGui.QPainter()
        painter.begin(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtCore.Qt.black, 10))
        painter.drawRoundedRect(self.mRect, 20, 20)
        # unset drawing pen
        painter.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        painter.end()

    def setButtons(self, buttons):
        if isinstance(buttons, dict):
            if 'accept' in buttons.keys():
                btn = QtGui.QPushButton(buttons['accept'])
                btn.clicked.connect(self.accept)
                self.layout().addWidget(btn, 4, 5)
            if 'reject' in buttons.keys():
                btn = QtGui.QPushButton(buttons['reject'])
                btn.clicked.connect(self.reject)
                self.layout().addWidget(btn, 4, 4 if 'accept' in buttons.keys() else 5)

    def clearButtons(self):
        for col in [4, 5]:
            if self.layout().itemAtPosition(4, col):
                index = self.layout().indexOf(self.layout().itemAtPosition(4, col).widget())
                wgt = self.layout().takeAt(index)
                del wgt

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

    def setBackgroundIcons(self, icons):
        if not self.mWgtContent: self.mWgtContent = self.window().findChild(QtGui.QWidget, 'wgtContent')

        d = self.rect().width() / 6
        if self.mWgtContent and isinstance(icons, dict):
            for key, res in icons.items():
                lbl = None
                if key == 'NoIface':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem0') # 'msgItem1'
                elif key == 'NoCable':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem1') # 'msgItem2'
                elif key == 'NoServer':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem2') # 'msgItem3'
                else:
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem0')

                if lbl:
                    _logger.debug('set background icon {} to {}'.format(res, lbl))
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
                if key == 'NoIface':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem0_OL') # 'msgItem1_OL'
                elif key == 'NoCable':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem1_OL') # 'msgItem2_OL'
                elif key == 'NoServer':
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem2_OL') # 'msgItem3_OL'
                else:
                    lbl = self.mWgtContent.findChild(QtGui.QLabel, 'msgItem0_OL')

                # setup which flag icon to use
                if flag: # True or False
                    pixmap = QtGui.QIcon(':res/images/cross.svg').pixmap(QtCore.QSize(d * 2, d * 2)).scaled(QtCore.QSize(d, d), QtCore.Qt.IgnoreAspectRatio)
                else:
                    if ('NoDbus' in flags or 'NoCpuForm' in flags) and key in ['NoIface', 'NoCable', 'NoServer']:
                        pixmap = None
                    else:
                        pixmap = QtGui.QIcon(':res/images/tick.svg').pixmap(QtCore.QSize(d * 2, d * 2)).scaled(QtCore.QSize(d, d), QtCore.Qt.IgnoreAspectRatio)

                # set the label pixmap
                if lbl and pixmap:
                    _logger.debug('set label {} for {} with {}'.format(lbl, key, pixmap))
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
        _logger.debug('setup message box with msgtype: {}'.format(msgtype))

        if msgtype in ['NoCable', 'NoIface', 'NoServer']: # 'NoNic'
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
            self.setTitle("System Check")
            self.setBackgroundIcons({'NoCable': ':res/images/no_cable.svg', \
                                     'NoIface': ':res/images/no_iface.svg', \
                                     'NoServer': ':res/images/no_server.svg'}) # {'NoNIC': ':res/images/no_nic.svg'}
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
        elif msgtype == 'NoDLFile':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Server Check")
            self.setContent("No matching file to download from TechNexion rescue server.")
        elif msgtype == 'NoCrawl':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Server Check")
            self.setContent("Not all files are explored from TechNexion rescue server.")
        elif msgtype == 'NoSelection':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Input Error")
            self.setContent("Please Choose a valid image file to download and an existing storage device to flash.")
        elif msgtype == 'NoInterrupt':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Input Error")
            self.setContent("Please do not interrupt the download and flash progress.")
        elif msgtype == 'NoDownload':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
            self.setTitle("Program Check")
            self.setContent("Download and flash failed.\nClick continue to restore rescue system.")
        elif msgtype == 'NoFlash':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
            self.setTitle("Program Check")
            self.setContent("Download and flash failed.\nPlease retry to flash the image again.")
        elif msgtype == 'NoEmmcWrite':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Warning")
            self.setContent("Cannot set writable to emmc boot partition.\nRestart Rescue to try again.")
        elif msgtype == 'NoEmmcBoot':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
            self.setTitle("Warning")
            self.setContent("Cannot set emmc boot options.")
        elif msgtype == 'Restore':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxInformation')))
            self.setTitle("Restore Complete")
            self.setContent('Please set your jumper to BOOT MODE,\nand reset your board.')
        elif msgtype == 'Complete':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxInformation')))
            self.setTitle("Program Complete")
            # movie = QtGui.QMovie(':/res/images/error_edm-fairy_reset.gif')
            # movie.setScaledSize(QtCore.QSize(self.rect().width() / 2, self.rect().height() / 2))
            # self.setContent(movie)
            self.setContent('Please set your jumper to BOOT MODE,\nand reset your board.')
        elif msgtype == 'Interrupt':
            self.setIcon(self.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxQuestion')))
            self.setTitle("Flashing images.")
            self.setContent("Do you want to stop?")
        # special qrcode setting
        if msgtype == 'QRCode':
            qrIcon = QtGui.QIcon('/tmp/qrcode.svg')
            self.setQrCode(qrIcon)

    def setAskButtons(self, asktype):
        if asktype == 'reboot':
            self.setButtons({'accept': 'REBOOT'})
        elif asktype == 'retry':
            self.setButtons({'accept': 'RETRY'})
        elif asktype == 'continue':
            self.setButtons({'accept': 'CONTINUE'})
        elif asktype == 'interrupt':
            self.setButtons({'accept': 'CONTINUE', 'reject': 'STOP'})

    def clearMessage(self):
        self.clearIcon()
        self.clearTitle()
        self.clearContent()
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
                    _logger.debug('show non Modal')
                    self.show()
