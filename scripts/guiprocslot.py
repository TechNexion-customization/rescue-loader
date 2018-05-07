#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
from math import log
from urllib.parse import urlparse
from PyQt4 import QtGui, QtCore, QtSvg
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
    r,f=min(int(log(max(n*b**pow,1),b)),len(pre)-1),'{:,.%if} %s%s'
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
                        if int(row['size']) == 3825205248:
                            resName = ":/res/images/storage_emmc.svg"
                        else:
                            resName = ":/res/images/storage_sd.svg"
                    item.setText('{}'.format(row['name']))
                elif 'os' in row and 'ver' in row:
                    resName = ":/res/images/os_{}.svg".format(row['os'].lower())
                    item.setText('{}'.format(row['ver'].lower()))
                elif 'board' in row:
                    #update the VERSION within the svg resource byte array, and draw the svg
                    resName = ":/res/images/board_{}.svg".format(row['board'].lower())
                    item.setText(row['board'].lower())
                elif 'display' in row:
                    resName = ":/res/images/display.svg"
                    item.setText(row['display'].lower())
                else:
                    resName = ":/res/images/os_tux.svg"
                    item.setText(row['name'])

                item.setIcon(QtGui.QIcon(resName))
                item.setTextAlignment(QtCore.Qt.AlignCenter)
                qContainer.addItem(item)

            # set disable / enable
            if 'disable' in row:
                item.setFlags((item.flags() & ~QtCore.Qt.ItemIsEnabled) if (row['disable'] == True) else (item.flags() | QtCore.Qt.ItemIsEnabled))

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
        return cls.subclasses[confdict['name']](confdict, parent)

    def __init__(self, confdict, parent = None):
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

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
        self.mResults = ''

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
        if 'found_match' in results:
            form, cpu, baseboard = results['found_match'].split(',')
            self._findChildWidget('lblCpu').setText(cpu)
            self._findChildWidget('lblForm').setText(form)
            self.success.emit('Found: {} {} {}\n'.format(cpu, form, baseboard))
        else:
            if results['status'] != 'processing':
                form = cpu = baseboard = '' # same reference
                self._findChildWidget('lblCpu').setText('No CPU')
                self._findChildWidget('lblForm').setText('No Form Factor')
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
        self.mResults = []

    def process(self, inputs):
        """
        Handle crawlWeb callback slot
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

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
        self.mResults = []

    def process(self, inputs):
        """
        Handle crawling xz files from inputs, i.e. lists of mount points
        """
        # make up the request params
        params = {'target': os.uname()[1]}
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

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
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
        # Check for available storage disk in the self.mResult list
        if isinstance(self.mResults, list) and len(self.mResults):
            # emit results to the next QProcessSlot, i.e. chooseStorage, and crawlLocalfs
            self.success.emit(self.mResults)
            return
        else:
            ret = QtGui.QMessageBox.warning(self, 'TechNexion Rescue System', 'No suitable storage found, please insert sdcard...\nClick Retry to rescan!!!', QtGui.QMessageBox.Ok | QtGui.QMessageBox.Retry, QtGui.QMessageBox.Ok)
            if ret == QtGui.QMessageBox.Retry:
                # retry scanning the storage
                self.process()


@QProcessSlot.registerProcessSlot('scanPartition')
class scanPartitionSlot(QProcessSlot):
    """
    Can for the mounted points from exiting partitions in the system
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(object)
    fail = pyqtSignal(str)

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
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
        # Check for available storage disk in the self.mResult list
        _logger.debug('validateResult scanPartition result: {}'.format(self.mResults))
        if isinstance(self.mResults, list) and len(self.mResults):
            # emit results to the next QProcessSlot, i.e. crawlLocalfs
            self.success.emit(list(set(self.mResults)))



