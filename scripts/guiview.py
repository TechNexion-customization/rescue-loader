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
import logging
import defconfig

from guidraw import GuiDraw
from guiprocslot import QMessageDialog
from xmldict import XmlDict, ConvertXmlToDict
from defconfig import DefConfig, SetupLogging
from messenger import BaseMessenger
from view import BaseViewer

from PyQt4 import QtCore, QtDBus, QtGui, QtSvg, QtNetwork
from PyQt4.QtCore import QObject, pyqtSignal, pyqtSlot

# get the handler to the current module, and setup logging options
SetupLogging('/tmp/installer_gui.log')
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)



###############################################################################
#
# Signal Handler
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

        # Restore any old handler on deletion
        if self.mOrigWakeupFd is not None and hasattr(signal, 'set_wakeup_fd'):
            signal.set_wakeup_fd(self.mOrigWakeupFd)

        # restore original signal handler
        for sig, origHandler in self.mOrigSignalHandlers.items():
            signal.signal(sig, origHandler)

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
        data = self.readData(1)
        _logger.warning('Received Unix Signal:{} read data: {}...'.format(signum, data[0]))
        # Emit a Qt signal for convenience
        self.signalReceived.emit(int(data[0]))



###############################################################################
#
# DBus
#
###############################################################################

class MsgerAdaptor(QtDBus.QDBusAbstractAdaptor):
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
        '    <signal name="receive">\n'
        '      <arg direction="out" type="a{sv}" name="response"/>\n'
        '    </signal>\n'
        '    <method name="quit">\n'
        '      <arg direction="out" type="a{sv}" name="quit"/>\n'
        '    </method>\n'
        '  </interface>\n'
        '')

    receive = QtCore.pyqtSignal(QtDBus.QDBusMessage)

    def __init__(self, parent):
        super().__init__(parent)
        self.setAutoRelaySignals(True)
        self.mRetStatus = {}
        self.mRetResult = {}

    @QtCore.pyqtSlot(QtDBus.QDBusMessage)
    def send(self, request):
        """
        provide sent request RPC call_method on the server
        """
        req = request.arguments()[0]
        _logger.debug('qtdbus send method: {}'.format(req))
        params = {}
        #called through the Dbus with request
        if callable(self.mCbExecHandler):
            # parse the serialized second string back to dict
            params.update(req)
            self.mCbExecHandler(params)
            return True
        return False

    @QtCore.pyqtSlot()
    def status(self):
        return self.mRetStatus

    @property
    def Status(self):
        return self.mRetStatus

    @Status.setter
    def Status(self, status):
        if isinstance(status, dict):
            self.mRetStatus.update(status)
            self.send(self.mRetStatus)
        else:
            self.mRetStatus.clear()

    @QtCore.pyqtSlot()
    def result(self):
        return self.mRetResult

    @property
    def Result(self):
        return self.mRetResult

    @Result.setter
    def Result(self, result):
        # called by the Installer server to set param to server
        if isinstance(result, dict):
            self.mRetResult.update(result)
            self.send(self.mRetResult)
        else:
            self.mRetResult.clear()


class MsgerInterface(QtDBus.QDBusAbstractInterface):

    def __init__(self, busname, objpath, ifacename, connection, parent=None):
        super().__init__(busname, objpath, ifacename, connection, parent)

    def send(self, msg):
        ret = self.asyncCall('send', msg) # or self.call()
        reply = QtDBus.QDBusReply(ret)
        if reply.isValid():
            return reply.value()
        else:
            return False

    def status(self):
        ret = self.asyncCall('status') # or self.call()
        reply = QtDBus.QDBusReply(ret)
        if reply.isValid():
            return reply.value()
        else:
            return None

    def result(self):
        ret = self.asyncCall('result') # or self.call()
        reply = QtDBus.QDBusReply(ret)
        if reply.isValid():
            return reply.value()
        else:
            return None

    def quit(self):
        ret = self.asyncCall('quit') # or self.call()
        reply = QtDBus.QDBusReply(ret)
        if reply.isValid():
            return reply.value()
        else:
            return None



