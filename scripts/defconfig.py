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

# defconfig:
# handles xml configuration parsing
#
# Author: Po Cheng <po.cheng@technexion.com>

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from lxml.etree import ElementTree
from xmldict import XmlDict, ConvertXmlToDict, ConvertDictToXml

# get the handler to the current module
_logger = logging.getLogger(__name__)

def SetupLogging(logfname):
    # set up logging to file - see previous section for more details
    logging.basicConfig(level=logging.DEBUG, \
                        format='%(asctime)s %(name)-12s (%(threadName)-10s):%(levelname)-8s %(message)s', \
                        datefmt='%m-%d %H:%M', \
                        filename=logfname, \
                        filemode='a')
    # define a Handler which writes INFO messages or higher to the sys.stderr
    consolefmtr = logging.Formatter('%(name)-12s: (%(threadName)-10s):%(levelname)-8s %(message)s')
    console = logging.StreamHandler()
    console.setFormatter(consolefmtr)
    console.setLevel(logging.WARNING)
    # add the console handler to the root logger
    logging.getLogger().addHandler(console)



class SingletonMetaClass(type):
    """
    Define a 'SingletonMetaClass' type
    """

    def __init__(cls, name, bases, dicts):
        # call class object's parent(i.e. type)'s __init__()  
        super(SingletonMetaClass, cls).__init__(name, bases, dicts)
        # assign orig_new_method to reference the class's original __new__()
        orig_new_method = cls.__new__
        # declare a local function to replace __new__()
        def replace_new_method(cls, *args, **kwds):
            # if class's variable __instance is None, i.e. nothing
            if cls.__instance == None:
                # call the original new method to create an instance
                cls.__instance = orig_new_method(cls, *args, **kwds)
            return cls.__instance
        # declare class variable
        cls.__instance = None
        # assign class method to new def method, which is decorated as static
        # therefore any interehited class calling __new__() woudl call to
        # replace_new_method() function
        cls.__new__ = staticmethod(replace_new_method)



class DefConfig(object):
    """
        A singleton DefConfig class for loading, saving, getting, setting installer configurations

        e.g.
        DefConfig(object)
        __metaclass__ = SingletonMetaClass
    """
    
    __metaclass__ = SingletonMetaClass
    
    def __init__(self):
        super().__init__()
        self.mSettings = None

    def loadConfig(self, filename):
        """
        loadsConfig(filename) - loads from xml configuration file
        """
        _logger.debug('load configurations from file: {}'.format(filename))
        try:
            if self.mSettings == None:
                self.mSettings = ConvertXmlToDict(filename)
            else:
                self.mSettings.update(ConvertXmlToDict(filename))
            return True
        except TypeError as err:
            return err
    
    def saveConfig(self, filename):
        """
        saveConfig(filename) - saves to xml configuration file
        """
        _logger.debug('save configurations to file: {}'.format(filename))
        root = ConvertDictToXml(self.mSettings)
        tree = ElementTree(root)
        tree.write(open(filename, 'w'), encoding='utf-8')

    def getSettings(self, key=None, flatten=False):
        """
        getConfig() - gets the configuration in a python dictionary, e.g. {}
        """
        ret = {}
        ret.update(self.mSettings)
        if isinstance(key, str):
            return self.__find(key, ret)
        if flatten:
            return self.__flatten(ret)
        return ret
    
    def setSetting(self, changed):
        """
        setConfig(changed) - sets the changed configurations (dict)
        """
        try:
            # check validify of changed dictionary
            if (self.__checkSetting(changed)):
                self.mSettings.update(changed)
                return True
        except TypeError as err:
            return err

    def __checkSetting(self, changed):
        if isinstance(changed, dict):
            # TODO:
            # you can access the data as a dictionary
            # print changed['settings']['color']
            # changed['settings']['color'] = 'red'
            # TODO: Write checking logics here
            
            return True
        elif isinstance(changed, XmlDict):
            # TODO:
            # or you can access it like object attributes
            # print configdict.settings.color
            # configdict.settings.color = 'red'
            # TODO: Write checking logics here
            
            return True
        else:
            raise TypeError('Expected Dictionary or XmlDict')

    def __find(self, key, value):
        ret = {}
        if isinstance(value, dict):
            for k, v in value.items():
                if k == key:
                    ret[k] = v
                elif isinstance(v, dict):
                    ret.update(self.__find(key, v))
                elif isinstance(v, list):
                    for d in v:
                        if isinstance(d, dict):
                            more = self.__find(key, d)
                            for r in more:
                                ret.update(self.__find(key,r))
        return ret

    def __flatten(self, value):
        ret = {}
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, dict):
                    ret.update(self.__flatten(v))
                else:
                    ret[k] = v
        return ret



if __name__ == "__main__":
    defconf = DefConfig()
    defconf.loadConfig("/etc/installer.xml")
    settings = defconf.getSettings()
    print(settings)
    settings.update({'MESSENGER_CLIENT': True})
    defconf.setSetting(settings)
    settings = defconf.getSettings('server_busname')
    print(settings)
    settings = defconf.getSettings('server_name')
    print(settings)
    settings = defconf.getSettings(flatten=True)
    print(settings)
    defconf.saveConfig("./installer.xml")
    exit()