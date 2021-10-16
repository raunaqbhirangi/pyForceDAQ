__author__ = "Oliver Lindemann"
__version__ = "0.3"

from ._config import DAQConfiguration
from ._pyATIDAQ import ATI_CDLL
from .. import USE_DUMMY_SENSOR


#### change import here if you want to use nidaqmx instead of pydaymx ####
try:
    # from ._daq_read_Analog_pydaqmx import DAQReadAnalog
    from ..daq._daq_read_analog_nidaqmx import DAQReadAnalog
    print('works')
except:
    print('nope')
    from ._daq_read_Analog_dummy import DAQReadAnalog

if USE_DUMMY_SENSOR:
    from ._daq_read_Analog_dummy import DAQReadAnalog
