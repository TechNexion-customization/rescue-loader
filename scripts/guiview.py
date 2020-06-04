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

# guiview:
# The Qt client (guiclientd) main script for starting a Qt Gui Application
# it manages the GUI of the TechNexion Installer/Rescue system
#
# Author: Po Cheng <po.cheng@technexion.com>

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#----------------------------------------------------------
# Gui Viewer
#
# Gui Viewer that runs rescue/install GUI program on your
# target device
#
#----------------------------------------------------------

import re
import os
import sys
import signal
import socket
import serial
import logging

from guidraw import GuiDraw
from guiprocslot import QProcessSlot, QMessageDialog
from xmldict import XmlDict, ConvertXmlToDict
from defconfig import DefConfig, SetupLogging, IsATargetBoard
from messenger import BaseMessenger, SerialMessenger
from view import BaseViewer

from PyQt4 import QtCore, QtDBus, QtGui, QtSvg, QtNetwork
from PyQt4.QtCore import QObject, pyqtSignal, pyqtSlot
from threading import Event

# get the handler to the current module, and setup logging options
SetupLogging('/tmp/installer_gui.log')
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)



###############################################################################
#
# Unix OS Signal Handler / PC-Host OS Signal Handler
#
###############################################################################
class SignalHandler(QtNetwork.QAbstractSocket):
    # Normally Python capture SIGTERM and exit, but PyQt's mainloop stops that
    # hence, setup signal.SIGTERM to quit QApplication gracefully
    # This way, when system reboots, the systemd queued stop job for stopping
    # guiclientd.service wouldn't take too long.
    signalReceived = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(QtNetwork.QAbstractSocket.UdpSocket, parent)
        self.mActivatedFlag = False
        self.mNotifier = None
        self.mTimer = QtCore.QTimer(self)
        self.mOrigSignalHandlers = {}
        self.mOrigWakeupFd = None

    def activate(self, unixSignals, handlerSlot, UseTimer=False):
        """
        Set up signal handlers.
        - For OS without a Socket Pair, use a QTimer to periodically hand control
        from Qt mainloop (C++) over to Python so it can handle signals.
        - For OS with QSocketNotifier/QAbstractSocket, it uses a
        QSocketNotifier/QAbstractSocket with signal.set_wakeup_fd to get notified.
        """
        if isinstance(unixSignals, list) and len(unixSignals):
            if callable(handlerSlot):
                self.signalReceived.connect(handlerSlot)

            for sig in unixSignals:
                # setup new handler using signal.signal(), and it returns origin unix signal handler
                self.mOrigSignalHandlers[sig] = signal.signal(sig, self.interrupt)
                _logger.info('capture signal {} original handler {}'.format(sig, self.mOrigSignalHandlers[sig]))

            if IsATargetBoard():
                if not UseTimer and hasattr(signal, 'set_wakeup_fd'):
                    _logger.debug('socket pair setup')
                    # get a pair of file descriptors from creating a socket pair
                    self.wsock, self.rsock = socket.socketpair(type=socket.SOCK_DGRAM)
                    # Let Qt AbstractSocket listen on the one end
                    self.setSocketDescriptor(self.rsock.fileno())
                    # Un-blocking the write socket and let Python write on the other end
                    self.wsock.setblocking(False)
                    # Set the wakeup file descriptor to fd. When a signal is received,
                    # the signal number is written as a single byte into the fd.
                    self.mOrigWakeupFd = signal.set_wakeup_fd(self.wsock.fileno())
                    # setup the AbstractSocket's readyRead signal to handleSignalWakeup slot
                    self.readyRead.connect(lambda : None) # the first time connect generates exception
                    self.readyRead.connect(self.handleSignalWakeup)
                else:
                    # Dirty timer hack to get timer slice from mainloop (MS-Windows)
                    self.mTimer.timeout.connect(lambda: None)
                    self.mTimer.start(1000)

            self.mActivatedFlag = True

    def deactivate(self):
        """
        Deactivate all signal handlers.
        """
        if not self.mActivatedFlag:
            return

        # restore original signal handler
        for sig, origHandler in self.mOrigSignalHandlers.items():
            signal.signal(sig, origHandler)

        if IsATargetBoard():
            # Restore any old handler on deletion
            if self.mOrigWakeupFd is not None and hasattr(signal, 'set_wakeup_fd'):
                signal.set_wakeup_fd(self.mOrigWakeupFd)
            # stop the timer slicing
            self.mTimer.stop()
        self.mActivatedFlag = False

    @pyqtSlot()
    def handleSignalWakeup(self):
        """
        Handle a newly arrived signal.
        This gets called via self.mNotifier when there's a signal.
        Python will get control here, so the signal will get handled.
        """
        # Read the written byte.
        # Note: readyRead is blocked from occuring again until readData() was called,
        #       so call it, even if you don't need the value.
        data = self.readData(1)
        _logger.warning('Handling signal wakeup! read data on rsock: {}'.format(data))

    def interrupt(self, signum, stackframe):
        """
        Handler for signals to gracefully shutdown (SIGINT/SIGTERM).
        """
        if IsATargetBoard():
            data = self.readData(1)
        else:
            data = [0]
        _logger.warning('Received Unix Signal:{} read data: {}...'.format(signum, data[0]))
        # Emit a Qt signal for convenience
        self.signalReceived.emit(int(data[0]))
        # deactivate signals, so we only capture signal once
        self.deactivate()



