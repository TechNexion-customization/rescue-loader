#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
import sys
import logging
import defconfig
from gui import GuiDraw
from xmldict import XmlDict, ConvertXmlToDict
from defconfig import DefConfig
from messenger import BaseMessenger
from view import BaseViewer

from PyQt4 import QtCore, QtDBus, QtGui
from PyQt4.QtCore import QObject

# get the handler to the current module, and setup logging options
_logger = logging.getLogger(__name__)


def _printSignatures(qobj):
    metaobject = qobj.metaObject()
    for i in range(metaobject.methodCount()):
        _logger.debug(metaobject.method(i).signature())



###############################################################################
#
# GuiViewer
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
            #ret = self.mSessDBus.connect(self.mBusName, self.mObjPath, self.mIfaceName, 'receive', self, QtCore.SLOT('receiveMsg(dict)')) # not working
            _logger.debug('mSessBus returns: {} mSessBus connected? {}'.format(ret, self.mSessDBus.isConnected()))

    def sendMsg(self, msg):
        """
        If self is acting as a server then emits signal, otherwise sends the message
        """
        if isinstance(msg, dict):
            if self.mIsServer:
                self.mAdapter.receive.emit(msg) # call receive() to signal client with msg
            else:
                # called by the CLI/WEB/GUI viewer to send param to server
                if self.mIface: # and self.mIface.isValid():
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
            if self.mIface: #self.mIface.isValid():
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
            if self.mIface: #self.mIface.isValid():
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
        self.mGuiRoot = None
        self.mGuiRootSignals = []
        if confname:
            self.mUiConfDict = ConvertXmlToDict(confname)
            self.__parseConf(self.mUiConfDict)
        else:
            self.mConfDict = self.mDefConfig.getSettings('gui_viewer')
            self.__parseConf(self.mConfDict['gui_viewer'])
        self.__setupMsger()

    def __setupMsger(self):
        # check the DefConfig, and create mMsger as the dbus client
        conf = self.mDefConfig.getSettings(flatten=True)
        self.mMsger = QtDbusMessenger(conf, self.mGuiRoot, self.response)

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
            if not all([self._checkCustomWidget(customconf)]):
                _logger.error('Not All Custom Widget Classes are supported')
                return False
        return True

    def _checkCustomWidget(self, customconf):
        def get_all_subclasses(c):
            all_subclasses = []
            for subclass in c.__subclasses__():
                all_subclasses.append(subclass)
                all_subclasses.extend(get_all_subclasses(subclass))
            return all_subclasses

        for subcls in get_all_subclasses(QtGui.QWidget):
            if customconf['class'] == subcls.__name__:
                subcls = subcls
                slotlist = customconf['slots']['slot'] if isinstance(customconf['slots']['slot'], list) \
                                                        else [customconf['slots']['slot']]
                if all([hasattr(subcls, slot.rstrip('()')) for slot in slotlist]):
                    return True
        return False

    def __setupUI(self, confdict, parent=None):
        # if root element, ie. no parent, setup specific way
        if parent is None:
            # set the root Gui elem
            parent = GuiDraw.GenGuiDraw(confdict)
            self.mGuiRoot = parent
            # Window Additional Flags
            self.mGuiRoot.setWindowFlags(QtCore.Qt.SplashScreen) # | QtCore.Qt.WindowStaysOnTopHint)
        else:
            # takes the old parent, and return itself as the new parent
            parent = GuiDraw.GenGuiDraw(confdict, parent)

        # recursively create all GUI elements but ignoring 'property' and 'attribute'
        for tag in ['widget', 'layout', 'item', 'action']:
            if tag in confdict.keys():
                # ensure confdict[tag] into a list
                taglist = []
                if isinstance(confdict[tag], XmlDict):
                    taglist.append(confdict[tag])
                elif isinstance(confdict[tag], list):
                    taglist.extend(confdict[tag])

                # iterate each item and recursive call to create it
                for entry in taglist:
                    if tag == 'action':
                        # setup actions, i.e. QAction here
                        entry.update({'class': 'QAction'})
                        self.__setupUI(entry, self.mGuiRoot)
                    elif 'class' in entry.keys() and entry['class'] == 'QProcessSlot':
                        # setup other cases, i.e. QProcessSlot, subclasses here
                        self.__setupUI(entry, self.mGuiRoot)
                    elif 'class' in entry.keys() and 'name' in entry.keys():
                        self.__setupUI(entry, parent)
                    else:
                        for k in entry.keys():
                            if 'class' in entry[k].keys() and 'name' in entry[k].keys():
                                self.__setupUI(entry[k], parent)
                            else:
                                raise RuntimeError('Error Parsing the GUI Xml')

    def __validateSlots(self, confdict):
        # Validate that the root widget has the appropriate signal defined.
        for k, v in confdict.items():
            if k == 'signal':
                if isinstance(v, dict):
                    self.mGuiRootSignals.extend(v)
                else:
                    self.mGuiRootSignals.append(v)
        if all([hasattr(self.mGuiRoot, i.rstrip('()')) for i in self.mGuiRootSignals]):
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
        if isinstance(confdict, list):
            for conn in confdict:
                self._setupSignals(conn)
        elif isinstance(confdict, XmlDict):
            self._setupSignals(confdict)

    def _setupSignals(self, confdict):
        if confdict['sender'] in GuiDraw.clsGuiDraws.keys():
            sender = GuiDraw.clsGuiDraws[confdict['sender']]
            signalName = re.sub('\(.*\)', '', confdict['signal'])
            slotName = re.sub('\(.*\)', '', confdict['slot'])
            if hasattr(sender, signalName):
                if confdict['receiver'] in GuiDraw.clsGuiDraws.keys():
                    receiver = GuiDraw.clsGuiDraws[confdict['receiver']]
                    if hasattr(receiver, slotName):
                        getattr(sender, signalName).connect(getattr(receiver, slotName))
                        _logger.info("connect {}.{} to {}.{}".format(sender.objectName(), signalName, receiver.objectName(), slotName))
                else:
                    if hasattr(self.__module__, slotName):
                        getattr(sender, signalName).connect(getattr(self.__module__, slotName))
                        _logger.info("connect {}.{} to {}.{}".format(sender.objectName(), signalName, self.__module__, slotName))

    def show(self):
        # Show the Widgets
        if isinstance(self.mGuiRoot, QtGui.QWidget):
            self.mGuiRoot.show()

        # Emit the signals defined for the root gui element, allowing
        # the connections to be setup to start the web crawling and storage discovery
        for s in self.mGuiRootSignals:
            signalName = re.sub('\(.*\)', '', s)
            if hasattr(self.mGuiRoot, signalName):
                getattr(self.mGuiRoot, signalName)[dict].emit({'viewer': self})
                _logger.info("emit {}.{}, #slots:{}".format(self.mGuiRoot.objectName(), signalName, self.mGuiRoot.receivers(QtCore.SIGNAL("initialised(PyQt_PyObject)"))))

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
        """
        handles checking slot's sender
        also have to ensure results goes back to sender when response comes back from QtDBus
        """
        _logger.debug("connect responseSignal to {}.resultSlot".format(self.sender().objectName()))
        self.responseSignal.connect(self.sender().resultSlot)
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
        3. pre-execute the command,
           check slot's sender, have to ensure results goes back to sender
           when response comes back from QtDBus
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
        A slot handles all the dbus receive signal messages from QtDbus

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

            # status == processing or has user_request
