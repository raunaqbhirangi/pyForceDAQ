"""class to record force sensor data

See COPYING file distributed along with the pyForceDAQ copyright and license terms.
"""
__author__ = "Oliver Lindemann"

import atexit
import gzip
import os
import sys
import logging
from time import localtime, strftime,asctime

from .. import __version__ as forceDAQVersion
from .._lib.types import ForceData, UDPData, DAQEvents, TAG_DAQEVENT, \
                        TAG_UDPDATA, TAG_COMMENTS, PollingPriority
from .._lib.types import GUIRemoteControlCommands as RemoteCmd
from .._lib.udp_connection import UDPConnectionProcess
from .._lib.process_priority_manager import ProcessPriorityManager
from .._lib.timer import app_timer
from .sensor import SensorSettings
from .sensor_process import SensorProcess

NEWLINE = "\n"

class DataRecorder(object):
    """handles multiple sensors and udp connection"""

    def __init__(self, force_sensor_settings,
                 poll_udp_connection=False,
                 write_deviceid = False,
                 write_Fx = True,
                 write_Fy = True,
                 write_Fz = True,
                 write_Tx = False,
                 write_Ty = False,
                 write_Tz = False,
                 write_trigger1 = True,
                 write_trigger2 = False,
                 polling_priority=None):


        """queue_data will be saved
        see sensorprocess.__init__

        polling_priority has to be types.PollingPriority.{HIGH},
        {REALTIME} or {NORMAL} or None
        """

        self._write_deviceid = write_deviceid
        self._write_forces = [write_Fx, write_Fy, write_Fz, write_Tx, write_Ty, write_Tz]
        self._write_trigger = [write_trigger1, write_trigger2]

        #create sensor processes
        if not isinstance(force_sensor_settings, list):
            force_sensor_settings = [force_sensor_settings]
        self._force_sensor_processes =[]

        event_trigger = []
        for fs in force_sensor_settings:
            if not isinstance(fs, SensorSettings):
                RuntimeError("Recorder needs a list of Force Sensor Settings!")
            else:
                fst = SensorProcess(settings = fs,
                                    pipe_buffered_data_after_pause=True)
                fst.start()
                event_trigger.append(fst.event_trigger)
                self._force_sensor_processes.append(fst)

        # create udp connection process
        if poll_udp_connection:
            self.udp = UDPConnectionProcess(event_trigger=event_trigger,
                                            event_ignore_tag = RemoteCmd.COMMAND_STR)
            self.udp.start()
        else:
            self.udp = None

        # process managing
        self._proc_manager = ProcessPriorityManager()
        self._proc_manager.add_subprocess(self.udp)
        self._proc_manager.add_subprocess(self._force_sensor_processes)
        if polling_priority is not None:
            self._proc_manager.set_subprocess_priorities(
                level=PollingPriority.get_priority(polling_priority),
                disable_gc=False)

        logging.info("Main process priority: {}".format(
            self._proc_manager.get_main_priority()))
        #logging.info("Subprocess priorities: {}".format(self._proc_manager.get_subprocess_priorities()))

        self._is_recording = False
        self._file = None
        self._daq_event = []
        self.filename = None
        atexit.register(self.quit)


    @property
    def is_alive(self):
        """Property indicates whether the recording processes are alive"""
        try:
            return self._force_sensor_processes[0].is_alive()
        except:
            return False

    @property
    def is_recording(self):
        """Property indicates whether the recording is started or paused"""
        return self._is_recording

    @property
    def force_sensor_processes(self):
        return self._force_sensor_processes

    @property
    def sensor_settings_list(self):
        return list(map(lambda x:x.sensor_settings,
                        self._force_sensor_processes))

    def quit(self):
        """Stop all recording processes, close data file and quit recording

        Notes
        -----
        Will be automatically called at exit.

        """

        if not self.is_alive:
            return

        buffer = self.pause_recording()
        self.close_data_file()

        if self.udp is not None:
            self.udp.quit()

        # wait that all processes are quitted
        for fsp in self._force_sensor_processes:
            fsp.join()

        logging.info("Quit recording")

        return buffer

    def process_and_write_udp_events(self):
        """process udp events and return them"""
        buffer = []
        while True:
            try:
                data = self.udp.receive_queue.get_nowait()
            except:
                # until queue empty or no udp connection
                break
            buffer.append(data)
        if len(buffer)>0:
            self._save_data(buffer)
        return buffer

    def _save_data(self, data_buffer,
                   recording_screen=None,
                   float_decimal_places=4):
        """ writes data to disk and set counters

        ignores UDP remote control commands
        """
        #DOC output format

        BLOCKSIZE = 10000 # for recording screen feedback only

        float_format = "{0:." + str(float_decimal_places) + "f},"
        buffer_len = len(data_buffer)
        for c, d in enumerate(data_buffer):
            if self._file is not None:
                if isinstance(d, ForceData):
                    line = "{}, {},".format(d.time, d.acquisition_delay)
                    if self._write_deviceid:
                        line += "{0},".format(d.device_id)
                    for x in range(6):
                        if self._write_forces[x]:
                            line += float_format.format(d.forces[x])
                    for x in range(2):
                        if self._write_trigger[x]:
                            if isinstance(d.trigger[x], int):
                                line += "{0},".format(d.trigger[x])
                            else:
                                line += float_format.format(d.trigger[x])
                    self._file_write(line[:-1] + NEWLINE)

                elif isinstance(d, DAQEvents):
                    self._file_write("{0},{1},{2}".format(TAG_DAQEVENT, d.time, str(d.code)) + NEWLINE)

                elif isinstance(d, UDPData):
                    if not d.is_remote_control_command:
                        self._file_write("{0},{1},{2}".format(TAG_UDPDATA, d.time, d.unicode) + NEWLINE)

            if recording_screen is not None and c % BLOCKSIZE == 0:
                recording_screen.stimulus(
                    "Writing {0} of {1} blocks".format(c//BLOCKSIZE,
                                                       buffer_len//BLOCKSIZE)).present()

    def _file_write(self, str):
        self._file.write(str.encode())

    def save_daq_event(self, code, time=None):
        """Set marker code in file

        DAQEvent will be timestamps and occur in the data output

        """
        if time is None:
            time = app_timer.time
        self._daq_event.append(DAQEvents(time = time, code = code))


    def start_recording(self, determine_bias=False):
        """Start polling process and record

        See Also
        --------
        is_recording

        """

        if determine_bias:
            self.determine_biases(n_samples=1000)

        if len(list(filter(lambda x:x.event_bias_is_available.is_set(),
                   self._force_sensor_processes))) != len(self._force_sensor_processes):
            raise RuntimeError("Sensors can't be started before bias has been determined.")

        # start polling
        list(map(lambda x:x.start_polling(), self._force_sensor_processes))
        self._is_recording = True

    def pause_recording(self, recording_screen=None):
        """Pauses all polling processes and process data

        returns
        --------
        data : all last data

        """
        self._is_recording = False

        data = []
        if recording_screen is not None:
            recording_screen.stimulus("writing data ...").present()

        #pause polling
        for fsp in self._force_sensor_processes:
            fsp.pause_polling()

        app_timer.wait(500)

        # get data
        for fsp in self._force_sensor_processes:
            buffer = fsp.get_buffer(timeout=10.0)
            self._save_data(buffer, recording_screen)
            data.extend(buffer)

        # udp event
        data.extend(self.process_and_write_udp_events())

        # soft trigger
        self._save_data(self._daq_event)
        data.extend(self._daq_event)
        self._daq_event = []
        return data

    def determine_biases(self, n_samples):
        """Record n data samples (n_samples) to determine bias.
        Afterwards recording is in pause mode

        Notes
        -----
        The function take some time to be processed

        See Also
        --------
        Sensor.determine_bias()

        """

        self.pause_recording()
        for x in self._force_sensor_processes:
            x.determine_bias(n_samples=n_samples)

        for x in self._force_sensor_processes:
            x.event_bias_is_available.wait()

    def open_data_file(self, filename,
                       subdirectory="data",
                       time_stamp_filename=False,
                       varnames = True,
                       comment_line="",
                       zipped=False):
        """Create a data file

        Only if data file has been opened, data will be saved!

        Parameters
        ----------
        filename : string
            the filename
        subdirectory : string, optional
            the data subdirectory
        time_stamp_filename : boolean, optional
            if True all filename will contain a timestamp. This is usefull to
            ensure that data will not overwritten
        varnames : boolean, optional
            write variable names in first line of data output
        comment_line : string, optional
            add some comments at the beginning of the data output file
        zippers : boolean, optional
            are the data zipped or not. Note: Saving zipped data after pause
            takes much longer.

        Returns
        -------
        filename : string
                full path the actually used file (incl. timestamp)

        """

        base_dir = os.path.split(sys.argv[0])[0]
        data_dir = os.path.join(base_dir, subdirectory)
        if not os.path.isdir(data_dir):
            os.mkdir(data_dir)
        self.close_data_file()

        if filename is None or len(filename) == 0:
            filename = "daq_recording.csv"

        if zipped:
            suffix = ".gz"
        else:
            suffix = ""

        cnt = 0
        while True:
            flname = filename
            if cnt>0:
                x = flname.find(".")
                if x<0:
                    x = len(flname)
                flname = flname[:x] + "_{0}".format(cnt) + flname[x:]

            if time_stamp_filename:
                self.filename = flname + "_" + \
                        strftime("%Y%m%d%H%M", localtime()) + suffix
            else:
                self.filename = flname + suffix

            full_path_file = os.path.join(data_dir, self.filename)
            if os.path.isfile(full_path_file):
                # print "data file already exists, adding counter"
                cnt += 1
            else:
                break

        if zipped:
            self._file = gzip.open(full_path_file, 'w+')
        else:
            self._file = open(full_path_file, 'w+')
        print("Data file: {}".format(full_path_file))

        self._file_write(TAG_COMMENTS + "Recorded at {0} with pyForceDAQ {1}\n".format(
            asctime(localtime()), forceDAQVersion))
        logging.info("new file: {}".format(filename))

        for s in self.sensor_settings_list:
            txt = " Sensor: id={0}, name={1}, cal-file={2}\n".format(s.device_id,
                                s.sensor_name, s.calibration_file)
            self._file_write(TAG_COMMENTS + txt)

        if len(comment_line)>0:
            self._file_write(TAG_COMMENTS + comment_line + "\n")
        if varnames:
            line = "time,delay,"
            if self._write_deviceid: line += "device_tag,"
            for x in range(6):
                if self._write_forces[x]:
                    line += ForceData.forces_names[x] + ","
            if self._write_trigger[0]: line += "trigger1,"
            if self._write_trigger[1]: line += "trigger2,"
            self._file_write(line[:-1] + NEWLINE)

        return full_path_file

    def close_data_file(self):
        """Close the data file

        Afterwards data will not be saved anymore.

        """

        if self._file is not None:
            self._file.close()
            self._file = None