###############################################################################
#
# DBus
#
###############################################################################

class MsgerAdaptor(QtDBus.QDBusAbstractAdaptor):
    """
    Qt DBus's Adaptor Abstraction (for Server)
    """
    QtCore.Q_CLASSINFO("D-Bus Interface", 'com.technexion.dbus.interface')
    QtCore.Q_CLASSINFO("D-Bus Introspection", ''
        '  <interface name="com.technexion.dbus.interface">\n'
        '    <method name="send">\n'
        '      <arg direction="in" type="a{sv}" name="request"/>\n'
        '      <arg direction="out" type="b" name="result"/>\n'
        '    </method>\n'
        '    <method name="status">\n'
        '      <arg direction="out" type="a{sv}" name="status"/>\n'
        '    </method>\n'
        '    <method name="result">\n'
        '      <arg direction="out" type="a{sv}" name="result"/>\n'
        '    </method>\n'
        '    <signal name="receive">\n'
        '      <arg direction="out" type="a{sv}" name="response"/>\n'
        '    </signal>\n'
        '    <method name="interrupt">\n'
        '      <arg direction="in" type="a{sv}" name="parameters"/>\n'
        '    </method>\n'
        '  </interface>\n'
        '')

    receive = QtCore.pyqtSignal(QtDBus.QDBusMessage)

    def __init__(self, parent, CbExecHdl, cbStatusHdl, cbResultHdl, CbInterruptHdl):
        super().__init__(parent)
        self.setAutoRelaySignals(True)
        self.mRetStatus = {}
        self.mStatusEvent = Event()
        self.mRetResult = {}
        self.mResultEvent = Event()
        self.mCbExecHandler = CbExecHdl
        self.mCbStatusHandler = cbStatusHdl
        self.mCbResultHandler = cbResultHdl
        self.mCbInterruptHandler = CbInterruptHdl

    @QtCore.pyqtSlot(QtDBus.QDBusMessage)
    def send(self, request):
        """
        provide sent request RPC call_method on the server
        """
        _logger.debug('qtdbus i/f send method: callback to {} with {}'.format(self.mCbExecHandler.__name__, request))
        if callable(self.mCbExecHandler):
            self.mCbExecHandler(request)
            return True
        return False

    @QtCore.pyqtSlot()
    def status(self):
        """
        provide status() RPC call_method on Qt DBus server
        """
        _logger.debug('qtdbus i/f status method: callback to {}'.format(self.mCbStatusHandler.__name__))
        if callable(self.mCbStatusHandler):
            self.mCbStatusHandler()
        return RetStatus # gets the property of RetStatus

    @property
    def RetStatus(self):
        self.mStatusEvent.clear()
        self.mStatusEvent.wait()
        return self.mRetStatus

    @RetStatus.setter
    def RetStatus(self, status):
        self.mRetStatus.clear()
        if isinstance(status, dict):
            self.mRetStatus.update(status)
        self.mStatusEvent.set()

    @QtCore.pyqtSlot()
    def result(self):
        """
        provide result() RPC call_method on Qt DBus server
        """
        if callable(self.mCbResultHandler):
            self.mCbResultHandler()
        return RetResult # gets the property of RetStatus

    @property
    def RetResult(self):
        self.mResultEvent.clear()
        self.mResultEvent.wait()
        return self.mRetResult

    @RetResult.setter
    def RetResult(self, result):
        self.mRetResult.clear()
        if isinstance(result, dict):
            self.mRetResult.update(result)
        self.mResultEvent.set()

    @QtCore.pyqtSlot(QtDBus.QDBusMessage)
    def interrupt(self, parameters):
        """
        provide interrupt() RPC call_method on Qt DBus server
        """
        param = parameters.arguments()[0]
        _logger.debug('qtdbus interrupt method: {}'.format(param))
        inputs = {}
        #called through the Dbus with parameters
        if callable(self.mCbInterruptHandler):
            inputs.update(param)
            self.mCbInterruptHandler(inputs)
            return True
        return False



class MsgerInterface(QtDBus.QDBusAbstractInterface):
    """
    Qt DBus's Interface Abstraction (for Client)
    """
    def __init__(self, busname, objpath, ifacename, connection, parent=None):
        super().__init__(busname, objpath, ifacename, connection, parent)

    def send(self, msg):
        ret = self.asyncCall('send', msg) # or self.call()
        reply = QtDBus.QDBusReply(ret)
        if reply.isValid():
            return reply.value()
        else:
            raise reply.error()

    def status(self):
        ret = self.asyncCall('status') # or self.call()
        reply = QtDBus.QDBusReply(ret)
        if reply.isValid():
            return reply.value()
        else:
            raise reply.error()

    def result(self):
        ret = self.asyncCall('result') # or self.call()
        reply = QtDBus.QDBusReply(ret)
        if reply.isValid():
            return reply.value()
        else:
            raise reply.error()

    def interrupt(self):
        ret = self.asyncCall('interrupt') # or self.call()
        reply = QtDBus.QDBusReply(ret)
        if reply.isValid():
            return reply.value()
        else:
            raise reply.error()



