import os,sys
import subprocess
import time
import re
import ConfigParser
import json

APP_ROOT = 'applications'
LOG_ROOT = 'logs'

# Reading benchmark settings
cf_bs = ConfigParser.SafeConfigParser()
cf_bs.read("configs/benchmark_settings.cfg")

running_iters = cf_bs.getint("profile_control", "iters")
#running_time = cf_bs.getint("profile_control", "secs")
nvIns_dev_id = cf_bs.getint("profile_control", "nvIns_device_id")
cuda_dev_id = cf_bs.getint("profile_control", "cuda_device_id")
pw_sample_int = cf_bs.getint("profile_control", "power_sample_interval")
rest_int = cf_bs.getint("profile_control", "rest_time")
#metrics = json.loads(cf_bs.get("profile_control", "metrics"))
core_frequencies = json.loads(cf_bs.get("dvfs_control", "coreF"))
memory_frequencies = json.loads(cf_bs.get("dvfs_control", "memF"))

# Read GPU application settings
cf_ks = ConfigParser.SafeConfigParser()
cf_ks.read("configs/dl_settings.cfg")
benchmark_programs = cf_ks.sections()

print benchmark_programs
#print metrics
print core_frequencies
print memory_frequencies

if 'linux' in sys.platform:
    pw_sampling_cmd = 'nohup ./nvml_samples -device=%d -si=%d -output=%s/%s 1>null 2>&1 &'
    app_exec_cmd = './%s/%s %s 1>>%s/%s 2>&1'
    dvfs_cmd = 'gpu=%d fcore=%s fmem=%s ./adjustClock.sh' % (nvIns_dev_id, '%s', '%s')
    kill_pw_cmd = 'killall nvml_samples'
elif 'window' in sys.platform:
    pw_sampling_cmd = 'start /B nvml_samples.exe -device=%d -output=%s/%s > nul'
    app_exec_cmd = '%s\\%s %s -device=%d -secs=%d >> %s/%s'
    dvfs_cmd = 'nvidiaInspector.exe -forcepstate:%s,%s -setMemoryClock:%s,1,%s -setGpuClock:%s,1,%s'
    kill_pw_cmd = 'tasklist|findstr "nvml_samples.exe" && taskkill /F /IM nvml_samples.exe'

for core_f in core_frequencies:
    for mem_f in memory_frequencies:

        # set specific frequency
        command = dvfs_cmd % (core_f, mem_f)
        
        print command
        os.system(command)
        time.sleep(rest_int)

        for app in benchmark_programs:

            args = json.loads(cf_ks.get(app, 'args'))
            train_path = cf_ks.get(app, 'train_data')
            test_path = cf_ks.get(app, 'test_data')

            #argNo = 0

            for arg in args:

                # arg, number = re.subn('-device=[0-9]*', '-device=%d' % cuda_dev_id, arg)
                powerlog = 'benchmark_%s_%s_core%d_mem%d_power.log' % (app, arg, core_f, mem_f)
                perflog = 'benchmark_%s_%s_core%d_mem%d_perf.log' % (app, arg, core_f, mem_f)
                metricslog = 'benchmark_%s_%s_core%d_mem%d_metrics.log' % (app, arg, core_f, mem_f)


                # start record power data
                os.system("echo \"app:%s,arg:%s\" > %s/%s" % (app, arg, LOG_ROOT, powerlog))
                command = pw_sampling_cmd % (nvIns_dev_id, pw_sample_int, LOG_ROOT, powerlog)
                print command
                os.system(command)
                time.sleep(rest_int)

                # set data path for the network
                def set_datapath(network):
                    network_path = "networks/%s.prototxt" % network

		    replacement_list = {
		        '$TRAIN_PATH': ('%s' % train_path),
		        '$TEST_PATH': ('%s' % test_path),
		    }

		    proto = ''
		    tfile = open(network_path, "r")
		    proto = tfile.read()
		    tfile.close()

		    for r in replacement_list:
		        proto = proto.replace(r, replacement_list[r])
		    
		    tfile = open('tmp/%s.prototxt' % network, "w")
		    tfile.write(proto)
		    tfile.close()
                    
                set_datapath(arg)    

                exec_arg = "time -model tmp/%s.prototxt -gpu %d -iterations %d" % (arg, cuda_dev_id, running_iters)
                # execute program to collect power data
                os.system("echo \"app:%s,arg:%s\" > %s/%s" % (app, arg, LOG_ROOT, perflog))
                command = app_exec_cmd % (APP_ROOT, app, exec_arg, LOG_ROOT, perflog)
                print command
                os.system(command)
                time.sleep(rest_int)

                # stop record power data
                os.system(kill_pw_cmd)

                # execute program to collect time data
                command = 'nvprof --profile-child-processes %s/%s %s >> %s/%s 2>&1' % (APP_ROOT, app, exec_arg, LOG_ROOT, perflog)
                print command
                os.system(command)
                time.sleep(rest_int)

                # collect grid and block settings
                command = 'nvprof --print-gpu-trace --profile-child-processes %s/%s %s  > %s/%s 2>&1' % (APP_ROOT, app, exec_arg, LOG_ROOT, metricslog)
                print command
                os.system(command)
                time.sleep(rest_int)

                ## execute program to collect metrics data
                #metCount = 0

                ## to be fixed, the stride should be a multiplier of the metric number
                #while metCount < len(metrics):

                #    if metCount + 3 > len(metrics):
                #        metStr = ','.join(metrics[metCount:])
                #    else:
                #        metStr = ','.join(metrics[metCount:metCount + 3])
                #    command = 'nvprof --devices %s --metrics %s %s/%s %s -device=%d -iters=50 >> %s/%s 2>&1' % (cuda_dev_id, metStr, APP_ROOT, app, arg, cuda_dev_id, LOG_ROOT, metricslog)
                #    print command
                #    os.system(command)
                #    time.sleep(rest_int)
                #    metCount += 3
		#argNo += 1

time.sleep(rest_int)
