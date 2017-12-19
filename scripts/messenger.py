#!/usr/bin/env python3

import abc
import logging
import dbus
import gobject
#from gi.repository import GLib
from dbus.service import Object as DBusSrvObject
from dbus.mainloop.glib import DBusGMainLoop as GLib_DBusGMainLoop
from dbus.mainloop.glib import threads_init as GLib_threads_init

_logger = logging.getLogger(__name__)

class MergeMeta(type):
    def __new__(cls, name, bases, members):
        #collect up the metaclasses
        metas = [type(base) for base in bases]

        # prune repeated or conflicting entries
        metas = [meta for index, meta in enumerate(metas)
            if not [later for later in metas[index+1:]
                if issubclass(later, meta)]]

        # whip up the actual combined meta class derive off all of these
        meta = type(name, tuple(metas), dict(combined_metas = metas))

        # make the actual object
        return meta(name, bases, members)

    def __init__(self, name, bases, members):
        for meta in self.combined_metas:
            meta.__init__(self, name, bases, members)

# ============================================================
#
# BaseMessenger
#
# base messenger class for communications between different
# installer software components
#
# ============================================================
class BaseMessenger(object):
    """
        BaseMessenger
    
    """
    __metaclass__ = abc.ABCMeta
    
    def __init__(self, config, cbhandle):
        # super(BaseMessenger, self).__init__() # old python style
        super().__init__()
        self.mConfig = {}
        self.mConfig.update(config)
        self.mCallbackHandler = cbhandle

    @abc.abstractmethod
    def sendMsg(self, msg):
        pass

    @abc.abstractmethod
    def receiveMsg(self):
        pass



class DbusMessenger(BaseMessenger, DBusSrvObject):
    """
    The DbusMessenger class that handles the DBus IPC messages
    """
    
    __metaclass__ = MergeMeta
    
    def __init__(self, config, cbhandle=None):
        # BaseMessenger.__init__(self, config, cbhandle) # old python style
        super().__init__(config, cbhandle)
        # set the dbus.mainloop.glib.DBusGMainLoop() as default event loop mechanism
        gobject.threads_init() # Must Do this first if use gobject.MainLoop()
        GLib_threads_init()
        GLib_DBusGMainLoop(set_as_default=True)
        self.mIsServer = self.mConfig['IS_SERVER'] if ('IS_SERVER' in self.mConfig.keys()) else False
        self.__initialize()

    def __initialize(self):
        """
        initialize this object to the DBUS connection
        """
        # setup seesion bus
        self.mSessDBus = dbus.SessionBus()
        # get the dbus name for our app, and setup session bus name
        self.mBusName = dbus.service.BusName(self.mConfig['busname'], self.mSessDBus)
        # setup Dbus Server's obj path
        self.mObjPath = self.mConfig['srv_path']
        # both client and server require an actual loop to handle events,
        # so, create a MainLoop() from PyGObject's GLib binding
        self.mDBusLoop = gobject.MainLoop() #GLib.MainLoop()
        if self.mIsServer:
            # call dbus.service.Object constructor with sessbus and obj path
            dbus.service.Object.__init__(self, self.mBusName, self.mObjPath)
        else:
            # get the server proxy object
            self.mServerObj = self.mSessDBus.get_object(self.mConfig['busname'], self.mObjPath)
            self.mSignal = self.mSessDBus.add_signal_receiver(handler_function=self.receiveMsg, \
                                                              signal_name='receive', \
                                                              path=self.mObjPath, \
                                                              dbus_interface=self.mConfig['busname'])

    @dbus.service.method(dbus_interface="com.technexion.dbus.interface", in_signature='a{sv}', out_signature='b')
    def send(self, request):
        """
        provide sent request RPC call_method on the server
        """
        _logger.debug('dbus send method: {}'.format(request))
        params = {}
        #called through the Dbus with request
        if callable(self.mCallbackHandler):
            # parse the serialized second string back to dict
            params.update(request)
            self.mCallbackHandler(params)
            return True
        return False

    @dbus.service.signal(dbus_interface="com.technexion.dbus.interface", signature='a{sv}')
    def receive(self, response):
        """
        provide receive response RPC notify_signal on the server
        """
        _logger.debug('dbus receive signal: {}'.format(response))
        pass

    def run(self):
        # both client and server run the dbus with GLib.MainLoop()
        if self.mDBusLoop:
            self.mDBusLoop.run()

    def stop(self):
        # both server and client uses a DBus Loop
        if self.mDBusLoop:
            self.mDBusLoop.quit()
        if not self.mIsServer and self.mSignal:
            self.mSignal.remove()

    def sendMsg(self, msg):
        if isinstance(msg, dict):
            if self.mIsServer:
                self.receive(msg) # call receive() to signal client with param
            else:
                # called by the CLI/WEB/GUI viewer to send param to server
                if self.mServerObj: 
                    self.mServerObj.send(msg)
                else:
                    raise ReferenceError('Unable to access DBUS exported object')
        else:
            raise TypeError('Message has to be packaged in a dictionary.')

    def receiveMsg(self, response):
        """
        signal handler for the receive() signal from server
        """
        params = {}
        #called through the Dbus with response
        if callable(self.mCallbackHandler):
            # parse the serialized second string back to dict
            params.update(response)
            self.mCallbackHandler(params)
            return True
        return False