class QtDbusMessenger(QObject, BaseMessenger):
    """
    Qt's own version of the DBus Messenger with signals and slots
    """
    sigExecmd = QtCore.pyqtSignal(dict)
    sigStatus = QtCore.pyqtSignal()
    sigResult = QtCore.pyqtSignal()
    sigIntrpt = QtCore.pyqtSignal(dict)

    def __init__(self,  config, rootWidget, cbExecHdl = None, cbGetStatusHdl = None, cbGetResultHdl = None, cbIntrHdl = None):
        QObject.__init__(self, rootWidget)
        BaseMessenger.__init__(self, config)
        # setup the QtDBus messenger according to xml configuration
        self.mIsServer = self.mConfig['IS_SERVER'] if ('IS_SERVER' in self.mConfig.keys()) else False
        # Setup the Receive Slot Callback Function
        if callable(cbExecHdl): self.sigExecmd.connect(cbExecHdl)
        if callable(cbGetStatusHdl): self.sigStatus.connect(cbGetStatusHdl)
        if callable(cbGetResultHdl): self.sigResult.connect(cbGetResultHdl)
        if callable(cbIntrHdl): self.sigIntrpt.connect(cbIntrHdl)
        # FIXME: Need to implement callback functions to handle QtDBus server's SendSlot() and InterruptSlot()
        self.__initialize(rootWidget)

    def __initialize(self, rootWidget):
        """
        initialize this object to the DBUS connection
        """
        # get the session bus (the Qt way)
        self.mSessDBus = QtDBus.QDBusConnection.sessionBus()
        # get the dbus name, Server's obj path, and interface name
        self.mBusName = self.mConfig['busname']
        self.mObjPath = self.mConfig['srv_path']
        self.mIfaceName = self.mConfig['ifacename']
        # since the main loop of a QtApplication is running the GUI event loop,
        # we don't need to create mainloop() here
        if self.mIsServer:
            # create MsgerAdaptor (QtDBus server) with sessbus and obj path
            self.mAdapter = MsgerAdaptor(rootWidget, self.receiveMsg, self.getStatus, self.getResult, self.setInterrupt)
            self.mSessDBus.registerService(self.mBusName)
            self.mSessDBus.registerObject(self.mObjPath, self.mAdapter, QtDBus.QDBusConnection.ExportAdaptors)
            #self.mSessDBus.registerObject(self.mObjPath, self.mAdapter, QtDBus.QDBusConnection.ExportAllSlots)
        else:
            # get the server proxy object (QtDBus client), basically just create a MsgerInterface() object
            self.mIface = MsgerInterface(self.mBusName, self.mObjPath, self.mIfaceName, self.mSessDBus, rootWidget)
            # add_signal_receiver() to handle receive signals from QtDBus, the equivalent in Qt is connect()
            ret = self.mSessDBus.connect(self.mBusName, self.mObjPath, self.mIfaceName, 'receive', self.receiveMsg)
            _logger.debug('mSessBus returns: {} mSessBus connected? {} mIface isValid: {}'.format(ret, self.mSessDBus.isConnected(), self.mIface.isValid()))

    def stop(self):
        _logger.debug("shutting down dbus messenger...")
        if self.mIsServer:
            self.mSessDBus.unregisterObject(self.mObjPath)
            self.mSessDBus.unregisterService(self.mBusName)
            del self.mAdapter
        else:
            self.mSessDBus.disconnect(self.mBusName, self.mObjPath, self.mIfaceName, 'receive', self.receiveMsg)

    def hasValidConn(self):
        if self.mSessDBus.isConnected():
            return self.mIface.isValid()
        return False

    def sendMsg(self, msg):
        """
        If self is acting as a server then emits receive signal with msg, otherwise sends the message to QtDBus server
        """
        if isinstance(msg, dict):
            if self.mIsServer:
                self.mAdapter.receive.emit(msg)
            else:
                # called by the CLI/WEB/GUI viewer to send param to server
                if self.mIface and self.mIface.isValid():
                    return self.mIface.send(msg)
                else:
                    raise ReferenceError('Unable to access DBUS exported object')
        else:
            raise TypeError('Message has to be packaged in a dictionary.')

    @QtCore.pyqtSlot(QtDBus.QDBusMessage)
    def receiveMsg(self, response):
        """
        signal handler for the receiving receive() signal from QtDBus Server
        """
        resp = response.arguments()[0]
        params = {}
        params.update(resp)
        # emit recv signal which connects to cbReceiveSlotHandle callback handler
        self.sigExecmd.emit(params)

    def setInterrupt(self, param):
        """
        allow the client to setInterrupt to the QtDBus server via emit intr signal
        which calls back to cbInterruptSlotHandle
        """
        if isinstance(param, dict):
            if self.mIsServer:
                # called by the QtDBus Adaptor to emit the signal to set interrupt
                self.sigIntrpt.emit(param)
            else:
                # called by the CLI/WEB/GUI viewer to interrupt server jobs
                if self.mIface and self.mIface.isValid():
                    return self.mIface.interrupt(param)
                else:
                    raise ReferenceError('Unable to access DBUS exported object')
        else:
            raise TypeError('Interrupt Param has to be packaged in a dictionary')

    @pyqtSlot(dict)
    def setStatus(self, status):
        """
        Update the status within QtDBus Server
        and emit receive to client with the status
        """
        if self.mIsServer:
            if isinstance(status, dict):
                # calls property setter to set the status
                self.mAdapter.RetStatus = status
                # call sendMsg to emit receive() to signal client with status
                self.sendMsg(status)
            else:
                raise TypeError('Setting status must pass in a dictionary format')
        else:
            raise IOError("This method call is for dbus server only!")

    def getStatus(self):
        """
        Gets the status from QtDBus Server
        """
        if self.mIsServer:
            # called by the QtDBus Adaptor to emit sigStatus signal to get status,
            # whoever is signaled, need to callback to setStatus() slot to update the status
            self.sigStatus.emit()
        else:
            # called by the CLI/WEB/GUI viewer to ask DBus server for current status
            if self.mIface and self.mIface.isValid():
                retStatus = {}
                retStatus.update(self.mIface.status())
                return retStatus
            else:
                raise ReferenceError('Unable to access DBUS exported object')

    @pyqtSlot(dict)
    def setResult(self, result):
        """
        Update the result within QtDBus Server
        and emit receive to client with the results
        """
        if self.mIsServer:
            if isinstance(result, dict):
                self.mAdapter.RetResult = result
                # call sendMsg to emit receive() to signal client with result
                self.sendMsg(result)
            else:
                raise TypeError('Setting result must pass in a dictionary format')
        else:
            raise IOError("This method call is for dbus server only!")

    def getResult(self):
        """
        Gets the result from QtDBus Server
        """
        if self.mIsServer:
            # called by the QtDBus Adaptor to emit sigResult signal to get result,
            # whoever is signaled, need to callback to setResult() slot to update the results
            self.sigResult.emit()
        else:
            # called by the CLI/WEB/GUI viewer to ask DBus server for current result
            if self.mIface and self.mIface.isValid():
                retResults = {}
                retResults.update(self.mIface.result())
                return retResults
            else:
                raise ReferenceError('Unable to access DBUS exported object')