class QtDbusMessenger(QObject, BaseMessenger):

    done = QtCore.pyqtSignal(dict)

    def __init__(self,  config, rootWidget, cbSlotHandle = None):
        QObject.__init__(self, rootWidget)
        BaseMessenger.__init__(self, config)
        self.mIsServer = self.mConfig['IS_SERVER'] if ('IS_SERVER' in self.mConfig.keys()) else False
        if callable(cbSlotHandle):
            self.done.connect(cbSlotHandle)
        self.__initialize(rootWidget)

    def __initialize(self, rootWidget):
        """
        initialize this object to the DBUS connection
        """
        # get the session bus Qt way
        self.mSessDBus = QtDBus.QDBusConnection.sessionBus()
        # get the dbus name, Server's obj path, and interface name
        self.mBusName = self.mConfig['busname']
        self.mObjPath = self.mConfig['srv_path']
        self.mIfaceName = self.mConfig['ifacename']
        # since the main loop of a QtApplication is running the GUI event loop,
        # we don't need to create mainloop() here
        if self.mIsServer:
            # new MsgerAdaptor constructor with sessbus and obj path
            self.mAdapter = MsgerAdaptor(rootWidget)
            self.mSessDBus.registerService(self.mBusName)
            self.mSessDBus.registerObject(self.mObjPath, self.mAdapter, QtDBus.QDBusConnection.ExportAdaptors)
            #self.mSessDBus.registerObject(self.mObjPath, self.mAdapter, QtDBus.QDBusConnection.ExportAllSlots)
        else:
            # get the server proxy object, basically just new an MsgerInterface() object
            self.mIface = MsgerInterface(self.mBusName, self.mObjPath, self.mIfaceName, self.mSessDBus, rootWidget)
            # add_signal_receiver(), equivalent in Qt is connect()
            ret = self.mSessDBus.connect(self.mBusName, self.mObjPath, self.mIfaceName, 'receive', self.receiveMsg)
            _logger.debug('mSessBus returns: {} mSessBus connected? {} mIface isValid: {}'.format(ret, self.mSessDBus.isConnected(), self.mIface.isValid()))

    def hasValidDbusConn(self):
        if self.mSessDBus.isConnected():
            return self.mIface.isValid()
        return False

    def sendMsg(self, msg):
        """
        If self is acting as a server then emits signal, otherwise sends the message
        """
        if isinstance(msg, dict):
            if self.mIsServer:
                self.mAdapter.receive.emit(msg) # call receive() to signal client with msg
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
        signal handler for the receive() signal from server
        """
        resp = response.arguments()[0]
        params = {}
        params.update(resp)
        self.done.emit(params)

    def getStatus(self):
        """
        Gets the status from DBus Server
        """
        retStatus = {}
        if not self.mIsServer:
            # called by the CLI/WEB/GUI viewer to ask server for current status
            if self.mIface and self.mIface.isValid():
                retStatus.update(self.mIface.status())
                return retStatus
            else:
                raise ReferenceError('Unable to access DBUS exported object')
        else:
            raise IOError("This method call is for dbus client only!")

    def setStatus(self, status):
        if self.mIsServer:
            if isinstance(status, dict):
                self.mAdapter.Status = status
            else:
                raise TypeError('Setting status must pass in a dictionary format')
        else:
            raise IOError("This method call is for dbus server only!")

    def getResult(self):
        """
        Gets the status from DBus Server
        """
        retResults = {}
        if not self.mIsServer:
            # called by the CLI/WEB/GUI viewer to ask server for current status
            if self.mIface and self.mIface.isValid():
                retResults.update(self.mIface.result())
                return retResults
            else:
                raise ReferenceError('Unable to access DBUS exported object')
        else:
            raise IOError("This method call is for dbus client only!")

    def setResult(self, result):
        if self.mIsServer:
            if isinstance(result, dict):
                self.mAdapter.Result = result
            else:
                raise TypeError('Setting result must pass in a dictionary format')
        else:
            raise IOError("This method call is for dbus server only!")



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

    def __init__(self, confname=''):
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
        if confname:
            self.mUiConfDict = ConvertXmlToDict(confname)
            self.__parseConf(self.mUiConfDict)
        else:
            self.mConfDict = self.mDefConfig.getSettings('gui_viewer')
            self.__parseConf(self.mConfDict['gui_viewer'])
        self.__setupMsger()

        # signal once after 1000ms to do initialisation checking
        QtCore.QTimer.singleShot(1000, self.__initialCheck)

    def __setupMsger(self):
        # check the DefConfig, and create mMsger as the dbus client
        conf = self.mDefConfig.getSettings(flatten=True)
        self.mMsger = QtDbusMessenger(conf, self.mGuiRootWidget, self.response)

    ###########################################################################
    # PyQt GUI related
    ###########################################################################
    def __parseConf(self, confdict):
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
                # validate the slots for the top most widget/application
                ret = self.__validateSlots(confdict['ui']['slots'])
            if ret and 'connections' in confdict['ui']:
                self.__setupConnection(confdict['ui']['connections']['connection'])

    def __validateCustomWidget(self, confdict):
        # The custom widgets is really used for defining custom widgets
        # for the Qt Designer system.
        #
        # Probably just do checking or validating here to ensure that
        # the program can be executed in sync according to QtDesigner's
        # .UI configuration file's xml definitions, for example
        #
        #     <customwidgets>
        #         <customwidget>
        #             <class>QProcessSlot</class>
        #             <extends>QWidget</extends>
        #             <header>qprocessslot.h</header>
        #             <container>1</container>
        #             <slots>
        #                 <signal>processComplete()</signal>
        #                 <slot>process()</slot>
        #             </slots>
        #         </customwidget>
        #     </customwidgets>
        #
        # class = the custom class (should exist in GuiDraw's subclasses)
        # extends = we can check custom class to see if it is an instance of extends class
        # header = suppose to be the C header file that defines the class, ignored here
        # container = true or false
        # slots = defines the signal name and slot method for the custom class,
        #         we must check if these signals/slots are available in our python class
        #
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

    def __setupUI(self, confdict, parent=None):
        # if root element, ie. no parent, setup specific way
        if parent is None:
            # set the root Gui elem
            parent = GuiDraw.GenGuiDraw(confdict)
            self.mGuiRootWidget = parent
            # Window Additional Flags
            self.mGuiRootWidget.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint) #QtCore.Qt.SplashScreen | QtCore.Qt.WindowStaysOnTopHint)
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

    def __validateSlots(self, confdict):
        # Validate that the root widget has the appropriate signal defined.
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
        # Loop the connections, and setup the signal and slots designed in QtDesigner
        #
        # For example,
        #     <connections>
        #         <connection>
        #             <sender>pushButtonCmd</sender>
        #             <signal>clicked()</signal>
        #             <receiver>progressBarStatus</receiver>
        #             <slot>update()</slot>
        #             <hints>
        #                 <hint type="sourcelabel">
        #                     <x>590</x>
        #                     <y>438</y>
        #                 </hint>
        #                 <hint type="destinationlabel">
        #                     <x>590</x>
        #                     <y>469</y>
        #                 </hint>
        #             </hints>
        #         </connection>
        #     </connections>
        #
        # sender = the name of the Gui Element
        # signal = the signal name
        # receiver = the object that contains the Slot() method
        # slot = the actual method name
        # hints are for QtDesigner graphics and are ignored here
        #
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



    ###########################################################################
    # GuiViewer flow control related
    ###########################################################################
    def __initialCheck(self):
        msgbox = self.mGuiRootWidget.findChild(QMessageDialog, 'msgbox')
        msgbox.setMessage('NoDbus')
        # 1. Check whether the dbus connection and interface is valid
        if not self.mMsger.hasValidDbusConn():
            # the system does not have a valid DBus Session or dbus interface
            msgbox.setCheckFlags({'NoDbus': True})
            msgbox.setModal(False)
            msgbox.display(True) # _displayMessage(self.mGuiRootWidget, 'NoDbus') # non modal dialog
            _logger.critical('DBus session bus or installer dbus server not available!!! Retrying...')
            QtCore.QTimer.singleShot(1000, self.__initialCheck)
            return
        else:
            msgbox.setCheckFlags({'NoDbus': False}) # _displayMessage(self.mGuiRootWidget, 'NoDbus', hide=True)
            msgbox.display(False)
            msgbox.clearCheckFlags()
            msgbox.clearMessage()

        # Finally, emit the signals defined for the root gui element, passing
        # the viewer reference to the QProcessSlots, allowing them to
        # to setup their request signal to viewer's request. As well as start
        # the web crawling and storage discovery
        for s in self.mGuiRootSignals:
            signalName = re.sub('\(.*\)', '', s)
            if hasattr(self.mGuiRootWidget, signalName):
                # root widget's initialised.emit() signal passing {'viewer': self} to all QProcessSlots
                getattr(self.mGuiRootWidget, signalName)[dict].emit({'viewer': self})
                _logger.info("emit {}.{}, # connected slots:{}".format(self.mGuiRootWidget.objectName(), signalName, self.mGuiRootWidget.receivers(QtCore.SIGNAL("initialised(PyQt_PyObject)"))))

    def setResponseSlot(self, senderSlot):
        """
        setup responseSignal to connect back to sender's resultSlot() allowing
        results to go back to sender when response comes back from QtDBus
        called by QProcessSlot's processSlot() slot
        """
        try:
            # try to disconnect first, then connect
            self.responseSignal.disconnect(senderSlot)
        except:
            pass
        try:
            self.responseSignal.connect(senderSlot)
            _logger.info("connect responseSignal to {}.resultSlot.".format(senderSlot))
        except:
            _logger.warning("connect responseSignal to {}.resultSlot failed".format(senderSlot))
            raise

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
            logoH = int(scnRect.height() / 4) if (scnRect.height() / sizeLogo.height()) < 4 else sizeLogo.height()
            logoW = int(iconSize.width() * (logoH / iconSize.height()))
            if (logoW / scnRect.width()) < 3:
                logoW = int(scnRect.width() / 3)
                logoH = int(iconSize.height() * (logoW / iconSize.width()))
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lblLogo').setPixmap(iconLogo.pixmap(logoW, logoH))

            # work out the proportion to the selection icons
            sizeSelect = self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtSelection').size()
            sh = int(scnRect.height() / 4 * 0.8) if (scnRect.height() / sizeSelect.height()) < 4 else sizeSelect.height()
            if (sh / scnRect.width()) < 10:
                sh = int(scnRect.width() / 10)
            smalliconsize = QtCore.QSize(sh, sh)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtSelection').setIconSize(smalliconsize)
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtSelection').setSpacing(smalliconsize.width()/24)

            # Show/Hide additional Widgets
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lineRescueServer').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'textOutput').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'progressBarStatus').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lblRemaining').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lblDownloadFlash').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lblDoYouKnow').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'btnNext').hide()
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
                # clear the event before sending message over to dbus
                self._clearEvent()
                _logger.debug('send cmd via DBus: {}'.format(self.mCmd))
                return self.mMsger.sendMsg(self.mCmd) 
            else:
                raise TypeError('cmd must be in a dictionary format')
        except Exception as ex:
            _logger.info('Error: {}'.format(ex))
        return False

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
        # execute parsed commands
        if self._parseCmd(params):
            if (self._preExec()):
                if (self._mainExec()):
                    self._postExec()

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
            _logger.debug('DBus signaled response: {}'.format(retResult))
            self.responseSignal.emit(retResult)
        else:
            pass

    def _parseResult(self, response):
        # do the result parsing here, and convert it into proper
        # recognizable dictionary to send to the receiving slots

        # extract the result, and parse the result from server
        if isinstance(response, dict):
            if 'user_request' in response.keys():
                # if it is a user_request, then get user inputs using GUI objects
                self._getUserInput(response.pop('user_request'))
                return False
            # still processings, and allow the QProcessSlot to decide what to do next
            elif response['status'] == 'processing':
                return True
            elif response['status'] == 'success':
                return True
            elif response['status'] == 'failure':
                return True
        return False

    def _getUserInput(self, userRequest):
        # should update GUI element or call GUI Dialogue Boxes to get user input
#         userResponse = {}
#         self.mMoreInputs.clear()
#         self.mMoreInputs = {'user_response': userResponse}
        pass

    def queryResult(self):
        return self.mMsger.getResult()



if __name__ == '__main__':

    app = QtGui.QApplication(sys.argv)
    sighdl = SignalHandler(app)
    sighdl.activate([signal.SIGTERM, signal.SIGUSR1], app.exit)

    uifile = ''
    if os.path.isfile(sys.argv[-1]):
        uifile = sys.argv[-1]
    view = GuiViewer(uifile)
    view.show(app.desktop().screenGeometry())

    ret = app.exec_()
    sighdl.deactivate()
    sys.exit(ret)
