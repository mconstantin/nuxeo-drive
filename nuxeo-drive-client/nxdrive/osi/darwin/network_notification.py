#
# @file: reach
# @author: Michael Constantin
# @date: 10/20/16
#
# Copyright (C) Sharp 2016


from Foundation import NSNotificationCenter
from AppKit import NSLog, NSObject, NSWorkspace
from reachability import Reachability, kReachabilityChangedNotification

from nxdrive.logging_config import get_logger


log = get_logger(__name__)


class ReachabilityHandler(NSObject):
    """
    Handle reachability notifications from the network.
    """
    @staticmethod
    def handleChange_(target, flags, info):
        """
        Handle Reachability changes here.
        """
        log.info("network %s!", "connected" if flags == 2 else "disconnected")


def setup_reachability():
    rhandler = ReachabilityHandler.new()

    workspace = NSWorkspace.sharedWorkspace()
    default_center = NSNotificationCenter.defaultCenter()
    default_center.addObserver_selector_name_object_(
                rhandler,
                "handleChange:",
                kReachabilityChangedNotification,
                None)

    reachability = Reachability()
    reachability.startNotifier(callback=ReachabilityHandler.handleChange_)