###############################################################################
#
# MsgDispatcher to store viewer/msger/sender/cmd in DispatchQ
#
###############################################################################
class MsgDispatcher(QObject):

    respSignal = QtCore.pyqtSignal(dict)

    def __init__(self, viewer, msger, sender, reqMsg):
        QObject.__init__(self)
        """
        called by signals from other GObject components
        To be overriden by all sub classes
        """
        self.mMsgCmd = {}
        self.mViewer = None
        self.mMsger = None
        self.mSender = None
        self.mDoneFlag = False
        try:
            if viewer is not None and isinstance(viewer, GuiViewer) and \
                    isinstance(msger, BaseMessenger) and \
                    isinstance(sender, QProcessSlot) and \
                    isinstance(reqMsg, dict):
                self.mViewer = viewer
                self.mMsger = msger
                self.mSender = sender
                self.mSender.finish.connect(self._reqCompleted)
                if hasattr(self.mSender, 'resultSlot'):
                    # connect signal to sender's resultSlot
                    self.respSignal.connect(self.mSender.resultSlot)
                self.mMsgCmd.update(reqMsg)
            else:
                raise ValueError('Invalid Parameters')
        except:
            raise

    def matchAndSend(self, respMsg):
        #if (set(respMsg.items()) & set(self.mMsgCmd.items())) == set(respMsg.items()):
        if dict(respMsg, **self.mMsgCmd) == respMsg:
            _logger.warn('signal response to GUI {}: {}'.format(self.mSender.Name(), respMsg))
            # dict of cmd and results is the same as results, means cmd is already in results
            self.respSignal.emit(respMsg)

    @pyqtSlot()
    def _reqCompleted(self):
        self.mDoneFlag = True



###############################################################################
#
# GuiViewer
#
###############################################################################

