# qagentservice: Windows service wrapper for Qumranet monitoring agent
# The service is converted into an exe-file with py2exe

import win32serviceutil
import win32service
import win32evtlogutil
from GuestAgentWin32 import WinVdsAgent
import logging, logging.config
import servicemanager
import ConfigParser
import os
import _winreg

AGENT_CONFIG = 'cloud-times-guest-agent.ini'

# Values from WM_WTSSESSION_CHANGE message (http://msdn.microsoft.com/en-us/library/aa383828.aspx)
WTS_SESSION_LOGON = 0x5
WTS_SESSION_LOGOFF = 0x6
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8

class UranusGuestService(win32serviceutil.ServiceFramework):
    _svc_name_ = "CTVM Agent"
    _svc_display_name_ = "Uranus Agent Service"
    _svc_description_ = "Uranus Guest Agent Service"
    _svc_deps_ = ["EventLog"]
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self._shutting_down = False
        
        global AGENT_CONFIG

        #hkey = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Redhat\\RHEV\\Tools\\OVirt Guest Agent")
        #AGENT_CONFIG = os.path.join( _winreg.QueryValueEx(hkey, "InstallDir")[0], AGENT_CONFIG)
        #hkey.Close()

        ####################################################################################################
        CurrentInstallDir = os.path.realpath(__file__)
        CurrentInstallDir = os.path.split(CurrentInstallDir)[0]
        CurrentInstallDir = os.path.split(CurrentInstallDir)[0]
                
        AGENT_CONFIG = "\\" + AGENT_CONFIG
        AGENT_CONFIG = CurrentInstallDir + AGENT_CONFIG
        
        ####################################################
        configFile_handler = open(AGENT_CONFIG, 'w')
        
        strArgs = "args=(\'"
        strArgs += CurrentInstallDir
        strArgs += "\\cloud-times-agent.log\', \'a\', 100*1024, 5)\r\n"
        
        strConfigFileText = "\r\n"

        strConfigFileText += "[general]\r\n"
        strConfigFileText += "heart_beat_rate = 5\r\n"
        strConfigFileText += "report_user_rate = 10\r\n"
        strConfigFileText += "report_application_rate = 120\r\n"
        strConfigFileText += "report_disk_usage = 300\r\n"
        strConfigFileText += "\r\n"

        strConfigFileText += "[virtio]\r\n"
        strConfigFileText += "device = \\\\.\\Global\\com.redhat.rhevm.vdsm\r\n"
        strConfigFileText += "\r\n"

        strConfigFileText += "[loggers]\r\n"
        strConfigFileText += "keys=root\r\n"
        strConfigFileText += "\r\n"

        strConfigFileText += "[handlers]\r\n"
        strConfigFileText += "keys=console,logfile\r\n"
        strConfigFileText += "\r\n"

        strConfigFileText += "[formatters]\r\n"
        strConfigFileText += "keys=long,simple,none,sysform\r\n"
        strConfigFileText += "\r\n"

        strConfigFileText += "[logger_root]\r\n"
        strConfigFileText += "level=INFO\r\n"
        strConfigFileText += "handlers=logfile\r\n"
        strConfigFileText += "propagate=0\r\n"
        strConfigFileText += "\r\n"

        strConfigFileText += "[handler_logfile]\r\n"
        strConfigFileText += "class=handlers.RotatingFileHandler\r\n"
        strConfigFileText += strArgs
        strConfigFileText += "formatter=long\r\n"
        strConfigFileText += "\r\n"

        strConfigFileText += "[handler_console]\r\n"
        strConfigFileText += "class: StreamHandler\r\n"
        strConfigFileText += "args: []\r\n"
        strConfigFileText += "formatter: none\r\n"
        strConfigFileText += "\r\n"

        strConfigFileText += "[formatter_simple]\r\n"
        strConfigFileText += "format: %(name)s:%(levelname)s:  %(message)s\r\n"
        strConfigFileText += "\r\n"

        strConfigFileText += "[formatter_none]\r\n"
        strConfigFileText += "format: %(message)s\r\n"
        strConfigFileText += "\r\n"

        strConfigFileText += "[formatter_long]\r\n"
        strConfigFileText += "format: %(threadName)s::%(levelname)s::%(asctime)s::%(module)s::%(lineno)d::%(name)s::%(message)s\r\n"
        strConfigFileText += "\r\n"

        strConfigFileText += "[formatter_sysform]\r\n"
        strConfigFileText += "format= %(asctime)s %(levelname)s %(message)s\r\n"
        strConfigFileText += "datefmt=\r\n"
        
        configFile_handler.write(strConfigFileText)
        configFile_handler.close()
        
        logging.config.fileConfig(AGENT_CONFIG)

    # Overriding this method in order to accept session change notifications.
    def GetAcceptedControls(self):
        accepted = win32serviceutil.ServiceFramework.GetAcceptedControls(self) | win32service.SERVICE_ACCEPT_SESSIONCHANGE
        return accepted

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.vdsAgent.stop()

    def SvcDoRun(self):
        # Write a 'started' event to the event log...
        self.ReportEvent(servicemanager.PYS_SERVICE_STARTED)
        logging.info("Starting OVirt Guest Agent service")

        config = ConfigParser.ConfigParser()
        config.read(AGENT_CONFIG)

        self.vdsAgent = WinVdsAgent(config)
        self.vdsAgent.run()

        # and write a 'stopped' event to the event log (skip this step if the
        # computer is shutting down, because the event log might be down).
        if not self._shutting_down:
            self.ReportEvent(servicemanager.PYS_SERVICE_STOPPED)

        logging.info("Stopping OVirt Guest Agent service")

    def SvcShutdown(self):
        self.vdsAgent.sessionShutdown()
        self._shutting_down = True
        self.vdsAgent.stop()

    def SvcSessionChange(self, event_type):
        if event_type == WTS_SESSION_LOGON:
            self.vdsAgent.sessionLogon()
        elif event_type == WTS_SESSION_LOGOFF:
            self.vdsAgent.sessionLogoff()
        elif event_type == WTS_SESSION_LOCK:
            self.vdsAgent.sessionLock()
        elif event_type == WTS_SESSION_UNLOCK:
            self.vdsAgent.sessionUnlock()

    def SvcOtherEx(self, control, event_type, data):
        if control == win32service.SERVICE_CONTROL_SESSIONCHANGE:
            self.SvcSessionChange(event_type)

    def ReportEvent(self, EventID):
        try:
            win32evtlogutil.ReportEvent(self._svc_name_,
                                        EventID,
                                        0, # category
                                        servicemanager.EVENTLOG_INFORMATION_TYPE,
                                        (self._svc_name_, ''))
        except:
            logging.exception("Failed to write to the event log")


if __name__ == '__main__':
    # Note that this code will not be run in the 'frozen' exe-file!!!
    win32serviceutil.HandleCommandLine(UranusGuestService)
