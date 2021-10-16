import collections
import time

import numpy as np

# from forceDAQ.force import *
from .forceDAQ.force import *

_ForceSensorSetting = collections.namedtuple('ForceSensorSetting',
          'device_name_prefix device_ids sensor_names remote_control '
          'ask_filename calibration_folder '
          ' zip_data write_Fx write_Fy '
          'write_Fz write_Tx write_Ty write_Tz  write_trigger1 '
          'write_trigger2  reverse_scaling convert_to_forces priority')

class ForceSensor:
    def __init__(self, settings):
        self.settings = settings

        sensors = []
        
        for d_id, sn in zip(settings.device_ids, settings.sensor_names):
            try:
                reverse_parameter_names = settings.reverse_scaling[str(d_id)]
            except:
                reverse_parameter_names = []

            sensors.append(SensorSettings(device_id = d_id,
                                    device_name_prefix=settings.device_name_prefix,
                                    sensor_name = sn,
                                    calibration_folder=settings.calibration_folder,
                                    reverse_parameter_names=reverse_parameter_names,
                                    rate = 1000, # This could be changed later, let's see
                                    convert_to_FT=settings.convert_to_forces))

        self.n_sensors = len(sensors)
        self._last_processed_smpl = [0] * self.n_sensors

        self.recorder = DataRecorder(sensors,
                 poll_udp_connection=True,
                 write_deviceid = len(settings.device_ids)>1,
                 write_Fx = settings.write_Fx,
                 write_Fy = settings.write_Fy,
                 write_Fz = settings.write_Fz,
                 write_Tx = settings.write_Tx,
                 write_Ty = settings.write_Ty,
                 write_Tz = settings.write_Tz,
                 write_trigger1= settings.write_trigger1,
                 write_trigger2= settings.write_trigger2,
                 polling_priority=settings.priority)

        time.sleep(0.5)
        # self.sensor_type = []
        # for proc in self.recorder.force_sensor_processes:
        #     self.sensor_type+=[proc.sensor_type]
    
        self.recorder.determine_biases(n_samples=500)

    def start_recording(self):
        self.recorder.start_recording()

    def pause_recording(self):
        self.recorder.pause_recording()

    def get_data(self, num_samples):
        # st_time = time.time()
        # print('Start: 0')
        # self.recorder.start_recording()
        # print('Rec_start: {}'.format(time.time()-st_time))
        data = [[]]*self.n_sensors
        # For multiple sensors, k will need to be redefined differently
        k = 0
        while k<num_samples:
            # if pause_recording:
            #     app_timer.wait(100)

            udp = self.recorder.process_and_write_udp_events()
            while len(udp)>0:
                udp_event = udp.pop(0)
                udp_data = udp_event.byte_string
                # print(udp_data)
            
            check_new = self.check_new_samples()
            # print(check_new)
            for s in check_new:
                new_data = list(self.recorder.force_sensor_processes[s].get_Fxyz())
                data[s] += [new_data]
                k+=1
        # print(new_data)
        
        # print('Rec_pause: {}'.format(time.time()-st_time))
        # self.recorder.pause_recording()
        # print('Rec_end: {}'.format(time.time()-st_time))
            # app_timer.wait(500)

        return data    
    def check_new_samples(self):
        """returns list of sensors with new samples"""
        rtn = []
        for i,cnt in enumerate(map(SensorProcess.get_sample_cnt, self.recorder.force_sensor_processes)):
            if self._last_processed_smpl[i] < cnt:
                # new sample
                self._last_processed_smpl[i] = cnt
                rtn.append(i)
        return rtn
    
    def quit(self):
        self.recorder.quit()

if __name__ == '__main__':

    settings = _ForceSensorSetting(device_name_prefix="Dev",
                       device_ids = [1],
                       sensor_names = ["FT29531"],
                       calibration_folder="./",
                       reverse_scaling = {1: ["Fz"], 2:["Fz"]},  # key: device_id, parameter. E.g.:if x & z dimension of sensor 1 and z dimension of sensor 2 has to be flipped use {1: ["Fx", "Fz"], 2: ["Fz"]}
                       remote_control=False, ask_filename= False, write_Fx=True,
                       write_Fy=True, write_Fz=True, write_Tx=False, write_Ty=False,
                       write_Tz=False, write_trigger1=True, write_trigger2=False,
                       zip_data=True, convert_to_forces=True,
                       priority='normal')

    a = ForceSensor(settings)
    a.get_data(100)
    a.recorder.quit()