class GuiViewer(QObject, BaseViewer):
    """
    GuiViewer - setting up of any gui elem defined in XML (qt ui ver 4 format)

    For Displaying GUI elements on the target device
    It is the top most GUI class/object that handles display of all
    the sub-contained GUI elements

    The sub-contained GUI elements are defined in the installer.xml
    configuration file. The idea is to provide genericity for
    controlling what the UI of the installer looks like, thus
    allowing some degree of customization to the installer GUI system.
    """
    responseSignal = QtCore.pyqtSignal(dict)

    def __init__(self, confname = None, orient = 'landscape'):
        """
        Setup the Gui Elem according to 2 categories,
        1. GuiDraws, 2. Customised Slots.
        GuiDraws - responsible for the UI display
        Customised Slots - responsible for handling user inputs,
                           additional logics, and parse results
        """
        QObject.__init__(self)
        BaseViewer.__init__(self)
        self.mCmd = {}
        self.mMoreInputs = {}
        self.mGuiRootWidget = None
        self.mGuiRootSignals = []
        self.mMsger = []
        self.mDispatchQ = []

        # parse the configuration as well as setup the GUI components
        if os.path.isfile(os.path.realpath(confname) + '/' + confname):
            self.mUiConfDict = ConvertXmlToDict(confname)
            self.__parseConf(self.mUiConfDict)
        else:
            self.mConfDict = self.mDefConfig.getSettings('gui_viewer')
            self.__parseConf(self.mConfDict['gui_viewer'][orient])

        # setup DBus Messenger after all GUI components are setup
        self.__setupMsger()
        # emit initialize signal to UI components which are setup to receive them
        self.__emitInitSignal()
        # used to sequentialize QProcessSlot's request
        self._setEvent()

    def stop(self):
        for mgr in self.mMsger:
            mgr.stop()
            QtCore.QCoreApplication.instance().quit()

    def __setupMsger(self):
        """
        get the DefConfig, and create mMsger as the dbus client with the root widget
        and self.response callback function
        """
        conf = self.mDefConfig.getSettings(flatten=True)
        try:
            if not IsATargetBoard():
                _logger.info('add SerialMessager')
                self.mMsger.append(SerialMessenger(conf, self.response))
                self.mMsger[-1].run()
        except Exception as ex:
            _logger.error('Cannot start a serial messenger. Error:{}'.format(ex))
        _logger.info('add QtDbusMessenger')
        self.mMsger.append(QtDbusMessenger(conf, self.mGuiRootWidget, self.response))

    def checkDbusConn(self):
        for mgr in self.mMsger:
            if isinstance(mgr, QtDbusMessenger):
                return mgr.hasValidConn()
        return False

    def getConnType(self, mgr):
        if isinstance(mgr, QtDbusMessenger):
            return "dbus"
        elif isinstance(mgr, SerialMessenger):
            return "serial"
        return None

    def getRemoteHostUrl(self):
        if self.mDefConfig:
            prot = self.mDefConfig.getSettings('host_protocol')
            host = self.mDefConfig.getSettings('host_name')
            if prot and host:
                return '{}://{}'.format(prot['host_protocol'], host['host_name'])
        return None

    def getRemoteHostDir(self):
        hostdir = None
        if self.mDefConfig:
            hostdir = self.mDefConfig.getSettings('host_dir')
        return '/{}/'.format(hostdir['host_dir']) if hostdir else None

    def getRemoteHostUrls(self):
        if self.mDefConfig:
            conf = self.mDefConfig.getSettings('rescue')
            if isinstance(conf['rescue'], dict) and 'host' in conf['rescue'].keys():
                return conf['rescue']['host'] if isinstance(conf['rescue']['host'], list) else [(conf['rescue']['host'])]
        return None

    ###########################################################################
    # PyQt GUI related
    ###########################################################################
    def __parseConf(self, confdict):
        """
        Parsed the XML configuration from /etc/installer.xml or installer.ui
        """
        if 'app_name' in confdict:
            self.mAppName = confdict['app_name']
        if 'ui' in confdict  and confdict['ui']['version'] == "4.0":
            if 'customwidgets' in confdict['ui']:
                # import and validate the customewidgets
                ret = self.__validateCustomWidget(confdict['ui']['customwidgets']['customwidget'])
            if ret and 'widget' in confdict['ui']:
                # starting from top level widget
                self.__setupUI(confdict['ui']['widget'])
            if 'slots' in confdict['ui']:
                # validate the Ui slots for the top most widget/application
                ret = self.__validateUiSlots(confdict['ui']['slots'])
            if ret and 'connections' in confdict['ui']:
                # finally setup Qt signals and slots
                self.__setupConnection(confdict['ui']['connections']['connection'])

    def __validateCustomWidget(self, confdict):
        """
        The custom widgets is really used for defining custom widgets for the Qt Designer system.

        Probably just do checking or validating here to ensure that
        the program can be executed in sync according to QtDesigner's
        .UI configuration file's xml definitions, for example

            <customwidgets>
                <customwidget>
                    <class>QProcessSlot</class>
                    <extends>QWidget</extends>
                    <header>qprocessslot.h</header>
                    <container>1</container>
                    <slots>
                        <signal>processComplete()</signal>
                        <slot>process()</slot>
                    </slots>
                </customwidget>
            </customwidgets>

        class = the custom class (should exist in GuiDraw's subclasses)
        extends = we can check custom class to see if it is an instance of extends class
        header = suppose to be the C header file that defines the class, ignored here
        container = true or false
        slots = defines the signal name and slot method for the custom class,
                we must check if these signals/slots are available in our python class
        """
        def check_custom_widget(cconf):
            def get_all_subclasses(c):
                all_subclasses = []
                for subclass in c.__subclasses__():
                    all_subclasses.append(subclass)
                    all_subclasses.extend(get_all_subclasses(subclass))
                return all_subclasses

            for subcls in get_all_subclasses(QtGui.QWidget):
                if cconf['class'] == subcls.__name__:
                    subcls = subcls
                    if 'slots' in cconf:
                        slotlist = cconf['slots']['slot'] if isinstance(cconf['slots']['slot'], list) else [cconf['slots']['slot']]
                        if all([hasattr(subcls, slot.rstrip('()')) for slot in slotlist]):
                            return True
                    else:
                        return True
            return False

        customlist = []
        if isinstance(confdict, list):
            # loop through each customwidget to see if we have them supported
            # in the python class definitions
            customlist.extend(confdict)
        elif isinstance(confdict, XmlDict):
            # check if the custom widget is supported in the python class definition,
            # also check for <slots> definitions which is a must to ensure correct
            # operations defined in the .UI File
            customlist.append(confdict)

        for customconf in customlist:
            if not all([check_custom_widget(customconf)]):
                _logger.error('Not All Custom Widget Classes are supported')
                return False
        return True

    def __setupUI(self, confdict, parent = None):
        """
        Setup the UI hierarchical xml elements specified in QtDesigner ui file
        """
        # if root element, ie. no parent, setup specific way
        if parent is None:
            # set the root Gui elem
            parent = GuiDraw.GenGuiDraw(confdict)
            self.mGuiRootWidget = parent
            if IsATargetBoard():
                # Window Additional Flags
                self.mGuiRootWidget.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint) #QtCore.Qt.SplashScreen | QtCore.Qt.WindowStaysOnTopHint)
            else:
                self.mGuiRootWidget.setWindowFlags(QtCore.Qt.WindowCloseButtonHint)
                self.mGuiRootWidget.setAttribute(QtCore.Qt.WA_DeleteOnClose)
                self.mGuiRootWidget.finished.connect(self.stop)
        else:
            # takes the old parent, and return itself as the new parent
            parent = GuiDraw.GenGuiDraw(confdict, parent)

        # recursively create all GUI elements but ignoring 'property' and 'attribute'
        for tag in ['widget', 'layout', 'item', 'action']:
            if tag in confdict.keys():
                # ensure confdict[tag] into a list
                entrylist = []
                if isinstance(confdict[tag], XmlDict):
                    entrylist.append(confdict[tag])
                elif isinstance(confdict[tag], list):
                    entrylist.extend(confdict[tag])

                # iterate each item entry and recursive call to create it
                for entry in entrylist:
                    if tag == 'action':
                        # setup actions, i.e. QAction here
                        entry.update({'class': 'QAction'})
                        self.__setupUI(entry, self.mGuiRootWidget)
                    elif 'class' in entry.keys() and entry['class'] == 'QProcessSlot':
                        # setup other customized cases, i.e. QProcessSlot, subclasses here
                        self.__setupUI(entry, self.mGuiRootWidget)
                    elif 'class' in entry.keys() and 'name' in entry.keys():
                        # setup other GUI element where a class and a name is set
                        self.__setupUI(entry, parent)
                    elif tag == 'item':
                        # setup layout's item
                        # DIRTY HACK!!! extract item's attributes and setup layout's item with it
                        passparam = {}
                        passparam.update(entry)
                        if 'widget' in entry.keys():
                            passparam.pop('widget', None)
                            entry['widget'].update(passparam)
                            self.__setupUI(entry['widget'], parent)
                        elif 'layout' in entry.keys():
                            passparam.pop('layout', None)
                            entry['layout'].update(passparam)
                            self.__setupUI(entry['layout'], parent)
                    else:
                        # Other fall-through cases
                        for k in entry.keys():
                            if isinstance(entry[k], XmlDict) and 'class' in entry[k].keys() and 'name' in entry[k].keys():
                                _logger.warning('Setup fall through GUI XML entry[{}]: {}'.format(k, entry[k]))
                                self.__setupUI(entry[k], parent)
                            else:
                                _logger.warning('Warning: parsing unrecognised GUI XML entry[{}]: {}'.format(k, entry[k]))
                                # raise RuntimeError('Error Parsing the GUI Xml')

    def __validateUiSlots(self, confdict):
        """
        Validate that the root widget has the appropriate signal defined.
        """
        for k, v in confdict.items():
            if k == 'signal':
                if isinstance(v, dict):
                    self.mGuiRootSignals.extend(v)
                else:
                    self.mGuiRootSignals.append(v)
        if all([hasattr(self.mGuiRootWidget, i.rstrip('()')) for i in self.mGuiRootSignals]):
            return True
        else:
            return False

    def __setupConnection(self, confdict, parent=None):
        """
        Traverse the connections xml tags, and setup the signal and slots specified in QtDesigner

        For example,
            <connections>
                <connection>
                    <sender>pushButtonCmd</sender>
                    <signal>clicked()</signal>
                    <receiver>progressBarStatus</receiver>
                    <slot>update()</slot>
                    <hints>
                        <hint type="sourcelabel">
                            <x>590</x>
                            <y>438</y>
                        </hint>
                        <hint type="destinationlabel">
                            <x>590</x>
                            <y>469</y>
                        </hint>
                    </hints>
                </connection>
            </connections>

        sender = the name of the Gui Element
        signal = the signal name
        receiver = the object that contains the Slot() method
        slot = the actual method name
        hints = QtDesigner graphics parameters and are ignored here
        """
        def setup_signals(cfdict):
            if cfdict['sender'] in GuiDraw.clsGuiDraws.keys():
                sender = GuiDraw.clsGuiDraws[cfdict['sender']]
                signalName = re.sub('\(.*\)', '', cfdict['signal'])
                slotName = re.sub('\(.*\)', '', cfdict['slot'])
                if hasattr(sender, signalName):
                    if cfdict['receiver'] in GuiDraw.clsGuiDraws.keys():
                        receiver = GuiDraw.clsGuiDraws[cfdict['receiver']]
                        if hasattr(receiver, slotName):
                            getattr(sender, signalName).connect(getattr(receiver, slotName))
                            _logger.info("connect {}.{} to {}.{}".format(sender.objectName(), signalName, receiver.objectName(), slotName))
                    else:
                        if hasattr(self.__module__, slotName):
                            getattr(sender, signalName).connect(getattr(self.__module__, slotName))
                            _logger.info("connect {}.{} to {}.{}".format(sender.objectName(), signalName, self.__module__, slotName))

        if isinstance(confdict, list):
            for conn in confdict:
                setup_signals(conn)
        elif isinstance(confdict, XmlDict):
            setup_signals(confdict)

    def __emitInitSignal(self):
        """
        (Last Step) Emit the signals defined for the root gui element, passing
        the viewer reference to the QProcessSlots, allowing GUI elements to
        to setup their request signal to viewer's request. As well as start
        the web crawling and storage discovery
        """
        for s in self.mGuiRootSignals:
            signalName = re.sub('\(.*\)', '', s)
            if hasattr(self.mGuiRootWidget, signalName):
                # root widget's initialised.emit() signal passing {'viewer': self} to all defined QProcessSlots
                getattr(self.mGuiRootWidget, signalName)[dict].emit({'viewer': self})
                _logger.info("emit {}.{}, # connected slots:{}".format(self.mGuiRootWidget.objectName(), signalName, self.mGuiRootWidget.receivers(QtCore.SIGNAL("initialised(PyQt_PyObject)"))))



    ###########################################################################
    # GuiViewer flow control related
    ###########################################################################
    def show(self, scnRect):
        if isinstance(self.mGuiRootWidget, QtGui.QWidget):
            palette = QtGui.QPalette(self.mGuiRootWidget.palette())
            pixmap = QtGui.QIcon(':res/images/tn_bg.svg').pixmap(QtCore.QSize(scnRect.width() * 4, scnRect.height() * 4)).scaled(QtCore.QSize(scnRect.width(), scnRect.height()), QtCore.Qt.IgnoreAspectRatio)
            brush = QtGui.QBrush(pixmap)
            palette.setBrush(QtGui.QPalette.Background, brush)
            self.mGuiRootWidget.setPalette(palette)
            self.mGuiRootWidget.setGeometry(scnRect)

            # set the tabTitle widget so that the layout can then be calculated automatically.
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabTitle').setFixedHeight(int(scnRect.height() / 4))
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabSpace').setFixedHeight(int(scnRect.height() / 24))
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabOS').setFixedHeight(int(scnRect.height() / 16 * 9))
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabBoard').setFixedHeight(int(scnRect.height() / 16 * 9))
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabDisplay').setFixedHeight(int(scnRect.height() / 16 * 9))
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabStorage').setFixedHeight(int(scnRect.height() / 16 * 9))
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabInstall').setFixedHeight(int(scnRect.height() / 16 * 9))
            #self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabFooter').setFixedHeight(int(scnRect.height() / 16))
            # Set the geometry of the message box to slightly smaller than application geomtry
            dialogrect = QtCore.QRect(int(scnRect.width() / 16), int(scnRect.height() / 16), int(scnRect.width() - (scnRect.width() / 8)), int(scnRect.height() - (scnRect.height() / 8)))
            self.mGuiRootWidget.findChild(QtGui.QDialog, 'msgbox').setGeometry(dialogrect)
            self.mGuiRootWidget.show()

            # setup the icon size for QListWidgets
            w = scnRect.width() if scnRect.width() < scnRect.height() else scnRect.height()
            d = w / 3.5 if (w / 3.5) > 50 else 50
            # 50x50 pixels are the icon default size
            iconsize = QtCore.QSize(d, d)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtOS').setIconSize(iconsize)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtOS').setSpacing(w / 14)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtBoard').setIconSize(iconsize)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtBoard').setSpacing(w / 14)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtDisplay').setIconSize(iconsize)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtDisplay').setSpacing(w / 14)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtStorage').setIconSize(iconsize)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtStorage').setSpacing(w / 14)

            # draw logo according to scale
            iconLogo = QtGui.QIcon(':/res/images/tn_logo.svg')
            iconSize = iconLogo.actualSize(QtCore.QSize(100, 100))
            sizeLogo = QtCore.QSize(self.mGuiRootWidget.findChild(QtGui.QWidget, 'lblLogo').size())
            logoW = sizeLogo.width()
            logoH = int(iconSize.height() * (logoW / iconSize.width()))
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lblLogo').setPixmap(iconLogo.pixmap(logoW, logoH))

            # work out the proportion to the selection icons
            sizeSelect = self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtSelection').size()
            sh = int(sizeSelect.width() / 4 * 0.8)
            smalliconsize = QtCore.QSize(sh, sh)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtSelection').setIconSize(smalliconsize)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtSelection').setSpacing(smalliconsize.width()/24)

            # set font size
            fontsize = int(w/50)
            _logger.warning('fontsize = {}'.format(fontsize))
            self.mGuiRootWidget.setFont(QtGui.QFont('Lato', fontsize))
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'btnFlash').setFont(QtGui.QFont('Lato', fontsize * 2))

            # Show/Hide additional Widgets
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'progressBarStatus').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lblRemaining').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lblDownloadFlash').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabBoard').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabDisplay').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabStorage').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabInstall').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'waitingIndicator').hide()

    ###########################################################################
    # BaseViewer related
    ###########################################################################
    def _parseCmd(self, params):
        # GuiWidget will issue a command, which is parsed here

        # do the user commands checking here, and convert it into proper
        # recognizable dictionary to send to the dbus server
        self.mCmd.clear()

        if 'cmd' in params.keys():
            # FORMAT for server parsing dictionary
            # {cmd: {options}}
            if 'verbose' in params and params.pop('verbose'):
                params.update({'verbose': 'True'})
            else:
                params.update({'verbose': 'False'})
            if 'interactive' in params:
                params.pop('interactive')
                params.update({'interactive': 'True'})
            if params['cmd'] is None:
                params.pop('cmd')
            #self.mCmd.update({params.pop('cmd'): params})
            self.mCmd.update(params)
        if len(self.mCmd) > 0:
            return True
        else:
            return False

    def _mainExec(self):
        """
        override BaseViewer::_mainExec()
        Send the actual dbus commands
        """
        try:
            if isinstance(self.mCmd, dict):
                mgr = self.mMsger[int(self.mCmd['msger_id'])]
                ret = mgr.sendMsg(self.mCmd)
