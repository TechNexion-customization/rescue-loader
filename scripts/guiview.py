#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import os
import sys
import logging
import defconfig
from guidraw import GuiDraw
from xmldict import XmlDict, ConvertXmlToDict
from defconfig import DefConfig, SetupLogging
from messenger import BaseMessenger
from view import BaseViewer

from PyQt4 import QtNetwork
from PyQt4 import QtCore, QtDBus, QtGui
from PyQt4.QtCore import QObject

# get the handler to the current module, and setup logging options
SetupLogging('/tmp/installer_gui.log')
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)



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

        # for checking network connectivity
        self.mNetMgr = QtNetwork.QNetworkAccessManager()
        # setup callback slot to self._networkResponse() for QtNetwork's NAMgr finish signal
        self.mNetMgr.finished.connect(self._networkResponse)
        # signal once after 1000ms to check network connectivity
        QtCore.QTimer.singleShot(1000, self.__checkNetwork)

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
                    slotlist = cconf['slots']['slot'] if isinstance(cconf['slots']['slot'], list) \
                                                            else [cconf['slots']['slot']]
                    if all([hasattr(subcls, slot.rstrip('()')) for slot in slotlist]):
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
            self.mGuiRootWidget.setWindowFlags(QtCore.Qt.SplashScreen) # | QtCore.Qt.WindowStaysOnTopHint)
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
    def __checkNetwork(self):
        # use QtNetwork NAMger to send a request to technexion's rescue server
        # when the request is finished, NAMger will signal its "finish" signal
        # which calls back to self._networkResponse() with reply
        url = 'http://rescue.technexion.net'
        req = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
        self.mNetMgr.get(req)

    def _networkResponse(self, reply):
        # Check whether network connect is active and correct
        if reply.error() != QtNetwork.QNetworkReply.NoError:
            _logger.error("Network Access Manager Error occured: {}, {}", reply.error(), reply.errorString())
            # the system does not have a valid network interface and connection
            ret = QtGui.QMessageBox.critical(self.mGuiRootWidget, 'TechNexion Rescue System', 'Internet not available!!!', QtGui.QMessageBox.Reset|QtGui.QMessageBox.Retry, QtGui.QMessageBox.Retry)
            if ret == QtGui.QMessageBox.Reset:
                # reset/reboot the system
                _logger.critical('Internet not available!!!')
                sys.exit(1)
            elif ret == QtGui.QMessageBox.Retry:
                QtCore.QTimer.singleShot(1000, self.__checkNetwork)
                return

        # Check whether the dbus connection and interface is valid
        if not self.mMsger.hasValidDbusConn():
            # the system does not have a valid DBus Session or dbus interface
            ret = QtGui.QMessageBox.critical(self.mGuiRootWidget, 'TechNexion Rescue System', 'DBus session bus or installer dbus server not available!!!', QtGui.QMessageBox.Reset, QtGui.QMessageBox.Reset)
            if ret == QtGui.QMessageBox.Reset:
                # reset/reboot the system
                _logger.critical('DBus session bus or installer dbus server not available!!!')
                sys.exit(1)

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
        setup responseSignal to connect back to sender's slot allowing
        results to go back to sender when response comes back from QtDBus
        called by QProcessSlot's processSlot() slot
        """
        try:
            # self.responseSignal.connect(self.sender().resultSlot)
            self.responseSignal.connect(senderSlot)
            _logger.info("connect responseSignal to {}.resultSlot.".format(senderSlot))
        except:
            _logger.warning("connect responseSignal to {}.resultSlot failed".format(senderSlot))

    def show(self, scnRect):
        if isinstance(self.mGuiRootWidget, QtGui.QWidget):
            self.mGuiRootWidget.setGeometry(scnRect)
            if (scnRect.width() / 4) > 100 and (scnRect.height() / 4) > 100:
                # 100x100 pixels are the icon default size
                self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtBoard').setIconSize(QtCore.QSize(scnRect.width() / 4, scnRect.height() / 4))
                self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtOS').setIconSize(QtCore.QSize(scnRect.width() / 4, scnRect.height() / 4))
                self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtDisplay').setIconSize(QtCore.QSize(scnRect.width() / 4, scnRect.height() / 4))
                self.mGuiRootWidget.findChild(QtGui.QWidget, 'lstWgtStorage').setIconSize(QtCore.QSize(scnRect.width() / 4, scnRect.height() / 4))
            self.mGuiRootWidget.show()
            # Hide additional Widgets
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'lineRescueServer').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'textOutput').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'btnFlash').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabRescue').hide()
            self.mGuiRootWidget.findChild(QtGui.QWidget, 'tabInstall').hide()

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

    def _preExec(self):
#         print('receivers count: {}'.format(self.receivers(QtCore.SIGNAL("responseSignal(PyQt_PyObject)"))))
#         _printSignatures(self)
        return True

    def _mainExec(self):
        """
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

    def _postExec(self):
        """
        Handles additional work when main execution was successful
        """
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
    uifile = ''
    if os.path.isfile(sys.argv[-1]):
        uifile = sys.argv[-1]
    view = GuiViewer(uifile)
    view.show(app.desktop().screenGeometry())

    sys.exit(app.exec_())