@QProcessSlot.registerProcessSlot('chooseImage')
class chooseImageSlot(QProcessSlot):
    """
    Handles button click event to issue cmd to choose board, os, and display
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(dict)
    fail = pyqtSignal(str)

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
        self.mResults = []
        self.mPick = {'board': None, 'os': None, 'ver': None, 'display': None}
        self.mLstWgtBoard = None
        self.mLstWgtOS = None
        self.mLstWgtDisplay = None
        self.mUrl = None

    def process(self, inputs):
        # update Display the dynamic UI from the available list of found rescue files passed in inputs
        _logger.debug('chooseImageSlot: signal sender: {}, inputs: {}'.format(self.sender().objectName(), inputs))
        # update the UI element for later use
        if self.mLstWgtBoard is None: self.mLstWgtBoard = self._findChildWidget('lstWgtBoard')
        if self.mLstWgtOS is None: self.mLstWgtOS = self._findChildWidget('lstWgtOS')
        if self.mLstWgtDisplay is None: self.mLstWgtDisplay = self._findChildWidget('lstWgtDisplay')

        if (self.sender().objectName() == 'crawlWeb' or self.sender().objectName() == 'crawlLocalfs') and isinstance(inputs, list):
            # parse the download files into selectable options, i.e. board, OS, ver, display
            self.__parseDownloadFilesList(inputs)
            self.__updateUI()

        if self.sender() == self.mLstWgtBoard or self.sender() == self.mLstWgtDisplay or self.sender() == self.mLstWgtOS:
            # do smart selections based on item chosen from the board, OS, ver, display pools/lists
            filtered = self.__smartFilterSelections(inputs)
            # do clever filtering to disable items not related to selection
            self.__disableList(filtered)
            self.__updateUI()

        if self.sender().objectName()== "btnNext":
            # Find a matching CPU and FORM from the self.mCpuNames and self.mFormNames pool
            for cpu in self.mCpuNames:
                if cpu in self._findChildWidget('lblCpu').text().lower():
                    self.mPick['cpu'] = cpu
            for form in self.mFormNames:
                if form in self._findChildWidget('lblForm').text().lower():
                    self.mPick['form'] =  form
            self.mUrl = '{}-{}/{}-{}/{}-{}.xz'.format(self.mPick['form'], \
                                                      self.mPick['cpu'], \
                                                      self.mPick['board'], \
                                                      self.mPick['display'], \
                                                      self.mPick['os'], \
                                                      self.mPick['ver'])
            if self.mPick['board'] is not None and self.mPick['os'] is not None and self.mPick['display'] is not None and self.mPick['ver'] is not None:
                self.finish.emit()

    def __parseDownloadFilesList(self, listOfFileDict):
        # {'os': 'ubuntu',
        #  'size': '3420454912',
        #  'ver': '16.04',
        #  'display': 'lcd800x480',
        #  'cpu': 'imx7',
        #  'form': 'pico',
        #  'board': 'dwarf',
        #  'url': 'http://rescue.technexion.net/rescue/pico-imx7/dwarf-lcd800x480/ubuntu-16.04.xz'
        self.mResults.extend([d for d in listOfFileDict if (int(d['size']) > 0)])
        _logger.info('list of xz files: {}'.format(self.mResults))

        # gets the unique set of available boards, OS, version, Display from the crawled list
        self.mCpuNames = set(dlfile['cpu'] for dlfile in self.mResults if ('cpu' in dlfile))
        self.mFormNames = set(dlfile['form'] for dlfile in self.mResults if ('form' in dlfile))
        self.mBoardNames = set(dlfile['board'] for dlfile in self.mResults if ('board' in dlfile))
        self.mDisplayNames = set(dlfile['display'] for dlfile in self.mResults if ('display' in dlfile))
        self.mOSNames = []
        for d in [{'os':dlfile['os'], 'ver':dlfile['ver']} for dlfile in self.mResults if ('os' in dlfile and 'ver' in dlfile)]:
            if all(not (d == n) for n in self.mOSNames):
                self.mOSNames.append(d)

        # come up with a new list to send to GUI container, i.e. QListWidget
        self.mBoardList = list({'name': name, 'board': name, 'disable': False} for name in self.mBoardNames)
        self.mDisplayList = list({'name': name, 'display': name, 'disable': False} for name in self.mDisplayNames)
        self.mOSList = list({'name': item['os']+'-'+item['ver'], 'os': item['os'], 'ver': item['ver'], 'disable': False} for item in self.mOSNames)

    def __smartFilterSelections(self, clickedItem):
        """
        Handles user selection with the ability to disable other unrelated options (e.g. Board, OS, Version, Display)
        """
        def find_match(strSearch, listOfFileDict):
            for fdict in listOfFileDict:
                if strSearch in fdict.values():
                    yield fdict

        def find_subset(lstValues, lstFiles):
            if len(lstValues):
                v = lstValues.pop()
                return list(find_subset(lstValues, list(find_match(v, lstFiles)))) if len(lstValues) else list(find_match(v, lstFiles))

        selection = []
        # clever UI display to provide smarter human computer interfaces
        if isinstance(clickedItem, QtGui.QListWidgetItem):
            # if not coming from the crawling procSlots, determine what has been chosen from the QListWidget
            # get the selected item, and do some clever thing to gray out other options
            if self.sender() == self.mLstWgtBoard:
                if (int(clickedItem.flags()) & QtCore.Qt.ItemIsEnabled):
                    self.mPick['board'] = clickedItem.data(QtCore.Qt.UserRole)['board']
                else:
                    self.mPick['board'] = None
            elif self.sender() == self.mLstWgtOS:
                if (int(clickedItem.flags()) & QtCore.Qt.ItemIsEnabled):
                    self.mPick['os'] = clickedItem.data(QtCore.Qt.UserRole)['os']
                    self.mPick['ver'] = clickedItem.data(QtCore.Qt.UserRole)['ver']
                else:
                    self.mPick['os'] = None
                    self.mPick['ver'] = None
            elif self.sender() == self.mLstWgtDisplay:
                if (int(clickedItem.flags()) & QtCore.Qt.ItemIsEnabled):
                    self.mPick['display'] = clickedItem.data(QtCore.Qt.UserRole)['display']
                else:
                    self.mPick['display'] = None

        # find the subset of availablelists from user selections
        _logger.debug('Pick: {}'.format(self.mPick))
        for v in self.mPick.values():
            if v is not None:
                selection.append(v)
        _logger.debug('Selection: {}'.format(selection))
        lstReturn = find_subset(selection, self.mResults) if len(selection) else self.mResults
#         if len(lstReturn) == 1:
#             # should automatically check the only possible selection
#             self.mPick['board'] = lstReturn['board']
#             self.mPick['display'] = lstReturn['display']
#             self.mPick['os'] = lstReturn['os']
#             self.mPick['version'] = lstReturn['version']
        return lstReturn

    def __disableList(self, filteredList):
        _logger.debug('filtered list: {}'.format(filteredList))
        for ui in self.mBoardList:
            if len(filteredList) and all(ui['board'] not in dlfile.values() for dlfile in filteredList):
                ui['disable'] = True
            else:
                ui['disable'] = False
        for ui in self.mDisplayList:
            if len(filteredList) and all(ui['display'] not in dlfile.values() for dlfile in filteredList):
                ui['disable'] = True
            else:
                ui['disable'] = False
        for ui in self.mOSList:
            if len(filteredList) and all(ui['os'] not in dlfile.values() for dlfile in filteredList):
                ui['disable'] = True
            else:
                ui['disable'] = False
            if len(filteredList) and all(ui['ver'] not in dlfile.values() for dlfile in filteredList):
                ui['disable'] = True
            else:
                ui['disable'] = False


    def __updateUI(self):
        # update the UI display according to the parsed board/os/ver/display selections from lists of download files
        _insertToContainer(self.mBoardList, self.mLstWgtBoard, None)
        _insertToContainer(self.mOSList, self.mLstWgtOS, None)
        _insertToContainer(self.mDisplayList, self.mLstWgtDisplay, None)

    # NOTE: Not using the resultSlot() and in turn parseResult() because we did not send a request via DBus
    # to get results from installerd
    #def parseResult(self, results):
    #    pass

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # so, check for valid storage to flash selected Url file here
        if self.mUrl and isinstance(self.mUrl, str):
            for item in self.mResults:
                if self.mUrl.replace('/', '_') in item['url'] or self.mUrl in item['url']:
                    _logger.warning('validateResult found matched download URL: {}'.format(item['url']))
                    self.success.emit(item)
                    self._findChildWidget('tabChoose').hide()
                    self._findChildWidget('btnNext').hide()
                    self._findChildWidget('tabRescue').show()
                    self._findChildWidget('btnFlash').show()
                    return
        else:
            self.fail.emit('failed to choose a valid file to download')



@QProcessSlot.registerProcessSlot('chooseStorage')
class chooseStorageSlot(QProcessSlot):
    """
    Handles button click event to issue cmd to choose board, os, and display
    """
    request = pyqtSignal(dict)
    success = pyqtSignal(dict)
    fail = pyqtSignal(str)

    def __init__(self,  confdict, parent = None):
        super().__init__(confdict, parent)
        self.mPathList = []
        self.mStorage = None
        self.mLstWgtStorage = None

    def process(self, inputs):
        # Display the dynamic UI from the available list of found target storage passed in inputs
        _logger.debug('chooseStorageSlot: signal sender: {}, inputs: {}'.format(self.sender().objectName(), inputs))
        # get the UI element to update
        if self.mLstWgtStorage is None: self.mLstWgtStorage = self._findChildWidget('lstWgtStorage')

        if self.sender().objectName() == 'scanStorage' and isinstance(inputs, list):
            # filter out only the valid disks and put available disks in a temporary set
            diskNames = set(d['name'] for d in inputs if ('size' in d and int(d['size']) > 0))
            # stuff the available disks in self.mPathList for the container coming from scanStorage's self.mResult
            # {'name': tgt[1],
            #  'path': tgt[2]['device_node'],
            #  'device_type': tgt[2]['device_type'],
            #  'size':int(tgt[2]['size']) * 512,
            #  'id_bus': tgt[2]['id_bus'],
            #  'id_serial': tgt[2]['id_serial'],
            #  'id_model': tgt[2]['id_model']}
            for d in inputs:
                if ('name' in d and d['name'] in diskNames):
                    d.update({'disable': False})
                    self.mPathList.append(d)
            _logger.debug('chooseStorage: mPathList: {}'.format(self.mPathList))
            _insertToContainer(self.mPathList, self.mLstWgtStorage, None)

        if self.sender() == self.mLstWgtStorage:
            # parse the QListWidgetItem to get the chosen storage
            if isinstance(inputs, QtGui.QListWidgetItem):
                # determine what has been chosen from the QListWidget, get the selected item
                self.mStorage = inputs.data(QtCore.Qt.UserRole)

        if self.sender().objectName() == 'btnFlash':
            if self.mStorage is not None and isinstance(self.mStorage, dict):
                self.finish.emit()

    # NOTE: Not using the resultSlot() and in turn parseResult() because we did not send a request via DBus
    # to get results from installerd
    #def parseResult(self, results):
    #    pass

    def validateResult(self):
        # flow comes here (gets called) after self.finish.emit()
        # so check for valid storage to flash selected Url file here
        if self.mStorage is not None and isinstance(self.mStorage, dict):
            self.success.emit(self.mStorage)
            self._findChildWidget('btnFlash').hide()
            self._findChildWidget('tabRescue').hide()
            self._findChildWidget('tabInstall').show()
            return
        else:
            self.fail.emit('failed to choose a valid file to download')



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
        self.mFileUrl = None
        self.mTgtStorage = None
        self.mFlashFlag = False
        self.mAvSpeed = 0
        self.mLastWritten = 0
        self.mRemaining = 0
        self.mTimer = QtCore.QTimer()
        self.mTimer.timeout.connect(self._queryResult)
        self.mLblRemain = None

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

            if 'status' in self.mResults and (self.mResults['status'] == 'success' or self.mResults['status'] == 'failure'):
                self.finish.emit()

    def process(self, inputs):
        """
        grab the dl_url and tgt_filename from the tableRescueFile and tableTargetStorage itemClicked() signals
        when signal sender is from btnFlash, issue flash command with clicked rescue file and target storage.
        """
        if self.mLblRemain is None: self.mLblRemain = self._findChildWidget('lblRemaining')

        if not self.mFlashFlag:
            _logger.debug('downloadImageSlot: signal sender: {}, inputs: {}'.format(self.sender().objectName(), inputs))
            if self.sender().objectName() == 'chooseImage' and isinstance(inputs, dict):
                # clone the Url
                self.mFileUrl = inputs['url'][:]
                _logger.debug('download from {}'.format(self.mFileUrl))
                # reset the progress bar
                self.success.emit(0)

            if self.sender().objectName() == 'chooseStorage' and isinstance(inputs, dict):
                # clone the storage
                self.mTgtStorage = inputs['path'][:]
                _logger.debug('flash to {}'.format(self.mTgtStorage))
                # reset the progress bar
                self.success.emit(0)

            # step 6: make up the command to download and flash and execute it
            # Need to grab or keep the chooses from file list selection and target list selection
            if self.sender().objectName() == 'chooseStorage':
                if self.mFileUrl and self.mTgtStorage:
                    _logger.info('download from {} and flash to {}'.format(self.mFileUrl, self.mTgtStorage))
                    self._setCommand({'cmd': 'download', 'dl_url': self.mFileUrl, 'tgt_filename': self.mTgtStorage})
                    self.request.emit(self.mCmds[-1])
                    # show and hide some Gui elements
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
        self.mResults.update(results)
        if results['status'] == 'processing':
            self.mTimer.start(1000) # 1000 ms
            self.mFlashFlag = True
        else:
            # flash job either success or failure
            self.mTimer.stop()
            self.mFlashFlag = False

    def validateResult(self):
        _logger.debug('validateResult: {}'.format(self.mResults))
        # Check for flash complete
        # Check for available storage disk in the self.mResult list
        if isinstance(self.mResults, dict) and (self.mResults['status'] == 'success' or self.mResults['status'] == 'failure'):
            ret = QtGui.QMessageBox.warning(self, 'TechNexion Rescue System', 'Installation {}...\nSet boot jumper to boot from sdcard/emmc,\nAnd click RESET to reboot sytem!'.format('Complete' if (self.mResults['status'] == 'success') else 'Failed'), QtGui.QMessageBox.Ok | QtGui.QMessageBox.Reset, QtGui.QMessageBox.Ok)
            if ret == QtGui.QMessageBox.Reset:
                # reset/reboot the system
                os.system("reboot")