#                 if isinstance(mgr, QtDbusMessenger):
#                     _logger.debug('send cmd via DBus: {} ret: {}'.format(self.mCmd, ret))
#                 elif isinstance(mgr, SerialMessenger):
#                     _logger.debug('send cmd via Serial: {} ret: {}'.format(self.mCmd, ret))
                return ret
            else:
                raise TypeError('cmd must be in a dictionary format')
#         except QtDBus.QDBusError as err:
#             _logger.error('QtDBus Error: {}'.format(err))
        except serial.serialutil.SerialException as err:
            _logger.error('Serial Error: {}'.format(err))
        except (IOError, TypeError, ReferenceError, Exception) as err:
            _logger.error('Error: {}'.format(err))
        return False

    def _postExec(self):
        mgr = self.mMsger[int(self.mCmd['msger_id'])]
        # if the new self.mCmd match previously send command, don't append to dispatch queue
        for q in self.mDispatchQ:
            if dict(q.mMsgCmd, **self.mCmd) == q.mMsgCmd:
                _logger.warn("cmd already exist in queue: {}".format(self.mCmd))
                return False
        _logger.warn("send and append cmd to queue: {}".format(self.mCmd))
        self.mDispatchQ.append(MsgDispatcher(self, mgr, self.sender(), self.mCmd))
        return True

    @QtCore.pyqtSlot(dict)
    def request(self, arguments):
        """
        A slot called by QProcessSlot's signals to handles command requests which then goes to QtDBus
        1. update the arguments dictionary
        2. parse the command params
        3. pre-execute the command, ensure results goes back to sender when response comes back from QtDBus
        4. execute the command
        5. post-exectue if execute command was successful
        """
        params = {}
        params.update(arguments)
        self._waitForEventTimeout(None)
        self._clearEvent()
        # execute parsed commands
        if self._parseCmd(params):
            for msger_id, mgr in enumerate(self.mMsger, start=0):
                self.mCmd.update({'msger_id': '{}'.format(msger_id), 'msger_type': self.getConnType(mgr), 'total_mgrs': '{}'.format(len(self.mMsger))})
                if (self._preExec()):
                    if (self._mainExec()):
                        self._postExec()
        self._setEvent()

    @QtCore.pyqtSlot(dict)
    def response(self, result):
        """
        This slot handles all the dbus receive signal messages from QtDbus

        Check what has come back from the server, and distribute the results
        to appropriate GUI elements / ProcessSlot accordingly
        """
        retResult = {}
        retResult.update(self._unflatten(result))
        if self._parseResult(retResult):
            for q in self.mDispatchQ:
                q.matchAndSend(retResult)
        else:
            _logger.debug('dropped response from messenger: {}'.format(retResult))

    def _parseResult(self, response):
        # do the result parsing here, and convert it into proper
        # recognizable dictionary to send to the receiving slots
        _logger.debug('parse response from messenger: {}'.format(response))
        # extract the result, and parse the result from server
        if isinstance(response, dict) and 'status' in response:
            if response['status'] in ['processing', 'success', 'failure']:
                return True
        return False

    def queryResult(self, msger_type):
        # get results returned from 'dbus' or 'serial' specified
        result = {}
        for mgr in self.mMsger:
            if self.getConnType(mgr) == msger_type:
                result.update(mgr.getResult())
        return result



def guiview():
    app = QtGui.QApplication(sys.argv)
    sighdl = SignalHandler(app)
    geo = app.desktop().screenGeometry()
    orient = 'landscape' if geo.width() > geo.height() else 'portrait'
    view = GuiViewer(sys.argv[-1], orient)
    sighdl.activate([signal.SIGINT, signal.SIGTERM, signal.SIGUSR1], view.stop)
    view.show(geo)

    try:
        sys.exit(app.exec_())
    except KeyboardInterrupt:
        sys.exit(-1)

if __name__ == '__main__':
    guiview()