class SocketMessenger(BaseMessenger):
    """
        SocketMessenger(BaseMessenger)
    
    """
    def __init__(self, config, cbhandle):
        # super(SocketMessenger, self).__init__(config, cbhandle) # old python style
        super().__init__(config, cbhandle)

    def sendMsg(self, msg):
        pass
    
    def receiveMsg(self):
        return {}



if __name__ == "__main__":
    import threading
    import time

    def flash():
        def CliHandler(params):
            print("CliHandler: received:")
            if isinstance(params, dict):
                for k, v in params.items():
                    print('key:{} value:{}'.format(k, v))

        dbuscli= DbusMessenger(setting, CliHandler)
        threadcli = threading.Thread(target=dbuscli.run)
        threadcli.start()
        dbuscli.sendMsg({u'flash':{u'src_filename': u'./test.bin', u'src_start_sector': u'0', u'src_total_sectors': u'64', \
              u'tgt_filename': u'./target.bin', u'tgt_start_sector': u'32'}})
        time.sleep(1)
        dbuscli.stop()
        threadcli.join()

    def server(setting):
        def CBhandler(params):
            print("CBhandler: received:\n{}".format(params))
            dbussrv.sendMsg(params)
            return True
        dbussrv = DbusMessenger(setting, CBhandler)
        dbussrv.run()

    def client(setting):
        def CliHandler(params):
            print("CliHandler: received:")
            if isinstance(params, dict):
                for k, v in params.items():
                    print('key:{} value:{}'.format(k, v))
        def Run():
            dbuscli.sendMsg({u'info':{u'target': u'emmc', u'location': u'disk'}})
            time.sleep(1)
            dbuscli.stop()

        dbuscli= DbusMessenger(setting, CliHandler)
        threadcli = threading.Thread(target=Run)
        threadcli.start()
        dbuscli.run()
        threadcli.join()

    import argparse
    parser = argparse.ArgumentParser(description='Process Arguments.')
    parser.add_argument('-c', '--config-file', dest='configfile', help='Specify the configuration file to load', metavar='FILE')
    parser.add_argument('-v', '--verbose', dest='verbose', default=False, help='Show more information')
    parser.add_argument('-t', dest='type', choices=['srv', 'flash', 'cli'], help='start the dbusmessage server, client_server, or client')
    args = parser.parse_args()
    
    from defconfig import DefConfig
    conf = DefConfig()
    conf.loadConfig("/etc/installer.xml")
    setting = conf.getSettings(flatten=True)
    
    if args.type == 'srv':
        setting.update({'IS_SERVER': True})
        server(setting)
    elif args.type == 'flash':
        flash()
    else:
        setting.update({'CLIENT_TYPE': 'cli_path'})
        client(setting)

    exit()