#                 while True:
#                     # loop to wait for dbus response
#                     # wait for dbus server response for 25 seconds, same as DBus timeout
#                     self._waitForEventTimeout(25)
#                     # handle what is received from the (dbus) server after Response Event is set
#                     if not self._parseResult():
#                         if len(self.mMoreInputs):
#                             _logger.info('get more user inputs: {}'.format(self.mMoreInputs))
#                             self.mMsger.sendMsg(self.mMoreInputs)
#                         else:
#                             # keep query for status while in the processing state, i.e. no new user inputs
#                             _logger.debug('still processing, so send query_status')
#                             self.mMsger.sendMsg({'query_status': 'True'})
#                         continue
#                     else:
#                         break

    def _parseResult(self, response):
        # do the result parsing here, and convert it into proper
        # recognizable dictionary to send to the receiving slots

        # extract the result, and parse the result from server
        if isinstance(response, dict):
            if 'user_request' in response.keys():
                # if it is a user_request, then get user inputs using GUI objects
                self._getUserInput(response.pop('user_request'))
                return False
            elif response['status'] == 'processing':
                # still processings, and allow the QProcessSlot to decide what to do next
                #response.pop('status')
                return True
            elif response['status'] == 'success':
                #response.pop('status')
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

    if not QtDBus.QDBusConnection.sessionBus().isConnected():
        sys.stderr.write("Cannot connect to the D-Bus session bus.\n"
                "Please check your system settings and try again.\n")
        sys.exit(1)

    view = GuiViewer('installer.ui' if os.path.isfile('./installer.ui') else '')
    view.show()

    sys.exit(app.exec_())
