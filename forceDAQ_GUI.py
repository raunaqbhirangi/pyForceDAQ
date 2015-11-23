__author__ = 'Oliver Lindemann'

from forceDAQ import remote_control

if __name__ == "__main__":
    from forceDAQ import gui

    remote_control = True
    gui.start(remote_control=remote_control,
              ask_filename=not remote_control,
              calibration_file="calibration/FT_demo.cal",
              write_deviceid=False,
              write_Fx=True,
              write_Fy=True,
              write_Fz=True,
              write_Tx=False,
              write_Ty=False,
              write_Tz=False,
              write_trigger1=True,
              write_trigger2=False,
              zip_data=True)
