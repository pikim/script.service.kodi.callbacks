#!/usr/bin/python
# -*- coding: utf-8 -*-
#
#     Copyright (C) 2016 KenV99
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
import sys
import os
import xbmcaddon
libs = os.path.join(xbmcaddon.Addon('script.service.kodi.callbacks').getAddonInfo('path'), 'resources', 'lib')
if libs.startswith('resources'):
    libs = 'C:\\Users\\Ken User\\AppData\\Roaming\\Kodi\\addons\\script.service.kodi.callbacks\\' + libs
sys.path.append(libs)

libs = os.path.join(xbmcaddon.Addon('script.service.kodi.callbacks').getAddonInfo('path'), 'resources', 'lib', 'watchdog')
if libs.startswith('resources'):
    libs = 'C:\\Users\\Ken User\\AppData\\Roaming\\Kodi\\addons\\script.service.kodi.callbacks\\' + libs
sys.path.append(libs)

import pickle
import xbmc
from resources.lib.events import Events
from resources.lib.watchdog.utils.dirsnapshot import DirectorySnapshot, DirectorySnapshotDiff
from resources.lib.watchdog.observers import Observer
from resources.lib.watchdog.events import PatternMatchingEventHandler, FileSystemEvent, EVENT_TYPE_CREATED, EVENT_TYPE_DELETED, EVENT_TYPE_MODIFIED, EVENT_TYPE_MOVED
from resources.lib.pubsub import Publisher, Message, Topic


class EventHandler(PatternMatchingEventHandler):
    def __init__(self, patterns, ignore_patterns, ignore_directories):
        super(EventHandler, self).__init__(patterns=patterns, ignore_patterns=ignore_patterns,
                                           ignore_directories=ignore_directories)
        self.data = {}

    def on_any_event(self, event):
        if event.is_directory:
            et = 'Dirs%s' % event.event_type.capitalize()
        else:
            et = 'Files%s' % event.event_type.capitalize()
        if et in self.data.keys():
            self.data[et].append(event.src_path)
        else:
            self.data[et] = [event.src_path]
#
# class StartupEvent(FileSystemEvent):
#
#     def __init__(self, folder, data):
#         super(StartupEvent, self).__init__(folder)
#         self.is_directory = True
#         self.data = data


class WatchdogStartup(Publisher):
    publishes = Events().WatchdogStartup.keys()

    def __init__(self, dispatcher, settings):
        super(WatchdogStartup, self).__init__(dispatcher)
        self.pickle = xbmc.translatePath(r'special://profile\addon_data\script.service.kodi.callbacks\watchdog.pkl')
        self.settings = settings.getWatchdogStartupSettings()

    def start(self):
        if not os.path.exists(self.pickle):
            return
        try:
            with open(self.pickle, 'r') as f:
                oldsnapshots = pickle.load(f)
        except OSError:
            raise
        newsnapshots = {}
        for setting in self.settings:
            folder = setting['ws_folder']
            if os.path.exists(folder):
                newsnapshot = DirectorySnapshot(folder, recursive=setting['ws_recursive'])
                newsnapshots[folder] = newsnapshot
                if folder in oldsnapshots.keys():
                    oldsnapshot = oldsnapshots[folder]
                    diff = DirectorySnapshotDiff(oldsnapshot, newsnapshot)
                    changes = self.getChangesFromDiff(diff)
                    if len(changes) > 0:
                        eh = EventHandler(patterns=setting['ws_patterns'].split(','), ignore_patterns=setting['ws_ignore_patterns'].split(','),
                                          ignore_directories=setting['ws_ignore_directories'])
                        observer = Observer()
                        try:
                            observer.schedule(eh, folder, recursive=setting['ws_recursive'])
                            for change in changes:
                                eh.dispatch(change)
                            observer.unschedule_all()
                        except Exception:
                            raise
                        if len(eh.data) > 0:
                            message = Message(Topic('onStartupFileChanges', setting['key']), listOfChanges=eh.data)
                            self.publish(message)
            else:
                message = Message(Topic('onStartupFileChanges', setting['key']), listOfChanges=[{'DirsDeleted':folder}])
                self.publish(message)

    @staticmethod
    def getChangesFromDiff(diff):
        ret = []
        events = {'dirs_created':(EVENT_TYPE_CREATED, True), 'dirs_deleted':(EVENT_TYPE_DELETED, True), 'dirs_modified':(EVENT_TYPE_MODIFIED, True), 'dirs_moved':(EVENT_TYPE_MOVED, True),
                  'files_created':(EVENT_TYPE_CREATED, False), 'files_deleted':(EVENT_TYPE_DELETED, False), 'files_modified':(EVENT_TYPE_MODIFIED, False), 'files_moved':(EVENT_TYPE_MOVED, False)}
        for event in events.keys():
            try:
                mylist = diff.__getattribute__(event)
            except Exception as e:
                mylist = []
            if len(mylist) > 0:
                for item in mylist:
                    evt = FileSystemEvent(item)
                    evt.event_type = events[event][0]
                    evt.is_directory = events[event][1]
                    ret.append(evt)
        return ret

    def abort(self, arg=None):
        snapshots = {}
        for setting in self.settings:
            folder = setting['ws_folder']
            if os.path.exists(folder):
                snapshot = DirectorySnapshot(folder, recursive=setting['ws_recursive'])
                snapshots[folder] = snapshot
        try:
            with open(self.pickle, 'w') as f:
                pickle.dump(snapshots, f)
        except Exception as e:
            raise

def clearPickle():
    path = xbmc.translatePath(r'special://profile\addon_data\script.service.kodi.callbacks\watchdog.pkl')
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            raise