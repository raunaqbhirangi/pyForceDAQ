#!/usr/bin/env python

"""
Functions to convert force data

This module can be also executed.
"""

__author__ = 'Oliver Lindemann'

import os
import sys
import gzip
import numpy as np
from .read_force_data import read_raw_data, data_frame_to_text

PAUSE_CRITERION = 500
MSEC_PER_SAMPLES = 1
REFERENCE_SAMPLE = 1000
CONVERTED_SUFFIX = ".conv.csv.gz"
CONVERTED_SUBFOLDER = "converted"

def _periods_from_daq_events(daq_events):

    periods = {}
    started = None
    sensor_id = None
    evt = np.array(daq_events["value"])
    times = np.array(daq_events["time"]).astype(int)
    idx = np.argsort(times)

    for t, v in zip(times[idx], evt[idx]):
        try:
            sensor_id = int(v.split(":")[1])
        except:
            sensor_id = None

        if sensor_id not in periods:
            periods[sensor_id] = []

        if v.startswith("started"):
            if started is None:
                started = t
            else:
                periods[sensor_id].append((started, None))
                started = None
        elif v.startswith("pause"):
            periods[sensor_id].append((started, t))
            started = None

    # sort remaining
    if started is not None:
        periods[sensor_id].append((started, None))

    return periods

def _pauses_idx_from_timeline(time, pause_criterion):
    pauses_idx = np.where(np.diff(time) > pause_criterion)[0]
    last_pause = -1
    rtn = []
    for idx in np.append(pauses_idx, len(time)-1):
        rtn.append((last_pause+1, idx))
        last_pause = idx
    return rtn

def _most_frequent_value(values):
    (v, cnt) = np.unique(values, return_counts=True)
    idx = np.argmax(cnt)
    return v[idx]

#def _hist(values):
#    (v, cnt) = np.unique(values, return_counts=True)
#    for a,b in zip(v,cnt):
#        print("{} -- {}".format(a,b))


def _matched_regular_timeline(irregular_timeline,
                              id_ref_sample, msec_per_sample):
    """match timeline that differences between the two is minimal
    new times can not be after irregular times
    """
    t_ref = irregular_timeline[id_ref_sample-1]
    t_first = t_ref - ((id_ref_sample-1)*msec_per_sample)
    t_last = t_first + ((len(irregular_timeline) - 1) * msec_per_sample)
    return np.arange(t_first, t_last + msec_per_sample, step=msec_per_sample)

def _adjusted_timestamps(timestamps, pauses_idx, evt_periods):

    # adapting timestamps
    rtn = np.empty(len(timestamps))*np.NaN
    period_counter = 0
    for idx, evt_per in zip(pauses_idx, evt_periods):
        period_counter += 1
        n_samples = idx[1] - idx[0] + 1
        if evt_per[1]: # end time
            sample_diff  = n_samples - (1+(evt_per[1]-evt_per[0])//MSEC_PER_SAMPLES)
            if sample_diff!=0:
                print("Period {}: Sample difference of {}".format(
                    period_counter, sample_diff))
        else:
            print("Period {}: No pause sampling time.".format(period_counter))

        irregular_times = timestamps[idx[0]:idx[1] + 1]
        # find ref sample or find next 10+ delay
        next_t_diffs = np.diff(irregular_times[REFERENCE_SAMPLE:(REFERENCE_SAMPLE+1000)])
        try:
            next_delayed = 1 + np.where(next_t_diffs>=10)[0][0]
        except:
            try:
                next_delayed = 1 + np.where(next_t_diffs>0)[0][0]
            except:
                next_delayed = 0

        newtimes = _matched_regular_timeline(irregular_times,
                                    id_ref_sample=REFERENCE_SAMPLE + next_delayed,
                                    msec_per_sample=MSEC_PER_SAMPLES)
        rtn[idx[0]:idx[1] + 1] = newtimes

    return rtn.astype(int)

def converted_filename(flname):
    """returns path and filename of the converted data file"""
    if flname.endswith(".gz"):
        tmp = flname[:-7]
    else:
        tmp = flname[:-4]

    path, new_filename = os.path.split(tmp)
    converted_path = os.path.join(path, CONVERTED_SUBFOLDER)
    return converted_path, new_filename + CONVERTED_SUFFIX

def convert_raw_data(filepath):
    """preprocessing raw pyForceData:

    """
    # todo only one sensor

    filepath = os.path.join(os.path.split(sys.argv[0])[0], filepath)
    print("converting {}".format(filepath))

    data, udp_event, daq_events, comments = read_raw_data(filepath)
    print("{} samples".format(len(data["time"])))

    sensor_id = 1
    # adapt timestamps
    _delay = np.array(data.pop("delay")).astype(int) # remove delays

    timestamps = np.array(data["time"]).astype(int)
    #pauses
    pauses_idx = _pauses_idx_from_timeline(timestamps, pause_criterion=PAUSE_CRITERION)
    evt_periods = _periods_from_daq_events(daq_events)

    if len(pauses_idx) != len(evt_periods[sensor_id]):
        raise RuntimeError("Pauses in DAQ events do not match recording pauses")
    else:
        data["adj_time"] = _adjusted_timestamps(timestamps=timestamps,
                                            pauses_idx=pauses_idx,
                                            evt_periods=evt_periods[sensor_id])

    folder, new_filename = converted_filename(filepath)
    try:
        os.makedirs(folder)
    except:
        pass
    new_filename = os.path.join(folder, new_filename)

    with gzip.open(new_filename, "wt") as fl:
        fl.write(comments.strip() + "\n")
        fl.write(data_frame_to_text(data))



def get_all_unconverted_data_files(folder):
    rtn = []
    files = os.listdir(folder)

    try:
        c_path, _ = converted_filename(os.path.join(folder, files[0]))
        converted_files = os.listdir(c_path)
    except:
        converted_files = []

    for flname in files:
        if (flname.endswith(".csv") or flname.endswith(".csv.gz")) and not \
                flname.endswith(CONVERTED_SUFFIX):
            flname = os.path.join(folder, flname)
            _, c_flname = converted_filename(flname)
            if c_flname not in converted_files:
                rtn.append(flname)
    return rtn

