#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import os
import sys
import pyqrcode
import subprocess
import math
import socket
from urllib.parse import urlparse
from PyQt4 import QtGui, QtCore, QtSvg, QtNetwork
from PyQt4.QtCore import QObject, pyqtSignal, pyqtSlot
# import our resource.py with all the pretty images/icons
import resource
import logging
# get the handler to the current module, and setup logging options
_logger = logging.getLogger(__name__)

def _printSignatures(qobj):
    metaobject = qobj.metaObject()
    for i in range(metaobject.methodCount()):
        _logger.warning('{} metaobject signature: {}'.format(qobj, metaobject.method(i).signature()))

def _prettySize(n,pow=0,b=1024,u='B',pre=['']+[p+'i'for p in'KMGTPEZY']):
    r,f=min(int(math.log(max(n*b**pow,1),b)),len(pre)-1),'{:,.%if} %s%s'
    return (f%(abs(r%(-r-1)),pre[r],u)).format(n*b**pow/b**float(r))

def _displayMessage(parent, msgtype):
    msgBox = QMessageDialog(parent)
    if msgtype == 'NoCable':
        msgBox.setIcon(parent.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
        msgBox.setTitle("No ethernet cable connected,\nplease connect an ethernet cable.")
        msgBox.setContent(QtGui.QMovie(':/res/images/error_lan.gif'))
        msgBox.setButtonText({'accept': 'RETRY'})
    elif msgtype == 'NoNIC':
        msgBox.setIcon(parent.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
        msgBox.setTitle("No NIC,\nPlease check your network card")
        #msgBox.setContent(QtGui.QMovie(':/res/images/error_lan.gif'))
        msgBox.setButtonText({'accept': 'RETRY'})
    elif msgtype == 'NoDrv':
        msgBox.setIcon(parent.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
        msgBox.setTitle("Network Interface is down,\nPlease check your network interface is ready")
        #msgBox.setContent(QtGui.QMovie(':/res/images/error_lan.gif'))
        msgBox.setButtonText({'accept': 'RETRY'})
    elif msgtype == 'NoConnection':
        msgBox.setIcon(parent.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
        msgBox.setTitle("No Network Connectivity,\nplease check your NAME server.")
        #msgBox.setContent(QtGui.QMovie(':/res/images/error_lan.gif'))
        msgBox.setButtonText({'accept': 'RETRY'})
    elif msgtype == 'NoDbus':
        msgBox.setIcon(parent.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
        msgBox.setTitle("No DBus Connectivity,\nplease make sure installerd.service is running...")
        #msgBox.setContent(QtGui.QMovie(':/res/images/error_dbus.gif'))
        msgBox.setButtonText({'accept': 'RETRY'})
    elif msgtype == 'NoStorage':
        msgBox.setIcon(parent.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
        msgBox.setTitle("No Mass Storage Detected,\n Please insert an SD card.")
        msgBox.setContent(QtGui.QMovie(':/res/images/error_sd.gif'))
        msgBox.setButtonText({'accept': 'RETRY'})
    elif msgtype == 'NoCpuForm':
        msgBox.setIcon(parent.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxWarning')))
        msgBox.setTitle("No CPU or Form Factor Detected,\n Continue with all CPU/Form Factor?")
        #msgBox.setContent(QtGui.QMovie(':/res/images/error_sd.gif'))
        msgBox.setButtonText({'accept': 'RETRY', 'reject': 'CONTINUE'})
    elif msgtype == 'Reboot':
        msgBox.setIcon(parent.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxInformation')))
        msgBox.setTitle("Flash Complete.\nPlease set your jumper to BOOT MODE,\nand reset your board.")
        msgBox.setContent(QtGui.QMovie(':/res/images/error_edm-fairy_reset.gif'))
        msgBox.setButtonText({'accept': 'REBOOT'})
    elif msgtype == 'InputError':
        msgBox.setIcon(parent.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
        msgBox.setTitle("Input Error.")
        msgBox.setContent("Please Choose an image file to download and a storage device to flash")
        msgBox.setButtonText({'accept': 'RETRY'})
    elif msgtype == 'Flashing':
        msgBox.setIcon(parent.style().standardIcon(getattr(QtGui.QStyle, 'SP_MessageBoxCritical')))
        msgBox.setTitle("Flashing images.")
        msgBox.setContent("Do you want to stop?")
        msgBox.setButtonText({'accept': 'NO', 'reject': 'STOP'})
    else:
        return False
    return msgBox.exec_()

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
                        if int(row['size']) == 3825205248:
                            resName = ":/res/images/storage_emmc.svg"
                        else:
                            resName = ":/res/images/storage_sd.svg"
                    item.setToolTip('{}'.format(row['name']))
                elif 'os' in row:
                    resName = ":/res/images/os_{}.svg".format(row['os'].lower())
                    item.setToolTip(row['os'].lower())
                elif 'board' in row:
                    #update the VERSION within the svg resource byte array, and draw the svg
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
        self.mCmds = []
        self.mViewer = None
        self.finish.connect(self._reqDone)

    def _setCommand(self, cmd):
        self.mCmds.append(cmd)
        _logger.debug("issued request: {}".format(self.mCmds[-1]))

    @pyqtSlot()
    @pyqtSlot(bool)
    @pyqtSlot(int)
    @pyqtSlot(str)
    @pyqtSlot(list)
    @pyqtSlot(dict)
    @pyqtSlot(QtGui.QListWidgetItem)
    def processSlot(self, inputs = None):
        """
        called by signals from other GObject components
        To be overriden by all sub classes
        """
        if self.mViewer is None and isinstance(inputs, dict) and 'viewer' in inputs.keys():
            try:
                self.request.disconnect()
                # disconnect request signal first
            except:
                _logger.debug("disconnect request signal first")

            self.mViewer = inputs['viewer']
            # call the viewer's setResponseSlot API to setup the callback to self.resultSlot()
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
    request = pyqtSignal(dict)
    success = pyqtSignal(str)
    fail = pyqtSignal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = {}

    def process(self, inputs = None):
        """
        Handle detect device callback slot
        """
        self._setCommand({'cmd': 'info', 'target': 'som'})
        self.request.emit(self.mCmds[-1])

    def parseResult(self, results):
        """
        Handle returned detect device results from PyQt Msger
        """
        if 'found_match' in results and results['status'] == 'success':
            self.mResults.update(results)
            form, cpu, baseboard = results['found_match'].split(',')
            self._findChildWidget('lblCpu').setText(cpu)
            self._findChildWidget('lblForm').setText(form)

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # Check for available cpu anf form factor
        if 'found_match' not in self.mResults and self.mResults['status'] == 'failure':
            ret = _displayMessage(self, 'NoCpuForm')
            if ret: # Accepted: 1 (retry), Rejected: 0 (continue)
                # retry scanning the storage
                # signal once after 1000ms to do check for CPU / Form Factor again
                QtCore.QTimer.singleShot(1000, self.process)
                return
            else:
                # do not retry and carry on detecting all imx and all form factor
                self._findChildWidget('lblCpu').setText('No CPU')
                self._findChildWidget('lblForm').setText('No Form Factor')
                self.fail.emit('Target Device SOM info not found.\n')

        form, cpu, baseboard = self.mResults['found_match'].split(',')
        self.success.emit('Found: {} {} {}\n'.format(cpu, form, baseboard))



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

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mInputs = {}
        self.mResults = []
        # use QtNetwork NAMger to send a request to technexion's rescue server
        # when the request is finished, NAMger will signal its "finish" signal
        # which calls back to self._networkResponse() with reply
        # for checking network connectivity
        self.mNetMgr = QtNetwork.QNetworkAccessManager()
        # setup callback slot to self._networkResponse() for QtNetwork's NAMgr finish signal
        self.mNetMgr.finished.connect(self._urlResponse)

    def process(self, inputs):
        """
        Handle crawlWeb process slot (signalled by initialized signal)
        """
        if 'location' not in inputs:
            self.mInputs.update({'location': '/'})
        if 'target' not in inputs:
            self.mInputs.update({'target': 'http://rescue.technexion.net'})

        # check network connections
        self.__checkNetwork()
        
    def __checkNetwork(self):
        # Check for networks, which means sending commands to installerd.service to request for network status
        # send request to installerd.service to request for network status.
        _logger.debug('send request to installerd to query network status...')
        self._setCommand({'cmd': 'config', 'subcmd': 'nic', 'config_id': 'ifflags', 'config_action': 'get', 'target': 'eth0'})
        self.request.emit(self.mCmds[-1])

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
            ret = _displayMessage(self, 'NoConnection')
            if ret: # accept: 1, reject: 0
                _logger.critical('TechNexion rescue server not available!!! Retrying...')
                QtCore.QTimer.singleShot(1000, self.__hasValidNetworkConnectivity)
                return
        _logger.debug('start the crawl process: {}'.format(self.mInputs))
        # start the crawl process
        self.__crawlUrl(self.mInputs) # e.g. /pico-imx7/pi-070/

    def __crawlUrl(self, inputs):
        params = {}
        params.update(inputs)
        self._setCommand({'cmd': 'info', 'target': params['target'], 'location': params['location']})
        _logger.debug('crawl request: {}'.format(self.mCmds[-1]))
        self.request.emit(self.mCmds[-1])

    def parseResult(self, results):
        if 'subcmd' in results.keys() and results['subcmd'] == 'nic':
            print('subcmd: nic, parse result: {}'.format(results))
            if 'status' in results and results['status'] == 'success':
                if 'state' in results.keys() and 'flags' in results.keys():
                    # a. Check whether NIC hardware available (do we have mac?)
                    #if 'LOWER_UP' in results['state']:
                    # b. Check NIC connection is up (flag says IFF_UP?)
                    if 'UP' in results['state']:
                        # c. Check NIC connection is running (flag says IFF_RUNNING?)
                        if 'RUNNING' in results['state']:
                            # d. when all is running, check to see if we can connect to our rescue server.
                            self.__hasValidNetworkConnectivity()
                            return
                        else:
                            err = 'NoCable'
                    else:
                        err = 'NoDrv'
                    #else:
                    #    err = 'NoNic'
                    ret = _displayMessage(self, err)
                    if ret: # accept: 1, (RETRY) reject: 0
                        if err == 'NoNic':
                            _logger.critical('Network Error No L1 Driver!!! Retrying...')
                        elif err == 'NoDrv':
                            _logger.critical('Network Error NIC Down!!! Retrying...')
                        elif err == 'NoCable':
                            _logger.critical('Network Error No Cable!!! Retrying...')
                        QtCore.QTimer.singleShot(1000, self.__checkNetwork)
            return

        #print('crawlWeb result: {}'.format(results))
        if 'total_uncompressed' in results.keys() or 'total_size' in results.keys():
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
            os, ver = self.__parseFilename(fname.rstrip('.xz'))
            # make up the XZ file URL
            url = results['target'] + '/rescue' + results['location']
            # add {cpu, form, board, display, os, ver, size(uncompsize), url}
            self.mResults.append({'cpu': cpu, 'form': form, 'board': board, 'display': display, 'os': os, 'ver': ver, 'size': uncompsize, 'url': url})

        elif 'file_list' in results.keys():
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
            self.fail.emit('Crawling url {} to find suitable xz file.\n'.format(results['location']))

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
        if (cpu[0:4] in filename.lower() or cpu in filename.lower()):
            if form in filename.lower():
                _logger.debug('Matched {} {}... {}'.format(cpu[0:4], form, filename))
                return True
        return False

    def __parseSOMInfo(self, path):
        p = re.compile('\/(\w+)[_|-](\w+)\/(\w+)-(\w+)\/(.+)\.xz', re.IGNORECASE)
        m = p.match(path)
        if m:
            return m.groups()

    def __parseFilename(self, fname):
        if ('-' in fname):
            os, ver = fname.split('-', 1)
        else:
            os, ver = fname, ''
        return os, ver

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        if isinstance(self.mResults, list) and len(self.mResults):
            _logger.debug('crawlWeb result: {}\n'.format(self.mResults))
            # if found suitable xz files, send them on to the next process slot
            self.success.emit(self.mResults)
            return
        else:
            self.fail.emit('Did not find any suitable xz file\n')



@QProcessSlot.registerProcessSlot('crawlLocalfs')
class crawlLocalfsSlot(QProcessSlot):
    """
    Potentially the Crawling Mechanism is done in a long process thread.
    If the long process is needed, it could possibly be done using QThread in Qt.
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(object)
    #success = pyqtSignal(int, int, object) # QtGui.PyQt_PyObject)
    fail = pyqtSignal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = []

    def process(self, inputs):
        """
        Handle crawling xz files from inputs, i.e. lists of mount points
        """
        # make up the request params
        params = {'target': socket.gethostname()}
        if isinstance(inputs, list):
            if len(inputs) == 0:
                inputs.append('~/')

            for path in inputs:
                params.update({'location': path if path.endswith('/') else (path + '/')})
                self._setCommand({'cmd': 'info', 'target': params['target'], 'location': params['location']})
                self.request.emit(self.mCmds[-1])

    def parseResult(self, results):
        # Parse the return local xz files
        if 'status' in results and results['status'] == 'success' and \
           'file_list' in results and isinstance(results['file_list'], dict):
            # We know that file_list is a dictionary because we send it from the server
            for fname, finfo in results['file_list'].items():
                # extract form, cpu, board, display, and filename of the XZ filename
                try:
                    form, cpu, board, display, os, ver = self.__parseProp(fname)
                    size = finfo['total_uncompressed'] if ('total_uncompressed' in finfo and int(finfo['total_uncompressed']) > 0) else finfo['total_size']
                    url = finfo['file_path'] if 'file_path' in finfo else None
                    if form is not None and cpu is not None and board is not None and display is not None and os is not None and ver is not None and size is not None and url is not None:
                        # add {cpu, form, board, display, os, ver, size(uncompsize), url}
                        self.mResults.append({'cpu': cpu, 'form': form, 'board': board, 'display': display, 'os': os, 'ver': ver, 'size': size, 'url': url})
                except:
                    _logger.warning("skip parsing {} to extract form, cpu, board, display, os, and version info.".format(fname))

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        if isinstance(self.mResults, list) and len(self.mResults):
            _logger.debug('validateResult: crawlLocalfs result: {}\n'.format(self.mResults))
            # if found suitable xz files, send them on to the next process slot
            self.success.emit(self.mResults)
            return
        else:
            self.fail.emit('Did not find any suitable xz file on mounted partitions\n')

    def __parseProp(self, filename):
        # '{}-{}_{}-{}_{}-{}.xz' => 'form' 'cpu', 'board', 'display', 'os', 'ver'
        p = re.compile('(\w+)[_|-](\w+)[_|-](\w+)[_|-](\w+)[_|-](\w+)[_|-](.+)\.xz', re.IGNORECASE)
        m = p.match(filename)
        if m:
            return m.groups()



@QProcessSlot.registerProcessSlot('scanStorage')
class scanStorageSlot(QProcessSlot):
    """
    Handle scanStorage callback slot
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(object)
    #success = pyqtSignal(int, int, object) # QtGui.PyQt_PyObject)
    fail = pyqtSignal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = []

    def process(self, inputs = None):
        # step 4: request for list of targets storage device
        self._setCommand({'cmd': 'info', 'target': 'emmc', 'location': 'disk'})
        self.request.emit(self.mCmds[-1])
        self._setCommand({'cmd': 'info', 'target': 'hd', 'location': 'disk'})
        self.request.emit(self.mCmds[-1])

    def parseResult(self, results):
        def parse_target_list(res):
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
                if isinstance(v, dict):
                    data.update({k: {att[0]:att[1] for att in findAttrs(['device_node', 'device_type', 'size', 'id_bus', 'id_serial', 'id_model'], v)}})
            return [(i, k, v) for i, (k, v) in enumerate(data.items())]

        # step 5: ask user to choose the target to flash
        listTarget = parse_target_list(results)
        if len(listTarget):
            for tgt in listTarget:
                # 'name', 'node path', 'disk size'
                self.mResults.append({'name': tgt[1], \
                                      'path': tgt[2]['device_node'], \
                                      'device_type': tgt[2]['device_type'], \
                                      'size':int(tgt[2]['size']) * 512, \
                                      'id_bus': tgt[2]['id_bus'] if 'id_bus' in tgt[2] else 'None', \
                                      'id_serial': tgt[2]['id_serial'] if 'id_serial' in tgt[2] else 'None', \
                                      'id_model': tgt[2]['id_model'] if 'id_model' in tgt[2] else 'None'})

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # Check for available storage disk in the self.mResult list
        if isinstance(self.mResults, list) and len(self.mResults):
            # emit results to the next QProcessSlot, i.e. chooseStorage, and crawlLocalfs
            self.success.emit(self.mResults)
            return
        else:
            #ret = QtGui.QMessageBox.warning(self, 'TechNexion Rescue System', 'No suitable storage found, please insert sdcard...\nClick Retry to rescan!!!', QtGui.QMessageBox.Ok | QtGui.QMessageBox.Retry, QtGui.QMessageBox.Ok)
            ret = _displayMessage(self, 'NoStorage')
            if ret: # Accepted: 1, Rejected: 0
                # retry scanning the storage
                QtCore.QTimer.singleShot(1000, self.process)


@QProcessSlot.registerProcessSlot('scanPartition')
class scanPartitionSlot(QProcessSlot):
    """
    Can for the mounted points from exiting partitions in the system
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(object)
    fail = pyqtSignal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mResults = []

    def process(self, inputs):
        # issue commands to find partitions with mount points
        self._setCommand({'cmd': 'info', 'target': 'hd', 'location': 'partition'})
        self.request.emit(self.mCmds[-1])
        self._setCommand({'cmd': 'info', 'target': 'emmc', 'location': 'partition'})
        self.request.emit(self.mCmds[-1])

    def parseResult(self, results):
        # parse the returned partition results to find mount points
        if isinstance(results, dict) and 'status' in results and results['status'] == "success":
            for k, v in results.items():
                if isinstance(v, dict) and 'mount_point' in v.keys():
                    if 'mount_point' in v and v['mount_point'] != 'None':
                        if 'media' in v['mount_point']:
                            self.mResults.append(v['mount_point'])

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # Check for available storage disk in the self.mResult list
        _logger.debug('validateResult scanPartition result: {}'.format(self.mResults))
        if isinstance(self.mResults, list) and len(self.mResults):
            # emit results to the next QProcessSlot, i.e. crawlLocalfs
            self.success.emit(list(set(self.mResults)))



# @QProcessSlot.registerProcessSlot('chooseImage')
# class chooseImageSlot(QProcessSlot):
#     """
#     Handles button click event to issue cmd to choose board, os, and display
#     """
#     request = pyqtSignal(dict)
#     success = pyqtSignal(dict)
#     fail = pyqtSignal(str)
# 
#     def __init__(self, parent = None):
#         super().__init__(parent)
#         self.mResults = []
#         self.mPick = {'board': None, 'os': None, 'ver': None, 'display': None}
#         self.mLstWgtBoard = None
#         self.mLstWgtOS = None
#         self.mLstWgtDisplay = None
#         self.mUrl = None
# 
#     def process(self, inputs):
#         # update Display the dynamic UI from the available list of found rescue files passed in inputs
#         _logger.debug('chooseImageSlot: signal sender: {}, inputs: {}'.format(self.sender().objectName(), inputs))
#         # update the UI element for later use
#         if self.mLstWgtBoard is None: self.mLstWgtBoard = self._findChildWidget('lstWgtBoard')
#         if self.mLstWgtOS is None: self.mLstWgtOS = self._findChildWidget('lstWgtOS')
#         if self.mLstWgtDisplay is None: self.mLstWgtDisplay = self._findChildWidget('lstWgtDisplay')
# 
#         if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
#             # parse the download files into selectable options, i.e. board, OS, ver, display
#             self.__parseDownloadFilesList(inputs)
#             self.__updateUI()
# 
#         if self.sender() == self.mLstWgtBoard or self.sender() == self.mLstWgtDisplay or self.sender() == self.mLstWgtOS:
#             # do smart selections based on item chosen from the board, OS, ver, display pools/lists
#             filtered = self.__smartFilterSelections(inputs)
#             # do clever filtering to disable items not related to selection
#             self.__disableList(filtered)
#             self.__updateUI()
# 
#         if self.sender().objectName()== "btnNext":
#             # Find a matching CPU and FORM from the self.mCpuNames and self.mFormNames pool
#             for cpu in self.mCpuNames:
#                 if cpu in self._findChildWidget('lblCpu').text().lower():
#                     self.mPick['cpu'] = cpu
#             for form in self.mFormNames:
#                 if form in self._findChildWidget('lblForm').text().lower():
#                     self.mPick['form'] =  form
#             self.mUrl = '{}-{}/{}-{}/{}-{}.xz'.format(self.mPick['form'], \
#                                                       self.mPick['cpu'], \
#                                                       self.mPick['board'], \
#                                                       self.mPick['display'], \
#                                                       self.mPick['os'], \
#                                                       self.mPick['ver'])
#             if self.mPick['board'] is not None and self.mPick['os'] is not None and self.mPick['display'] is not None and self.mPick['ver'] is not None:
#                 self.finish.emit()
# 
#     def __parseDownloadFilesList(self, listOfFileDict):
#         # {'os': 'ubuntu',
#         #  'size': '3420454912',
#         #  'ver': '16.04',
#         #  'display': 'lcd800x480',
#         #  'cpu': 'imx7',
#         #  'form': 'pico',
#         #  'board': 'dwarf',
#         #  'url': 'http://rescue.technexion.net/rescue/pico-imx7/dwarf-lcd800x480/ubuntu-16.04.xz'
#         self.mResults.extend([d for d in listOfFileDict if (int(d['size']) > 0)])
#         _logger.info('list of xz files: {}'.format(self.mResults))
# 
#         # gets the unique set of available boards, OS, version, Display from the crawled list
#         self.mCpuNames = set(dlfile['cpu'] for dlfile in self.mResults if ('cpu' in dlfile))
#         self.mFormNames = set(dlfile['form'] for dlfile in self.mResults if ('form' in dlfile))
#         self.mBoardNames = set(dlfile['board'] for dlfile in self.mResults if ('board' in dlfile))
#         self.mDisplayNames = set(dlfile['display'] for dlfile in self.mResults if ('display' in dlfile))
#         self.mOSNames = []
#         for d in [{'os':dlfile['os'], 'ver':dlfile['ver']} for dlfile in self.mResults if ('os' in dlfile and 'ver' in dlfile)]:
#             if all(not (d == n) for n in self.mOSNames):
#                 self.mOSNames.append(d)
# 
#         # come up with a new list to send to GUI container, i.e. QListWidget
#         self.mBoardList = list({'name': name, 'board': name, 'disable': False} for name in self.mBoardNames)
#         self.mDisplayList = list({'name': name, 'display': name, 'disable': False} for name in self.mDisplayNames)
#         self.mOSList = list({'name': item['os']+'-'+item['ver'], 'os': item['os'], 'ver': item['ver'], 'disable': False} for item in self.mOSNames)
# 
#     def __smartFilterSelections(self, clickedItem):
#         """
#         Handles user selection with the ability to disable other unrelated options (e.g. Board, OS, Version, Display)
#         """
# 
#         selection = []
#         # clever UI display to provide smarter human computer interfaces
#         if isinstance(clickedItem, QtGui.QListWidgetItem):
#             # if not coming from the crawling procSlots, determine what has been chosen from the QListWidget
#             # get the selected item, and do some clever thing to gray out other options
#             if self.sender() == self.mLstWgtBoard:
#                 if (int(clickedItem.flags()) & QtCore.Qt.ItemIsEnabled):
#                     self.mPick['board'] = clickedItem.data(QtCore.Qt.UserRole)['board']
#                 else:
#                     self.mPick['board'] = None
#             elif self.sender() == self.mLstWgtOS:
#                 if (int(clickedItem.flags()) & QtCore.Qt.ItemIsEnabled):
#                     self.mPick['os'] = clickedItem.data(QtCore.Qt.UserRole)['os']
#                     self.mPick['ver'] = clickedItem.data(QtCore.Qt.UserRole)['ver']
#                 else:
#                     self.mPick['os'] = None
#                     self.mPick['ver'] = None
#             elif self.sender() == self.mLstWgtDisplay:
#                 if (int(clickedItem.flags()) & QtCore.Qt.ItemIsEnabled):
#                     self.mPick['display'] = clickedItem.data(QtCore.Qt.UserRole)['display']
#                 else:
#                     self.mPick['display'] = None
# 
#         # find the subset of availablelists from user selections
#         _logger.debug('Pick: {}'.format(self.mPick))
#         for v in self.mPick.values():
#             if v is not None:
#                 selection.append(v)
#         _logger.debug('Selection: {}'.format(selection))
#         lstReturn = self._findSubset(selection, self.mResults) if len(selection) else self.mResults
# #         if len(lstReturn) == 1:
# #             # should automatically check the only possible selection
# #             self.mPick['board'] = lstReturn['board']
# #             self.mPick['display'] = lstReturn['display']
# #             self.mPick['os'] = lstReturn['os']
# #             self.mPick['version'] = lstReturn['version']
#         return lstReturn
# 
#     def __disableList(self, filteredList):
#         _logger.debug('filtered list: {}'.format(filteredList))
#         for ui in self.mBoardList:
#             if len(filteredList) and all(ui['board'] not in dlfile.values() for dlfile in filteredList):
#                 ui['disable'] = True
#             else:
#                 ui['disable'] = False
#         for ui in self.mDisplayList:
#             if len(filteredList) and all(ui['display'] not in dlfile.values() for dlfile in filteredList):
#                 ui['disable'] = True
#             else:
#                 ui['disable'] = False
#         for ui in self.mOSList:
#             if len(filteredList) and all(ui['os'] not in dlfile.values() for dlfile in filteredList):
#                 ui['disable'] = True
#             else:
#                 ui['disable'] = False
#             if len(filteredList) and all(ui['ver'] not in dlfile.values() for dlfile in filteredList):
#                 ui['disable'] = True
#             else:
#                 ui['disable'] = False
# 
#     def __updateUI(self):
#         # update the UI display according to the parsed board/os/ver/display selections from lists of download files
#         _insertToContainer(self.mBoardList, self.mLstWgtBoard, None)
#         _insertToContainer(self.mOSList, self.mLstWgtOS, None)
#         _insertToContainer(self.mDisplayList, self.mLstWgtDisplay, None)
# 
#     # NOTE: Not using the resultSlot() and in turn parseResult() because we did not send a request via DBus
#     # to get results from installerd
#     #def parseResult(self, results):
#     #    pass
# 
#     def validateResult(self):
#         # flow comes here (gets called) after self.finish.emit()
#         # so, check for valid storage to flash selected Url file here
#         if self.mUrl and isinstance(self.mUrl, str):
#             for item in self.mResults:
#                 if self.mUrl.replace('/', '_') in item['url'] or self.mUrl in item['url']:
#                     _logger.warning('validateResult found matched download URL: {}'.format(item['url']))
#                     self.success.emit(item)
#                     self._findChildWidget('tabChoose').hide()
#                     self._findChildWidget('btnNext').hide()
#                     self._findChildWidget('tabRescue').show()
#                     self._findChildWidget('btnFlash').show()
#                     return
#         else:
#             self.fail.emit('failed to choose a valid file to download')



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
        if self.mPick['os'] == None:
            self._findChildWidget('tabOS').show()
            self._findChildWidget('lblInstruction').setText('Choose an OS')
        elif self.mPick['board'] == None:
            self._findChildWidget('tabBoard').show()
            self._findChildWidget('lblInstruction').setText('Choose your baseboard type')
        elif self.mPick['display'] == None:
            self._findChildWidget('tabDisplay').show()
            self._findChildWidget('lblInstruction').setText('Choose your panel type')
        elif self.mPick['storage'] == None:
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
    request = pyqtSignal(dict)
    success = pyqtSignal(dict)
    fail = pyqtSignal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mOSUIList = None
        self.mLstWgtOS = None
        self.mLstWgtSelection =None
        self.mUserData = None

    def process(self, inputs):
        # update Display the dynamic UI from the available list of found rescue files passed in inputs
        _logger.debug('chooseOSSlot: signal sender: {}, inputs: {}'.format(self.sender().objectName(), inputs))

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
                _logger.debug('self:{}, sender:{}, old pick:{}, new pick:{}'.format(self.Name(), self.sender().objectName(), self.mPick, inputs))
                self.mPick.update(inputs)
                self._filterList('os', self.mPick, self.mOSUIList, self.mResults)
                _insertToContainer(self.mOSUIList, self.mLstWgtOS, None)

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
        self.mOSUIList = list({'name': name, 'os': name, 'disable': False} for name in self.mOSNames if name.lower() != 'rescue')

    def __extractLatestVersion(self):
        def parseVersion(strVersion):
            try:
                found = float(re.search('\d+\.\d+', strVersion).group(0))
            except:
                found = 0.0
            return found

        # Find newest version from the picked os
        version = 0.0
        for item in self.mVerList:
            if self.mPick['os'] == item['os']:
                version = parseVersion(item['ver']) if (version < parseVersion(item['ver'])) else version
        return '{}'.format(version) if version > 0.0 else None

    # NOTE: Not using the resultSlot() and in turn parseResult() because we did not send a request via DBus
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
            self.fail.emit('failed to choose a valid file to download')



@QProcessSlot.registerProcessSlot('chooseBoard')
class chooseBoardSlot(QChooseSlot):
    """
    Handles button click event to issue cmd to choose board
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(dict)
    fail = pyqtSignal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mBoardUIList = None
        self.mLstWgtBoard = None
        self.mLstWgtSelection =None
        self.mUserData = None

    def process(self, inputs):
        # update Display the dynamic UI from the available list of found rescue files passed in inputs
        _logger.debug('chooseBoardSlot: signal sender: {}, inputs: {}'.format(self.sender().objectName(), inputs))

        # update the UI element for later use
        if self.mLstWgtBoard is None: self.mLstWgtBoard = self._findChildWidget('lstWgtBoard')
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')

        if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
            # parse the download files into selectable options, i.e. board, OS, ver, display
            self._parseResultList(inputs)
            self._extractUIList()
            _insertToContainer(self.mBoardUIList, self.mLstWgtBoard, None)

        if self.sender().objectName() == 'chooseOS' or self.sender().objectName() == 'chooseBoard' or \
           self.sender().objectName() == 'chooseDisplay' or self.sender().objectName() == 'chooseStorage' or \
           self.sender().objectName() == 'chooseSelection':
            # chooseOS or chooseBoard or chooseDisplay or chooseStorage, then sends a picked choice
            if isinstance(inputs, dict) and all(field in inputs for field in ['board', 'os', 'ver', 'display', 'storage']):
                _logger.debug('self:{}, sender:{}, old pick:{}, new pick:{}'.format(self.Name(), self.sender().objectName(), self.mPick, inputs))
                self.mPick.update(inputs)
                self._filterList('board', self.mPick, self.mBoardUIList, self.mResults)
                _insertToContainer(self.mBoardUIList, self.mLstWgtBoard, None)

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

    # NOTE: Not using the resultSlot() and in turn parseResult() because we did not send a request via DBus
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
            self.fail.emit('failed to choose a valid file to download')



@QProcessSlot.registerProcessSlot('chooseDisplay')
class chooseDisplaySlot(QChooseSlot):
    """
    Handles button click event to issue cmd to choose display
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(dict)
    fail = pyqtSignal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mDisplayUIList = []
        self.mLstWgtDisplay = None
        self.mLstWgtSelection =None
        self.mIfaceTypes = ['lvds', 'hdmi', 'ttl', 'vga', 'dsi', 'dpi']

    def process(self, inputs):
        # update Display the dynamic UI from the available list of found rescue files passed in inputs
        _logger.debug('chooseDisplaySlot: signal sender: {}, inputs: {}'.format(self.sender().objectName(), inputs))

        # update the UI element for later use
        if self.mLstWgtDisplay is None: self.mLstWgtDisplay = self._findChildWidget('lstWgtDisplay')
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')

        if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
            # parse the download files into selectable options, i.e. board, OS, ver, display
            self._parseResultList(inputs)
            self._extractUIList()
            _insertToContainer(self.mDisplayUIList, self.mLstWgtDisplay, None)

        if self.sender().objectName() == 'chooseOS' or self.sender().objectName() == 'chooseBoard' or \
           self.sender().objectName() == 'chooseDisplay' or self.sender().objectName() == 'chooseStorage' or \
           self.sender().objectName() == 'chooseSelection':
            # chooseOS or chooseBoard or chooseDisplay or chooseStorage, then sends a picked choice
            if isinstance(inputs, dict) and all(field in inputs for field in ['board', 'os', 'ver', 'display', 'storage']):
                _logger.debug('self:{}, sender:{}, old pick:{}, new pick:{}'.format(self.Name(), self.sender().objectName(), self.mPick, inputs))
                self.mPick.update(inputs)
                self._filterList('display', self.mPick, self.mDisplayUIList, self.mResults)
                _insertToContainer(self.mDisplayUIList, self.mLstWgtDisplay, None)

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
            if any(sz in name for sz in ['050', '070', '101', '150', 'lcd']):
                iftype = 'ttl'
            elif any(sz in name for sz in ['mipi']):
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

    # NOTE: Not using the resultSlot() and in turn parseResult() because we did not send a request via DBus
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
            self.fail.emit('failed to choose a valid file to download')



@QProcessSlot.registerProcessSlot('chooseStorage')
class chooseStorageSlot(QChooseSlot):
    """
    Handles button click event to issue cmd to choose board, os, and display
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(dict)
    fail = pyqtSignal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mStorageUIList = None
        self.mLstWgtStorage = None
        self.mLstWgtSelection =None
        self.mPick = {'board': None, 'os': None, 'ver': None, 'display': None, 'storage': None}

    def process(self, inputs):
        # Display the dynamic UI from the available list of found target storage passed in inputs
        _logger.debug('chooseStorageSlot: signal sender: {}, inputs: {}'.format(self.sender().objectName(), inputs))
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
                _logger.debug('self:{}, sender:{}, old pick:{}, new pick:{}'.format(self.Name(), self.sender().objectName(), self.mPick, inputs))
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
                                  'size': item['size'], \
                                  'id_bus': item['id_bus'], \
                                  'disable': False} for item in self.mResults)
        _logger.debug('chooseStorage: mStorageUIList: {}'.format(self.mStorageUIList))

    # NOTE: Not using the resultSlot() and in turn parseResult() because we did not send a request via DBus
    # to get results from installerd
    #def parseResult(self, results):
    #    pass

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # so check for valid storage to flash selected Url file here
        if self.mPick['storage'] is not None:
            # show/hide GUI components
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
    request = pyqtSignal(dict)
    success = pyqtSignal(dict)
    chosen = pyqtSignal(dict)
    fail = pyqtSignal(str)

    def __init__(self, parent = None):
        super().__init__(parent)
        self.mLstWgtSelection =None
        self.mLstWgtStorage = None
        self.mLstWgtOS = None
        self.mLstWgtBoard = None
        self.mLstWgtDisplay = None
        self.mUserData = None

    def process(self, inputs):
        # Display the dynamic UI from the available list of found target storage passed in inputs
        _logger.debug('chooseSelectionSlot: signal sender: {}, inputs: {}'.format(self.sender().objectName(), inputs))
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
            # receive the btnFlash click signal, and send the mPick to downloadImage procslot
            if all(p is not None for p in self.mPick if (key in self.mPick for key in ['os', 'board', 'display', 'storage'])):
                if hasattr(self._findChildWidget('downloadImage'), 'processSlot'):
                    self.chosen.connect(getattr(self._findChildWidget('downloadImage'), 'processSlot'))
                    self.chosen.emit(self.mPick)

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
                self.finish.emit()

    # NOTE: Not using the resultSlot() and in turn parseResult() because we did not send a request via DBus
    # to get results from installerd
    #def parseResult(self, results):
    #    pass

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # show/hide GUI components
        self.mLstWgtSelection.clearSelection()
        self._updateDisplay()
        # send the self.mPick to appropriate QProcSlot so picking
        # process can be restarted from where it is disgarded
        self.success.emit(self.mPick)

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
                if int(data['size']) == 3825205248:
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
    request = pyqtSignal(dict)
    success = pyqtSignal(int)
    fail = pyqtSignal(str)

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
        self.mTimer = QtCore.QTimer()
        self.mTimer.timeout.connect(self._queryResult)
        self.mLblRemain = None
        #self.mLblDownloadFlash = None
        self.mLstWgtSelection = None
        self.mPick = {'board': None, 'os': None, 'ver': None, 'display': None, 'storage': None}

    def _queryResult(self):
        """
        A callback function acting as a slot for timer's timeout signal.
        Here we calculate the remaining time for the download and flash and update UI accordingly.
        """
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
                self.mLblRemain.setText('Remaining Time: {:02}:{:02}'.format(int(self.mRemaining / 60), int(self.mRemaining % 60)))
                pcent = int(float(self.mResults['bytes_written']) / float(self.mResults['total_uncompressed']) * 100)
                self.success.emit(pcent)

            if 'status' in self.mResults and self.mResults['status'] == 'success':
                self.success.emit(100)

    def process(self, inputs):
        """
        grab the dl_url and tgt_filename from the tableRescueFile and tableTargetStorage itemClicked() signals
        when signal sender is from btnFlash, issue flash command with clicked rescue file and target storage.
        """
        if self.mLblRemain is None: self.mLblRemain = self._findChildWidget('lblRemaining')
        #if self.mLblDownloadFlash is None: self.mLblDownloadFlash = self._findChildWidget('lblDownloadFlash')
        if self.mLstWgtSelection is None: self.mLstWgtSelection = self._findChildWidget('lstWgtSelection')

        if not self.mFlashFlag:
            _logger.debug('downloadImageSlot: signal sender: {}, inputs: {}'.format(self.sender().objectName(), inputs))

            if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
                # keep the available file list for lookup with a self.mPick later
                self.mFileList.extend([d for d in inputs if (int(d['size']) > 0)])

            # step 6: make up the command to download and flash and execute it
            # Need to grab or keep the chooses from file list selection and target list selection
            if self.sender().objectName() == 'chooseSelection':
                _logger.warning('selected choices: {}'.format(inputs))
                self.mPick.update(inputs)
                # extract URL and Target
                self.__getUrlStorageFromPick(inputs)
                # reset the progress bar
                self.success.emit(0)
                # if has URL and Target, then send command to download and flash
                if self.mFileUrl and self.mTgtStorage:
                    _logger.info('download from {} and flash to {}'.format(self.mFileUrl, self.mTgtStorage))
                    self._setCommand({'cmd': 'download', 'dl_url': self.mFileUrl, 'tgt_filename': self.mTgtStorage})
                    # send request to installerd
                    self.request.emit(self.mCmds[-1])
                    # show/hide GUI components
                    self._updateDisplay()
                    #QtGui.QMessageBox.information(self, 'TechNexion Rescue System', 'Download {} and Flash to {}'.format(self.mFileUrl, self.mTgtStorage))
                    # disable the selection widget once started flashing
                else:
                    # prompt for error message
                    #QtGui.QMessageBox.information(self, 'TechNexion Rescue System', 'Input Error:\nPlease Choose an image file to download and a storage device to flash')
                    _displayMessage(self, 'InputError')

        else:
            # prompt for error message
            #QtGui.QMessageBox.information(self, 'TechNexion Rescue System', 'Hold Your Hourses!!!\nPlease wait until downloading is completed...')
            _displayMessage(self, 'Flashing')

    def __getUrlStorageFromPick(self, pick):
        # get picked items from lstWgtSelection
#         for item in self.mLstWgtSelection.findItems('.*', QtCore.Qt.MatchRegExp):
#             data = item.data((QtCore.Qt.UserRole))
#             print(data)
#             if 'os' in data and data['os'] is not None: pick['os'] = data['os']
#             if 'ver' in data and data['ver'] is not None: pick['ver'] = data['ver']
#             if 'board' in data and data['board'] is not None: pick['board'] = data['board']
#             if 'display' in data and data['display'] is not None: pick['display'] = data['display']
#             if 'storage' in data and data['storage'] is not None: pick['storage'] = data['storage']
#                 # Find cpu and form, and search for the URL from self.mFileList
#                 self.mPick['cpu'] = self._findChildWidget('lblCpu').text().lower()
#                 self.mPick['form'] = self._findChildWidget('lblForm').text().lower()
        # Find the URL from filtered subset of the original download file list
        for disp in pick['display']:
            filteredAttr = []
            filteredAttr.append(disp)
            filteredAttr.extend(v for k, v in pick.items() if (v is not None and k != 'storage' and k != 'display'))
            filteredList = self._findSubset(filteredAttr, self.mFileList)
            # remove duplicates
            #urls = list(set(f['url'] for f in filteredList if ('url' in f)))
            urls = []
            for f in filteredList:
                if len(urls):
                    for l in urls:
                        if not (f['os'] == l['os'] and f['ver'] == l['ver'] and f['board'] == l['board'] and f['display'] == l['display'] and f['size'] == l['size']):
                            urls.append(f)
                else:
                    urls.append(f)
            if len(urls):
                self.mFileUrl = urls[0]['url'][:]
            self.mTgtStorage = pick['storage'][:]
        _logger.warning('found url: {} storage: {}'.format(self.mFileUrl, self.mTgtStorage))

    def parseResult(self, results):
        # step 7: parse the result in a loop until result['status'] != 'processing'
        # Start a timer to query results every 1 second
        self.mResults.update(results)
        if results['status'] == 'processing':
            self.mTimer.start(1000) # 1000 ms
            self.mFlashFlag = True
        else:
            # flash job either success or failure
            self.mTimer.stop()
            self.mFlashFlag = False

        # Check for flash complete and send another command for setting emmc boot sequence
        if results['status'] == 'success' and results['cmd'] == 'download':
            # 1. disable readonly for mmc boot partition
            # {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'readonly', 'config_action': 'disable', 'boot_part_no': '1', 'target': self.mTgtStorage]}
            self._setCommand({'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'readonly', \
                              'config_action': 'enable' if 'androidthings' in self.mPick['os'] else 'disable', \
                              'boot_part_no': '1', 'send_ack':'1', 'target': self.mTgtStorage})
            self.request.emit(self.mCmds[-1])

        if results['status'] == 'success' and results['cmd'] == 'config' and results['config_id'] == 'readonly':
            # 2. clear the mmc boot partition
            # {'cmd': 'flash', 'src_filename': '/dev/zero', 'tgt_filename': self.mTgtStorage + 'boot0'}
            self._setCommand({'cmd': 'flash', 'src_filename': '/dev/zero', 'tgt_filename': self.mTgtStorage + 'boot0'})
            self.request.emit(self.mCmds[-1])

        if results['status'] == 'success' and results['cmd'] == 'flash':
            # 3. set the mmc boot partition option
            # {'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', 'config_action': 'enable/disable', 'boot_part_no': '1', 'send_ack':'1', 'target': self.mTgtStorage}
            self._setCommand({'cmd': 'config', 'subcmd': 'mmc', 'config_id': 'bootpart', \
                              'config_action': 'enable' if 'androidthings' in self.mPick['os'] else 'disable', \
                              'boot_part_no': '1', 'send_ack':'1', 'target': self.mTgtStorage})
            self.request.emit(self.mCmds[-1])

#         # Check for success of the config mmc command
#         if results['status'] == 'successs' and results['cmd'] == 'config' and results['subcmd'] == 'mmc':
#             self.finish.emit()

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        _logger.debug('validateResult: {}'.format(self.mResults))

        # Final notification
        if isinstance(self.mResults, dict) and (self.mResults['status'] == 'success' or self.mResults['status'] == 'failure'):
            #ret = QtGui.QMessageBox.warning(self, 'TechNexion Rescue System', 'Installation {}...\nSet boot jumper to boot from sdcard/emmc,\nAnd click RESET to reboot sytem!'.format('Complete' if (self.mResults['status'] == 'success') else 'Failed'), QtGui.QMessageBox.Ok | QtGui.QMessageBox.Reset, QtGui.QMessageBox.Ok)
            ret = _displayMessage(self, 'Reboot')
            if ret:
                try:
                    # reset/reboot the system
                    subprocess.check_call(['reboot'])
                except:
                    raise

    def _updateDisplay(self):
        # show and hide some Gui elements
        self.mLstWgtSelection.setDisabled(True)
        self._findChildWidget('btnFlash').hide()
        self._findChildWidget('progressBarStatus').show()
        self.mLblRemain.show()
        self._findChildWidget('lblInstruction').setText('')
        #self.mLblDownloadFlash.setText('URL: {}'.format(self.mFileUrl.replace('http://rescue.technexion.net/rescue', '')))



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
        QtGui.QDialog.__init__(self, parent, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)

        # Set the geometry to slightly smaller than application geomtry
        self.mRect = parent.window().geometry() if parent else QtGui.QApplication.instance().desktop().screenGeometry()
        self.setGeometry(self.mRect.width() / 16, self.mRect.height() / 16, self.mRect.width() - (self.mRect.width() / 8), self.mRect.height() - (self.mRect.height() / 8))

        # draw and mask round corner
        radius = 20.0
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(self.rect()), radius, radius)
        mask = QtGui.QRegion(path.toFillPolygon().toPolygon())
        self.setMask(mask)

        # set background to transparent
        palette = QtGui.QPalette(self.palette())
        palette.setColor(palette.Background, QtCore.Qt.transparent)
        self.setPalette(palette)

        # sets fonts
        font = QtGui.QFont('Lato', 32, QtGui.QFont.Normal)
        self.setFont(font)

        # Create widgets
        self.mIcon = QtGui.QLabel()
        self.mIcon.setAlignment(QtCore.Qt.AlignCenter)
        self.mTitle = QtGui.QLabel()
        self.mContent = QtGui.QLabel()
        self.mContent.setAlignment(QtCore.Qt.AlignCenter)
        self.mButtons = {'accept': QtGui.QPushButton('ok'), 'reject': QtGui.QPushButton('cancel'), 'done': QtGui.QPushButton('done')}

        # Set dialog layout
        # Create grid layout for the MessageDialog widget and add widgets to layout
        self.mLayout = QtGui.QGridLayout()
        self.mLayout.addWidget(self.mIcon, 0, 0)
        self.mLayout.addWidget(self.mTitle, 0, 1, 1, 4)  # row, col, rowspan, colspan
        self.mLayout.addWidget(self.mContent, 1, 0, 3, 5)  # row, col, rowspan, colspan
        self.mLayout.addWidget(self.mButtons['accept'], 6, 4)
        self.mLayout.addWidget(self.mButtons['reject'], 6, 3)
        self.setLayout(self.mLayout)

        # Setup button signal to Dialog default slots
        self.mButtons['accept'].clicked.connect(self.accept)
        self.mButtons['reject'].clicked.connect(self.reject)
        self.mButtons['done'].clicked.connect(self.done)

    def paintEvent(self, event):
        painter = QtGui.QPainter()
        painter.begin(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = event.rect()

        # draw rounded rectangle the size of the event.rect() i.e. size of widget
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), 20, 20)
        pen = QtGui.QPen(QtCore.Qt.black, 10) #pen = QtGui.QPen(QtGui.QColor(15, 55, 112, 255), 10)
        painter.setPen(pen)
        # and fill it with our technexion background image
        pixmap = QtGui.QIcon(':res/images/tn_bg.svg').pixmap(QtCore.QSize(rect.width() * 4, rect.height() * 4)).scaled(QtCore.QSize(rect.width(), rect.height()), QtCore.Qt.IgnoreAspectRatio)
        brush = QtGui.QBrush(pixmap)
        painter.fillPath(path, brush)
        painter.drawPath(path)

        # painter.fillRect(rect, QtGui.QBrush(QtGui.QColor(200, 200, 200, 255)))
        painter.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        painter.end()

    def setButtonText(self, buttonTexts):
        if isinstance(buttonTexts, dict):
            for buttonRole, buttonText in buttonTexts.items():
                for role in ['accept', 'reject', 'done']:
                    if role == buttonRole:
                        if isinstance(buttonText, str):
                            self.mButtons[role].setText(buttonText)
                            self.mButtons[role].show()
                    else:
                        self.mButtons[role].hide()

    def setIcon(self, icon):
        if isinstance(icon, QtGui.QIcon):
            d = self.mRect.height() / 8 if self.mRect.height() / 8 < self.mRect.width() / 8 else self.mRect.width() / 8
            iconsize = QtCore.QSize(d, d)
            pix = icon.pixmap(QtCore.QSize(iconsize.width() * 2, iconsize.height() * 2)).scaled(iconsize, QtCore.Qt.IgnoreAspectRatio)
            self.mIcon.setPixmap(pix)
            #self.mIcon.setMask(pix.mask())
        else:
            self.clear()

    def setTitle(self, title):
        if isinstance(title, str):
            self.mTitle.setText(title)
        elif isinstance(title, QtGui.QIcon):
            d = self.mRect.height() / 8 if self.mRect.height() / 8 < self.mRect.width() / 8 else self.mRect.width() / 8
            iconsize = QtCore.QSize(d, d)
            pix = title.pixmap(QtCore.QSize(iconsize.width() * 2, iconsize.height() * 2)).scaled(iconsize, QtCore.Qt.KeepAspectRatio)
            self.mTitle.setPixmap(pix)
            #self.mIcon.setMask(pix.mask())
        elif isinstance(title, QtGui.QPixmap):
            self.mTitle.setPixmap(title)
        elif isinstance(title, QtGui.QMovie):
            self.mTitle.setMovie(title)
            title.start()
        else:
            self.clear()

    def setContent(self, content):
        if isinstance(content, str):
            self.mContent.setText(content)
        elif isinstance(content, QtGui.QIcon):
            d = self.mRect.height() / 1.5 if self.mRect.height() / 1.5 < self.mRect.width() / 1.5 else self.mRect.width() / 1.5
            iconsize = QtCore.QSize(d, d)
            pix = content.pixmap(QtCore.QSize(iconsize.width() * 2, iconsize.height() * 2)).scaled(iconsize, QtCore.Qt.KeepAspectRatio)
            self.mTitle.setPixmap(pix)
            #self.mIcon.setMask(pix.mask())
        elif isinstance(content, QtGui.QPixmap):
            self.mContent.setPixmap(content)
        elif isinstance(content, QtGui.QMovie):
            self.mContent.setMovie(content)
            content.start()
        else:
            self.clear()
